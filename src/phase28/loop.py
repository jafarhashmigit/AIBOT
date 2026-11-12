"""Bounded forward shadow loop for dual Phase 28 observers (no Discord/Telegram)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
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
from phase18.experience import ExperienceStore
from phase18.outcomes import atr_at_signal
from phase20.candles import enrich_observation_timestamps, filter_completed_bars, is_complete_m5_bar
from phase28.campaign import CampaignStore, evidence_status
from phase28.constants import (
    DATA_DIR,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_SESSION_MAX_CANDLES,
    OBSERVER_BASELINE,
    OBSERVER_HIGH_VOL,
    PRODUCTION_FINAL_ACTION,
)
from phase28.frozen_vol import load_frozen_vol_artifact
from phase28.integrity import assert_no_side_channels, verify_frozen_vol_ready
from phase28.journals import ObserverJournal, OutcomeStore
from phase28.live_features import predict_vol_at_bar
from phase28.observers import build_baseline_record, build_high_vol_record, run_h13c_prediction
from phase28.outcomes import resolve_observer_outcomes, summarize_outcomes

UTC = timezone.utc
BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class Phase28LoopError(RuntimeError):
    pass


def _observer_root(root: Path, observer_id: str) -> Path:
    return Path(root) / "observers" / observer_id


def process_candle(
    *,
    root: Path,
    bar: dict[str, Any],
    all_m5: list[dict],
    h1_bars: list[dict],
    closes_prefix: list[float],
    as_of: str,
    prev_open: str | None,
    campaign_id: str,
    session_id: str,
    vol_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    """Process one completed candle into both observer journals (idempotent)."""
    assert_no_side_channels()
    if not is_complete_m5_bar(bar, as_of_utc=as_of):
        raise Phase28LoopError("incomplete candle rejected")

    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    ts = enrich_observation_timestamps(bar)
    h1_rows = h1_rows_for_trend(h1_bars)
    pred = run_h13c_prediction(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    if pred.get("final_action") != PRODUCTION_FINAL_ACTION:
        raise Phase28LoopError("production final_action must remain WAIT")

    if vol_artifact is None:
        vol = {"ok": False, "reason": "frozen_vol_artifact_missing"}
    else:
        vol = predict_vol_at_bar(
            m5_bars=all_m5,
            h1_bars=h1_bars,
            decision_close_utc=bar["bar_close_timestamp_utc"],
            artifact=vol_artifact,
        )

    baseline = build_baseline_record(
        bar=bar,
        pred=pred,
        gap_status=g,
        campaign_id=campaign_id,
        session_id=session_id,
    )
    high = build_high_vol_record(
        bar=bar,
        pred=pred,
        vol=vol,
        gap_status=g,
        campaign_id=campaign_id,
        session_id=session_id,
    )

    results = {}
    for rec, oid in ((baseline, OBSERVER_BASELINE), (high, OBSERVER_HIGH_VOL)):
        j = ObserverJournal(_observer_root(root, oid), oid)
        wrote = j.append(rec)
        results[oid] = {
            "written": wrote,
            "duplicate": not wrote,
            "decision_id": rec["decision_id"],
            "experimental_action": rec["experimental_action"],
            "accepted": rec["accepted"],
            "reason_code": rec["reason_code"],
            "pred_vol_regime": rec.get("pred_vol_regime"),
        }

    # Seed pending outcomes for newly written accepted decisions.
    atr_val = None
    try:
        opens = [b["bar_open_timestamp_utc"] for b in all_m5]
        signal_pos = opens.index(bar["bar_open_timestamp_utc"])
        atr_val = atr_at_signal(all_m5, signal_pos)
    except Exception:
        atr_val = None

    from phase28.outcomes import pending_from_decision

    for rec, oid in ((baseline, OBSERVER_BASELINE), (high, OBSERVER_HIGH_VOL)):
        if not results[oid]["written"]:
            continue
        ostore = OutcomeStore(_observer_root(root, oid), oid)
        for row in pending_from_decision(rec, atr=atr_val):
            ostore.append(row)

    return {
        "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
        "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
        "gap_status": g,
        "timestamps": ts,
        "h13c_experimental_action": pred["experimental_action"],
        "final_action": pred["final_action"],
        "observers": results,
        "vol": {
            "ok": vol.get("ok"),
            "pred_vol_regime": vol.get("pred_vol_regime"),
            "pred_fwd_vol_12": vol.get("pred_fwd_vol_12"),
            "reason": vol.get("reason"),
        },
    }


def resolve_all_observers(*, root: Path, bars: list[dict], as_of: str) -> dict[str, Any]:
    out = {}
    for oid in (OBSERVER_BASELINE, OBSERVER_HIGH_VOL):
        oroot = _observer_root(root, oid)
        decisions = ObserverJournal(oroot, oid).read_all()
        ostore = OutcomeStore(oroot, oid)
        exp = ExperienceStore(oroot)
        # Guard: never write into historical hypothetical from forward path.
        hist_before = exp.historical_path.read_text(encoding="utf-8") if exp.historical_path.exists() else ""
        stats = resolve_observer_outcomes(
            decisions=decisions,
            outcome_store=ostore,
            experience=exp,
            bars=bars,
            as_of=as_of,
        )
        hist_after = exp.historical_path.read_text(encoding="utf-8") if exp.historical_path.exists() else ""
        if hist_after != hist_before:
            raise Phase28LoopError("HARD FAILURE: historical hypothetical store mutated by forward path")
        out[oid] = {
            **stats,
            "outcome_summary": summarize_outcomes(ostore.read_all()),
            "n_decisions": len(decisions),
            "n_accepted": sum(1 for d in decisions if d.get("accepted")),
            "n_buy_sell_h13c": sum(
                1 for d in decisions if str(d.get("h13c_experimental_action", "")).upper() in {"BUY", "SELL"}
            ),
        }
    return out


def run_bounded_live_shadow(
    *,
    max_candles: int = DEFAULT_SESSION_MAX_CANDLES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    store_root: Path | None = None,
    bar_source: BarSource | None = None,
    terminal_path: str | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Explicit live-shadow mode only. Default readiness path must not call this."""
    if max_candles <= 0:
        raise Phase28LoopError("max_candles must be positive")
    if max_candles > 100:
        raise Phase28LoopError("Phase 28 session batch capped at 100 new candles")

    root = Path(store_root) if store_root is not None else DATA_DIR
    root.mkdir(parents=True, exist_ok=True)
    campaign = CampaignStore(root)
    state = campaign.load()
    campaign_id = state["campaign_id"]
    processed = set(state.get("processed_keys") or [])

    vol_ready = verify_frozen_vol_ready()
    vol_artifact = None
    high_vol_blocker = None
    if vol_ready.get("ok"):
        vol_artifact = load_frozen_vol_artifact()
    else:
        high_vol_blocker = vol_ready.get("blocker") or "FROZEN_VOL_NOT_READY"

    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase28_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    # Forward-only watermark: never treat MT5 history buffer as forward observations.
    # Real MT5: freeze start on first live session. Injected bar_source (tests): allow all unless set.
    if bar_source is None and not state.get("forward_observation_start_utc"):
        state["forward_observation_start_utc"] = started
        campaign.save(state)
    forward_start = state.get("forward_observation_start_utc")

    handle = None
    mt5_started = False
    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            path = terminal_path or MT5_TERMINAL_PATH
            conn = open_readonly(path)
            if conn.get("status") != "connected_readonly":
                raise Phase28LoopError(f"MT5 readonly connect failed: {conn}")
            handle = conn["handle"]
            mt5_started = True
            # Enforce allowlist: only read APIs used via mt5_reader helpers.

        new_count = 0
        batch_results = []
        last_bars: list[dict] = []
        as_of = started
        skipped_pre_start = 0
        import time

        while new_count < max_candles:
            if stop_flag and stop_flag():
                break
            if bar_source is not None:
                m5, h1, as_of = bar_source()
            else:
                assert handle is not None
                as_of = now_utc_stamp()
                ts_mode = detect_timestamp_mode(handle, as_of_utc=as_of)
                m5 = fetch_completed_m5(handle, as_of_utc=as_of, count=500, ts_mode=ts_mode)
                h1 = fetch_completed_h1(handle, as_of_utc=as_of, count=300, ts_mode=ts_mode)
            m5 = filter_completed_bars(m5, as_of_utc=as_of)
            m5 = sorted(m5, key=lambda b: b["bar_open_timestamp_utc"])
            last_bars = m5
            # Reject out-of-order / duplicates via processed_keys + open time ordering.
            prev_open = None
            progressed = False
            for i, bar in enumerate(m5):
                key = bar["bar_open_timestamp_utc"]
                if prev_open is not None and key < prev_open:
                    raise Phase28LoopError("out-of-order candle open timestamp in feed")
                if prev_open is not None and key == prev_open:
                    raise Phase28LoopError("duplicate candle open timestamp in feed")
                # Only process candles not yet journaled (restart-safe).
                if key in processed:
                    prev_open = key
                    continue
                # Never replay candles that closed at/before forward observation start.
                if forward_start and bar["bar_close_timestamp_utc"] <= forward_start:
                    skipped_pre_start += 1
                    prev_open = key
                    continue
                # Genuinely new completed candle after forward start
                closes_prefix = [float(b["close"]) for b in m5[: i + 1]]
                result = process_candle(
                    root=root,
                    bar=bar,
                    all_m5=m5[: i + 1],
                    h1_bars=h1,
                    closes_prefix=closes_prefix,
                    as_of=as_of,
                    prev_open=prev_open,
                    campaign_id=campaign_id,
                    session_id=session_id,
                    vol_artifact=vol_artifact,
                )
                processed.add(key)
                state["processed_keys"] = sorted(processed)[-5000:]
                state["new_candles_processed"] = int(state.get("new_candles_processed") or 0) + 1
                state["last_candle_close_utc"] = bar["bar_close_timestamp_utc"]
                new_count += 1
                batch_results.append(result)
                progressed = True
                prev_open = key
                if new_count >= max_candles:
                    break
            if not progressed:
                if bar_source is not None:
                    break
                time.sleep(max(1, int(poll_interval_seconds)))
            else:
                # Resolve outcomes after each progress step.
                resolve_all_observers(root=root, bars=last_bars, as_of=as_of)
                campaign.save(state)
                if bar_source is not None and new_count >= max_candles:
                    break
                if bar_source is not None:
                    break

        resolve_stats = resolve_all_observers(root=root, bars=last_bars, as_of=as_of) if last_bars else {}
        state.setdefault("batches", []).append(
            {
                "session_id": session_id,
                "new_candles": new_count,
                "ended_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "high_vol_blocker": high_vol_blocker,
                "forward_observation_start_utc": forward_start,
                "skipped_pre_start_candles": skipped_pre_start,
            }
        )
        campaign.save(state)

        return {
            "session_id": session_id,
            "mt5_session_started": mt5_started,
            "mt5_readonly": True,
            "discord_enabled": False,
            "telegram_enabled": False,
            "broker_orders": 0,
            "new_candles_processed": new_count,
            "forward_observation_start_utc": forward_start,
            "skipped_pre_start_candles": skipped_pre_start,
            "campaign_state": state,
            "batch_results": batch_results,
            "resolve_stats": resolve_stats,
            "high_vol_blocker": high_vol_blocker,
            "evidence": evidence_status(n_candles=int(state.get("new_candles_processed") or 0)),
            "production_final_action": PRODUCTION_FINAL_ACTION,
        }
    finally:
        if handle is not None:
            close_readonly(handle)
