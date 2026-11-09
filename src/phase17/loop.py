"""Bounded read-only shadow loop: observe → predict → journal → Discord."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from phase12.bar_validator import gap_status
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
from phase16b.client import post_webhook
from phase16b.dedupe import DeliveryLedger
from phase16b.secrets import load_webhook_url, redact_secrets, webhook_configured
from phase17.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_ENABLE_DISCORD,
    DEFAULT_MAX_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    SOURCE_TYPE,
    SYMBOL,
    TIMEFRAME,
)
from phase17.shadow_messages import build_shadow_payload

UTC = timezone.utc

BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class ShadowLoopError(RuntimeError):
    pass


def _ensure_wait_final(pred: dict[str, Any]) -> None:
    if pred.get("final_action") != "WAIT":
        raise ShadowLoopError("HARD FAILURE: production final_action must remain WAIT under NO_MODEL")
    if pred.get("champion_status") != CHAMPION_STATUS:
        raise ShadowLoopError("HARD FAILURE: champion status mismatch")


def process_bar(
    *,
    store: Phase16aShadowStore,
    bar: dict[str, Any],
    closes_prefix: list[float],
    h1_rows: list[dict],
    as_of: str,
    prev_open: str | None,
    discord_enabled: bool,
    dry_run_discord: bool,
    ledger: DeliveryLedger,
    transport=None,
) -> dict[str, Any]:
    """Journal first, then optionally notify Discord. Discord failure isolated."""
    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    quality = "gap" if g == "gap" else "ok"
    pred = predict_h13c_experimental(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    _ensure_wait_final(pred)

    obs_id = f"p17_obs_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
    dec_id = f"p17_dec_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
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
        "tick_volume": bar.get("tick_volume", 0),
        "spread": bar.get("spread", 0.0),
        "data_source": bar.get("data_source", "synthetic"),
        "data_quality_status": quality,
        "gap_status": g,
        "model_status": CHAMPION_STATUS,
        "feature_snapshot_reference": dec_id,
        "source_timezone": bar.get("source_timezone", "UTC"),
        "conversion": bar.get("conversion", "already_utc"),
        "source_stamp": bar.get("source_stamp", bar["bar_open_timestamp_utc"]),
        "decision_id": dec_id,
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
        "market_regime": pred.get("market_regime", ""),
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
        "feature_snapshot_json": pred.get("feature_snapshot_json", "{}"),
        "outcome_status": "n_a_wait" if pred["experimental_action"] == "WAIT" else "pending",
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": "phase17 shadow; journal-before-discord; production WAIT",
    }
    store.append_decision(dec)
    journaled = True

    delivery = {
        "status": "SKIPPED_DISABLED",
        "changed_decision": False,
        "journaled_before_discord": True,
    }
    if discord_enabled:
        event = {
            "event_id": dec_id,
            "decision_id": dec_id,
            "message_type": f"SHADOW_{pred['experimental_action']}",
        }
        try:
            if ledger.already_sent(event):
                delivery = {
                    "status": "SKIPPED_DUPLICATE",
                    "changed_decision": False,
                    "journaled_before_discord": True,
                }
            else:
                payload = build_shadow_payload(dec, obs)
                if dry_run_discord or not webhook_configured():
                    delivery = {
                        "status": "DRY_RUN" if dry_run_discord else "FAILED_CONFIG",
                        "changed_decision": False,
                        "journaled_before_discord": True,
                        "http_status": None,
                    }
                    ledger.record(event, delivery)
                else:
                    url = load_webhook_url()
                    assert url is not None
                    result = post_webhook(url, payload, transport=transport)
                    result["changed_decision"] = False
                    result["journaled_before_discord"] = True
                    if result.get("error"):
                        result["error"] = redact_secrets(str(result["error"]))
                    ledger.record(event, result)
                    delivery = result
        except Exception as exc:
            delivery = {
                "status": "FAILED_ISOLATED",
                "error": redact_secrets(type(exc).__name__),
                "changed_decision": False,
                "journaled_before_discord": True,
            }
            # Decision remains journaled; Discord failure isolated.

    return {
        "observation_id": obs_id,
        "decision_id": dec_id,
        "experimental_action": pred["experimental_action"],
        "final_action": pred["final_action"],
        "journaled": journaled,
        "delivery": delivery,
        "gap_status": g,
    }


def run_bounded_shadow_loop(
    *,
    max_candles: int = DEFAULT_MAX_CANDLES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    enable_discord: bool = DEFAULT_ENABLE_DISCORD,
    dry_run_discord: bool = True,
    store_root=None,
    bar_source: BarSource | None = None,
    terminal_path: str | None = None,
    transport=None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Process up to max_candles newly completed M5 bars. Does not invent candles."""
    if max_candles <= 0:
        raise ShadowLoopError("max_candles must be positive")

    store = Phase16aShadowStore(store_root or DATA_DIR)
    ledger = DeliveryLedger(DATA_DIR / "discord_delivery_ledger.jsonl")
    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase17_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    if store.has_lock():
        raise ShadowLoopError("session lock already present; refusing start")
    store.write_lock(session_id, "shadow_discord_bounded", started)
    store.append_session(
        {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": started,
            "stopped_at_utc": "",
            "mode": "shadow_discord_bounded",
            "mt5_connected": bar_source is None,
            "error": "",
            "notes": f"max_candles={max_candles}; dry_run_discord={dry_run_discord}",
        }
    )

    handle = None
    ts_mode = None
    processed = []
    counts = {"BUY": 0, "SELL": 0, "WAIT": 0}
    errors: list[str] = []
    last_open = store.last_open_utc()
    mt5_started = False

    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            path = terminal_path or MT5_TERMINAL_PATH
            conn = open_readonly(path)
            if conn.get("status") != "connected_readonly":
                raise ShadowLoopError(f"mt5 unavailable: {conn.get('reason') or conn.get('status')}")
            handle = conn["handle"]
            mt5_started = True
            ts_mode = detect_timestamp_mode(handle, as_of_utc=now_utc_stamp())

            def live_source() -> tuple[list[dict], list[dict], str]:
                as_of = now_utc_stamp()
                m5 = fetch_completed_m5(handle, count=300, as_of_utc=as_of, ts_mode=ts_mode)
                h1 = fetch_completed_h1(handle, count=300, as_of_utc=as_of, ts_mode=ts_mode)
                return m5, h1, as_of

            source = live_source
        else:
            source = bar_source

        while len(processed) < max_candles:
            if stop_flag and stop_flag():
                break
            m5_bars, h1_bars, as_of = source()
            m5_sorted = sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"])
            if h1_bars and "bar_open_timestamp_utc" in h1_bars[0]:
                h1_rows = h1_rows_for_trend(h1_bars)
            else:
                h1_rows = list(h1_bars)

            new_bars = [
                b
                for b in m5_sorted
                if last_open is None or b["bar_open_timestamp_utc"] > last_open
            ]
            # Avoid bulk historical backfill on first poll: take oldest pending up to remaining quota
            # but only newly completed after last_open. If first start with empty store, take latest N only.
            if last_open is None and new_bars:
                new_bars = new_bars[-max_candles:]

            closes = [float(b["close"]) for b in m5_sorted]
            open_to_idx = {b["bar_open_timestamp_utc"]: i for i, b in enumerate(m5_sorted)}
            prev = last_open
            made_progress = False
            for bar in new_bars:
                if len(processed) >= max_candles:
                    break
                try:
                    idx = open_to_idx[bar["bar_open_timestamp_utc"]]
                    result = process_bar(
                        store=store,
                        bar=bar,
                        closes_prefix=closes[: idx + 1],
                        h1_rows=h1_rows,
                        as_of=as_of,
                        prev_open=prev,
                        discord_enabled=enable_discord,
                        dry_run_discord=dry_run_discord,
                        ledger=ledger,
                        transport=transport,
                    )
                    processed.append(result)
                    counts[result["experimental_action"]] = counts.get(result["experimental_action"], 0) + 1
                    last_open = bar["bar_open_timestamp_utc"]
                    prev = last_open
                    made_progress = True
                except Exception as exc:
                    errors.append(redact_secrets(f"{bar.get('bar_open_timestamp_utc')}: {exc}"))
            if not made_progress:
                # Offline synthetic sources typically exhaust immediately.
                if bar_source is not None:
                    break
                time.sleep(max(1, int(poll_interval_seconds)))
    finally:
        if handle is not None:
            close_readonly(handle)
        stopped = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        store.clear_lock()
        store.append_session(
            {
                "session_id": session_id,
                "status": "stopped",
                "started_at_utc": started,
                "stopped_at_utc": stopped,
                "mode": "shadow_discord_bounded",
                "mt5_connected": False,
                "error": "; ".join(errors[:20]),
                "notes": "graceful stop; lock cleared",
            }
        )

    return {
        "status": "completed",
        "session_id": session_id,
        "started_at_utc": started,
        "stopped_at_utc": stopped,
        "max_candles": max_candles,
        "candles_processed": len(processed),
        "prediction_counts": counts,
        "processed": processed,
        "errors": errors,
        "lock_remaining": store.has_lock(),
        "mt5_session_started": mt5_started,
        "discord_enabled": enable_discord,
        "dry_run_discord": dry_run_discord,
        "broker_orders": 0,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "any_final_non_wait": any(p["final_action"] != "WAIT" for p in processed),
    }
