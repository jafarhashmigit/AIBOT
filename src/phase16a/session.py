"""Controlled 1-hour read-only MT5 observation session for H13_C shadow."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase12.bar_validator import gap_status
from phase16a.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DATA_DIR,
    MT5_TERMINAL_PATH,
    POLL_INTERVAL_SECONDS,
    SESSION_DURATION_SECONDS,
    SOURCE_TYPE,
    SYMBOL,
    TIMEFRAME,
)
from phase16a.mt5_reader import (
    close_readonly,
    detect_timestamp_mode,
    fetch_completed_h1,
    fetch_completed_m5,
    h1_rows_for_trend,
    now_utc_stamp,
    open_readonly,
)
from phase16a.predictor import predict_h13c_experimental
from phase16a.storage import Phase16aShadowStore

UTC = timezone.utc
PKT = ZoneInfo("Asia/Karachi")


def _to_pkt(utc_stamp: str) -> str:
    dt = datetime.strptime(utc_stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return dt.astimezone(PKT).strftime("%Y-%m-%d %H:%M:%S %Z")


def run_pilot_session(
    *,
    duration_seconds: int = SESSION_DURATION_SECONDS,
    terminal_path: str = MT5_TERMINAL_PATH,
    poll_interval: int = POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    store = Phase16aShadowStore(DATA_DIR)
    if store.has_lock():
        return {
            "status": "aborted",
            "reason": "session lock already present; refusing start",
        }

    started = now_utc_stamp()
    session_id = f"phase16a_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"
    conn = open_readonly(terminal_path)
    if conn.get("status") != "connected_readonly":
        return {"status": "aborted", "reason": "mt5 connect failed", "mt5": conn}

    handle = conn["handle"]
    ts_mode = detect_timestamp_mode(handle, as_of_utc=now_utc_stamp())
    store.write_lock(session_id, "live_mt5_readonly_pilot", started)
    store.append_session(
        {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": started,
            "stopped_at_utc": "",
            "mode": "live_mt5_readonly_pilot",
            "mt5_connected": True,
            "error": "",
            "notes": f"controlled {duration_seconds}s pilot; H13_C experimental; champion NO_MODEL",
        }
    )

    counts = {"BUY": 0, "SELL": 0, "WAIT": 0}
    candles_observed = 0
    gaps = 0
    errors: list[str] = []
    last_open = store.last_open_utc()
    deadline = datetime.strptime(started, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) + timedelta(
        seconds=duration_seconds
    )

    try:
        while datetime.now(UTC) < deadline:
            as_of = now_utc_stamp()
            m5_bars = fetch_completed_m5(handle, count=300, as_of_utc=as_of, ts_mode=ts_mode)
            h1_bars = fetch_completed_h1(handle, count=300, as_of_utc=as_of, ts_mode=ts_mode)
            h1_rows = h1_rows_for_trend(h1_bars)
            m5_bars_sorted = sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"])

            # Process only newly completed bars after last_open
            new_bars = [
                b
                for b in m5_bars_sorted
                if last_open is None or b["bar_open_timestamp_utc"] > last_open
            ]
            # Warmup: if first poll, ingest only the latest completed bar to avoid bulk backfill
            if last_open is None and new_bars:
                new_bars = new_bars[-1:]

            closes = [float(b["close"]) for b in m5_bars_sorted]
            open_to_idx = {b["bar_open_timestamp_utc"]: i for i, b in enumerate(m5_bars_sorted)}

            prev = last_open
            for bar in new_bars:
                try:
                    g = gap_status(prev, bar["bar_open_timestamp_utc"])
                    if g == "gap":
                        gaps += 1
                        quality = "gap"
                    else:
                        quality = "ok"
                    idx = open_to_idx[bar["bar_open_timestamp_utc"]]
                    # Features from closes up to and including this bar only
                    pred = predict_h13c_experimental(
                        m5_closes=closes[: idx + 1],
                        h1_rows=h1_rows,
                        decision_time_utc=bar["bar_close_timestamp_utc"],
                    )
                    obs_id = f"obs_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
                    dec_id = f"dec_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
                    obs = {
                        "observation_id": obs_id,
                        "source_type": SOURCE_TYPE,
                        "symbol": SYMBOL,
                        "timeframe": TIMEFRAME,
                        "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
                        "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
                        "observation_created_at_utc": as_of,
                        "open": bar["open"],
                        "high": bar["high"],
                        "low": bar["low"],
                        "close": bar["close"],
                        "tick_volume": bar["tick_volume"],
                        "spread": bar.get("spread", 0.0),
                        "data_source": bar["data_source"],
                        "data_quality_status": quality,
                        "gap_status": g,
                        "model_status": CHAMPION_STATUS,
                        "feature_snapshot_reference": dec_id,
                        "source_timezone": bar["source_timezone"],
                        "conversion": bar["conversion"],
                        "source_stamp": bar["source_stamp"],
                        "decision_id": dec_id,
                        "candidate_id": CANDIDATE,
                        "candidate_status": CANDIDATE_STATUS,
                        "market_regime": pred["market_regime"],
                    }
                    store.append_observation(obs)
                    dec = {
                        "decision_id": dec_id,
                        "observation_id": obs_id,
                        "source_type": SOURCE_TYPE,
                        "decision_timestamp_utc": bar["bar_close_timestamp_utc"],
                        "symbol": SYMBOL,
                        "timeframe": TIMEFRAME,
                        "model_id": "no_model",
                        "model_status": CHAMPION_STATUS,
                        "candidate_id": CANDIDATE,
                        "candidate_status": CANDIDATE_STATUS,
                        "experimental_action": pred["experimental_action"],
                        "raw_action": pred["raw_action"],
                        "risk_gate_result": pred["gate"]["gate_status"],
                        "final_action": pred["final_action"],
                        "decision_reason": pred["experimental_reason"],
                        "feature_snapshot_json": pred["feature_snapshot_json"],
                        "outcome_status": "pending"
                        if pred["experimental_action"] in {"BUY", "SELL"}
                        else "n_a_wait",
                        "is_paper_trade": False,
                        "is_paper_execution": False,
                        "note": (
                            "experimental H13_C shadow; production final_action WAIT; "
                            "no broker order; no paper fill"
                        ),
                    }
                    store.append_decision(dec)
                    counts[pred["experimental_action"]] = counts.get(pred["experimental_action"], 0) + 1
                    candles_observed += 1
                    last_open = bar["bar_open_timestamp_utc"]
                    prev = last_open
                except Exception as exc:
                    errors.append(f"{bar.get('bar_open_timestamp_utc')}: {exc}")

            # Refresh outcomes for experimental BUY/SELL using current completed path
            store.refresh_outcomes(m5_bars_sorted, as_of_utc=as_of)
            time.sleep(max(1, int(poll_interval)))
    finally:
        close_readonly(handle)
        stopped = now_utc_stamp()
        store.clear_lock()
        store.append_session(
            {
                "session_id": session_id,
                "status": "stopped",
                "started_at_utc": started,
                "stopped_at_utc": stopped,
                "mode": "live_mt5_readonly_pilot",
                "mt5_connected": False,
                "error": "; ".join(errors[:20]),
                "notes": "graceful stop; lock cleared",
            }
        )

    outcomes = store.outcomes()
    pending = sum(1 for o in outcomes if o.get("outcome_status") == "pending")
    completed = sum(1 for o in outcomes if o.get("outcome_status") == "complete")
    excluded = sum(1 for o in outcomes if o.get("outcome_status") == "excluded_gap")

    return {
        "status": "completed",
        "session_id": session_id,
        "started_at_utc": started,
        "stopped_at_utc": stopped,
        "started_at_pkt": _to_pkt(started),
        "stopped_at_pkt": _to_pkt(stopped),
        "duration_seconds_target": duration_seconds,
        "mt5_server": conn.get("server"),
        "timestamp_mode": ts_mode,
        "candles_observed": candles_observed,
        "prediction_counts": counts,
        "gaps_detected": gaps,
        "errors": errors,
        "outcomes": {
            "pending": pending,
            "completed": completed,
            "excluded_gap": excluded,
            "total_tracked": len(outcomes),
        },
        "lock_remaining": store.has_lock(),
        "broker_orders": 0,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
    }
