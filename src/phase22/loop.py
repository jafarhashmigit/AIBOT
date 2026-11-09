"""Bounded resumable Phase 22 forward shadow sessions."""

from __future__ import annotations

import time
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
from phase16a.predictor import predict_h13c_experimental
from phase16b.client import post_webhook
from phase16b.dedupe import DeliveryLedger
from phase16b.secrets import load_webhook_url, redact_secrets, webhook_configured
from phase18.experience import ExperienceStore
from phase18.outcomes import atr_at_signal, create_pending_outcomes
from phase18.store import Phase18Store
from phase20.candles import enrich_observation_timestamps, filter_completed_bars, is_complete_m5_bar
from phase20.loop import resolve_pending_outcomes
from phase20.messages import build_shadow_signal_payload
from phase22.campaign import CampaignStore
from phase22.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CAMPAIGN_TARGET_CANDLES,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_SESSION_MAX_CANDLES,
    PHASE18_DATA,
    PHASE19_SYNTHETIC,
    PHASE20_DATA,
    SELECTED_HORIZON_DISPLAY,
    SOURCE_TYPE,
    STRATEGY_ID,
    SYMBOL,
    TIMEFRAME,
)
from phase22.diagnostics import DiagnosticJournal, build_condition_diagnostics

UTC = timezone.utc
BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class Phase22LoopError(RuntimeError):
    pass


def _ensure_wait_final(pred: dict[str, Any]) -> None:
    if pred.get("final_action") != "WAIT":
        raise Phase22LoopError("HARD FAILURE: production final_action must remain WAIT under NO_MODEL")
    if pred.get("champion_status") != CHAMPION_STATUS:
        raise Phase22LoopError("HARD FAILURE: champion status mismatch")


def _assert_isolated_root(root: Path) -> None:
    resolved = Path(root).resolve()
    for banned in (PHASE20_DATA, PHASE19_SYNTHETIC, PHASE18_DATA):
        try:
            resolved.relative_to(banned.resolve())
            raise Phase22LoopError(f"refusing write into protected store {banned}")
        except ValueError:
            pass


def _deliver(
    *,
    ledger: DeliveryLedger,
    event: dict[str, Any],
    payload: dict[str, str],
    dry_run_discord: bool,
    discord_enabled: bool,
    transport=None,
) -> dict[str, Any]:
    if not discord_enabled:
        return {"status": "SKIPPED_DISABLED", "journaled_before_discord": True}
    if ledger.already_sent(event):
        return {"status": "SKIPPED_DUPLICATE", "journaled_before_discord": True}
    if dry_run_discord or not webhook_configured():
        delivery = {
            "status": "DRY_RUN" if dry_run_discord else "FAILED_CONFIG",
            "journaled_before_discord": True,
            "http_status": None,
        }
        ledger.record(event, delivery)
        return delivery
    url = load_webhook_url()
    assert url is not None
    result = post_webhook(url, payload, transport=transport)
    result["journaled_before_discord"] = True
    if result.get("error"):
        result["error"] = redact_secrets(str(result["error"]))
    ledger.record(event, result)
    return result


def process_bar(
    *,
    store: Phase18Store,
    experience: ExperienceStore,
    bar: dict[str, Any],
    closes_prefix: list[float],
    h1_rows: list[dict],
    all_bars: list[dict],
    as_of: str,
    prev_open: str | None,
    discord_enabled: bool,
    dry_run_discord: bool,
    ledger: DeliveryLedger,
    diagnostics: DiagnosticJournal,
    campaign_id: str,
    session_id: str,
    transport=None,
) -> dict[str, Any]:
    if not is_complete_m5_bar(bar, as_of_utc=as_of):
        raise Phase22LoopError("incomplete candle rejected")

    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    quality = "gap" if g == "gap" else "ok"
    pred = predict_h13c_experimental(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    _ensure_wait_final(pred)
    cond = build_condition_diagnostics(pred)
    ts = enrich_observation_timestamps(bar)

    obs_id = f"p22_obs_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
    dec_id = f"p22_dec_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"

    atr_val = ""
    try:
        opens = [b["bar_open_timestamp_utc"] for b in all_bars]
        signal_pos = opens.index(bar["bar_open_timestamp_utc"])
        atr = atr_at_signal(all_bars, signal_pos)
        atr_val = f"{atr:.8f}"
    except Exception:
        atr = None

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
        "data_source": bar.get("data_source", "mt5_readonly"),
        "data_quality_status": quality,
        "gap_status": g,
        "model_status": CHAMPION_STATUS,
        "decision_id": dec_id,
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
    }
    newly_obs = store.append_observation(obs)
    if not newly_obs:
        return {
            "observation_id": obs_id,
            "decision_id": dec_id,
            "experimental_action": "DUPLICATE_SKIPPED",
            "final_action": "WAIT",
            "journaled": False,
            "duplicate": True,
            "delivery": {"status": "SKIPPED_DUPLICATE_CANDLE"},
            "pending_outcomes": 0,
            "diagnostics": cond,
        }

    exp_action = pred["experimental_action"]
    completed_at_decision = sum(
        1 for o in store.outcomes() if str(o.get("status")).upper() in {"PASS", "FAIL", "TIMEOUT"}
    )
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
        "experimental_action": exp_action,
        "raw_action": pred["raw_action"],
        "risk_gate_result": pred["gate"]["gate_status"],
        "final_action": pred["final_action"],
        "decision_reason": pred["experimental_reason"],
        "feature_snapshot_json": pred.get("feature_snapshot_json", "{}"),
        "selected_horizon": SELECTED_HORIZON_DISPLAY,
        "outcome_status": "n_a_wait" if exp_action == "WAIT" else "pending_multi_horizon",
        "signal_bar_open_utc": bar["bar_open_timestamp_utc"],
        "atr": atr_val,
        "tp_level": "",
        "sl_level": "",
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": f"phase22 campaign={campaign_id}; production WAIT; strategy={STRATEGY_ID}",
    }
    newly_dec = store.append_decision(dec)
    pending = create_pending_outcomes(dec, atr=float(atr_val) if atr_val else None)
    store.append_outcomes(pending)

    delivery = {"status": "SKIPPED_WAIT_NO_DISCORD", "journaled_before_discord": True}
    if newly_dec and exp_action in {"BUY", "SELL"} and discord_enabled:
        event = {
            "event_id": dec_id,
            "decision_id": dec_id,
            "message_type": f"SHADOW_SIGNAL_{exp_action}",
        }
        try:
            payload = build_shadow_signal_payload(dec, obs)
            delivery = _deliver(
                ledger=ledger,
                event=event,
                payload=payload,
                dry_run_discord=dry_run_discord,
                discord_enabled=discord_enabled,
                transport=transport,
            )
        except Exception as exc:
            delivery = {
                "status": "FAILED_ISOLATED",
                "error": redact_secrets(type(exc).__name__),
                "journaled_before_discord": True,
            }

    diagnostics.append(
        {
            "decision_id": dec_id,
            "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
            "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
            "candle_timestamp_pkt": ts.get("candle_timestamp_pkt", ""),
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            **cond,
            "experimental_action": exp_action,
            "wait_reason": pred["experimental_reason"],
            "final_action": pred["final_action"],
            "data_quality_status": quality,
            "pending_outcomes": len(pending),
            "completed_outcomes_at_decision": completed_at_decision,
            "campaign_id": campaign_id,
            "session_id": session_id,
        }
    )

    return {
        "observation_id": obs_id,
        "decision_id": dec_id,
        "experimental_action": exp_action,
        "final_action": pred["final_action"],
        "journaled": newly_dec,
        "duplicate": False,
        "pending_outcomes": len(pending),
        "delivery": delivery,
        "gap_status": g,
        "diagnostics": cond,
        "wait_reason": pred["experimental_reason"],
        "timestamps": ts,
    }


def run_bounded_campaign_session(
    *,
    max_candles: int = DEFAULT_SESSION_MAX_CANDLES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    enable_discord: bool = True,
    dry_run_discord: bool = True,
    store_root=None,
    bar_source: BarSource | None = None,
    terminal_path: str | None = None,
    transport=None,
    stop_flag: Callable[[], bool] | None = None,
    campaign_target: int = CAMPAIGN_TARGET_CANDLES,
) -> dict[str, Any]:
    if max_candles <= 0:
        raise Phase22LoopError("max_candles must be positive")

    root = Path(store_root) if store_root is not None else DATA_DIR
    _assert_isolated_root(root)
    campaign = CampaignStore(root)
    state = campaign.get_or_create(target=campaign_target)
    campaign_id = state["campaign_id"]

    # Cap session by remaining campaign quota
    remaining = int(state.get("remaining_candles", campaign_target))
    if remaining <= 0:
        return {
            "status": "campaign_target_already_reached",
            "campaign_id": campaign_id,
            "candles_processed": 0,
            "mt5_session_started": False,
            "prediction_counts": {"BUY": 0, "SELL": 0, "WAIT": 0},
            "broker_orders": 0,
            "champion_status": CHAMPION_STATUS,
            "candidate_status": CANDIDATE_STATUS,
            "note": "Campaign target already reached; no MT5 session started.",
        }
    max_candles = min(int(max_candles), remaining)

    store = Phase18Store(root)
    experience = ExperienceStore(root)
    ledger = DeliveryLedger(root / "discord_delivery_ledger.jsonl")
    diagnostics = DiagnosticJournal(root)
    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase22_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    if store.has_lock():
        raise Phase22LoopError("session lock already present; refusing start")
    store.write_lock(session_id, "forward_campaign_bounded", started)
    store.append_session(
        {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": started,
            "stopped_at_utc": "",
            "mode": "forward_campaign_bounded",
            "mt5_connected": bar_source is None,
            "error": "",
            "notes": f"campaign={campaign_id}; max_candles={max_candles}; dry_run={dry_run_discord}",
        }
    )

    handle = None
    ts_mode = None
    processed = []
    counts = {"BUY": 0, "SELL": 0, "WAIT": 0}
    errors: list[str] = []
    rejected_incomplete = 0
    rejected_duplicate = 0
    # Resume from campaign last OR store last — use the later of the two
    last_open = store.last_open_utc() or (state.get("last_bar_open_utc") or None) or None
    if state.get("last_bar_open_utc") and last_open:
        last_open = max(last_open, state["last_bar_open_utc"])
    elif state.get("last_bar_open_utc"):
        last_open = state["last_bar_open_utc"]
    mt5_started = False
    outcome_stats = {"finalized": [], "experience_added": 0}
    stopped = started

    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            path = terminal_path or MT5_TERMINAL_PATH
            conn = open_readonly(path)
            if conn.get("status") != "connected_readonly":
                raise Phase22LoopError(f"mt5 unavailable: {conn.get('reason') or conn.get('status')}")
            handle = conn["handle"]
            mt5_started = True
            ts_mode = detect_timestamp_mode(handle, as_of_utc=now_utc_stamp())

            def live_source() -> tuple[list[dict], list[dict], str]:
                as_of = now_utc_stamp()
                m5 = fetch_completed_m5(handle, count=400, as_of_utc=as_of, ts_mode=ts_mode)
                h1 = fetch_completed_h1(handle, count=400, as_of_utc=as_of, ts_mode=ts_mode)
                return m5, h1, as_of

            source = live_source
        else:
            source = bar_source

        m5_bars, h1_bars, as_of = source()
        m5_sorted = filter_completed_bars(
            sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"]), as_of_utc=as_of
        )
        store.cache_bars(m5_sorted)
        recovery = resolve_pending_outcomes(
            store=store,
            experience=experience,
            bars=store.load_cached_bars() or m5_sorted,
            as_of=as_of,
            discord_enabled=enable_discord,
            dry_run_discord=dry_run_discord,
            ledger=ledger,
            transport=transport,
        )
        outcome_stats["finalized"].extend(recovery.get("finalized", []))
        outcome_stats["experience_added"] += int(recovery.get("experience_added", 0))

        while len(processed) < max_candles:
            if stop_flag and stop_flag():
                break
            m5_bars, h1_bars, as_of = source()
            m5_sorted = filter_completed_bars(
                sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"]), as_of_utc=as_of
            )
            store.cache_bars(m5_sorted)
            if h1_bars and h1_bars and "bar_open_timestamp_utc" in h1_bars[0]:
                h1_rows = h1_rows_for_trend(h1_bars)
            else:
                h1_rows = list(h1_bars)

            new_bars = [
                b for b in m5_sorted if last_open is None or b["bar_open_timestamp_utc"] > last_open
            ]
            # First campaign session with empty store: do not backfill hundreds of history —
            # take only newest up to max_candles (same pattern as phase20).
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
                    if not is_complete_m5_bar(bar, as_of_utc=as_of):
                        rejected_incomplete += 1
                        continue
                    idx = open_to_idx[bar["bar_open_timestamp_utc"]]
                    result = process_bar(
                        store=store,
                        experience=experience,
                        bar=bar,
                        closes_prefix=closes[: idx + 1],
                        h1_rows=h1_rows,
                        all_bars=m5_sorted,
                        as_of=as_of,
                        prev_open=prev,
                        discord_enabled=enable_discord,
                        dry_run_discord=dry_run_discord,
                        ledger=ledger,
                        diagnostics=diagnostics,
                        campaign_id=campaign_id,
                        session_id=session_id,
                        transport=transport,
                    )
                    if result.get("duplicate"):
                        rejected_duplicate += 1
                        last_open = bar["bar_open_timestamp_utc"]
                        prev = last_open
                        continue
                    processed.append(result)
                    action = result["experimental_action"]
                    if action in counts:
                        counts[action] += 1
                    last_open = bar["bar_open_timestamp_utc"]
                    prev = last_open
                    made_progress = True
                except Phase22LoopError as exc:
                    if "incomplete" in str(exc).lower():
                        rejected_incomplete += 1
                    else:
                        errors.append(redact_secrets(str(exc)))
                except Exception as exc:
                    errors.append(redact_secrets(f"{bar.get('bar_open_timestamp_utc')}: {exc}"))

            resolved = resolve_pending_outcomes(
                store=store,
                experience=experience,
                bars=m5_sorted,
                as_of=as_of,
                discord_enabled=enable_discord,
                dry_run_discord=dry_run_discord,
                ledger=ledger,
                transport=transport,
            )
            outcome_stats["finalized"].extend(resolved.get("finalized", []))
            outcome_stats["experience_added"] += int(resolved.get("experience_added", 0))

            if not made_progress:
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
                "mode": "forward_campaign_bounded",
                "mt5_connected": False,
                "error": "; ".join(errors[:20]),
                "notes": "graceful stop; lock cleared",
            }
        )

    discord_sent = sum(
        1
        for p in processed
        if (p.get("delivery") or {}).get("status") == "SENT"
        and p.get("experimental_action") in {"BUY", "SELL"}
    )
    campaign_state = campaign.record_session(
        session_id=session_id,
        candles=len(processed),
        buy=counts["BUY"],
        sell=counts["SELL"],
        wait=counts["WAIT"],
        last_bar_open_utc=last_open or "",
        discord_sent=discord_sent,
        rejected_incomplete=rejected_incomplete,
        rejected_duplicate=rejected_duplicate,
        started_at_utc=started,
        stopped_at_utc=stopped,
    )

    outcome_counts = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0}
    for o in store.outcomes():
        st = str(o.get("status", "PENDING")).upper()
        if st in outcome_counts:
            outcome_counts[st] += 1

    return {
        "status": "completed",
        "campaign_id": campaign_id,
        "session_id": session_id,
        "started_at_utc": started,
        "stopped_at_utc": stopped,
        "max_candles": max_candles,
        "candles_processed": len(processed),
        "prediction_counts": counts,
        "processed": processed,
        "errors": errors,
        "rejected_incomplete": rejected_incomplete,
        "rejected_duplicate": rejected_duplicate,
        "lock_remaining": store.has_lock(),
        "mt5_session_started": mt5_started,
        "discord_enabled": enable_discord,
        "dry_run_discord": dry_run_discord,
        "discord_signals_sent": discord_sent,
        "broker_orders": 0,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "selected_horizon_policy": SELECTED_HORIZON_DISPLAY,
        "any_final_non_wait": any(p["final_action"] != "WAIT" for p in processed),
        "outcomes": outcome_counts,
        "pending_outcomes": outcome_counts.get("PENDING", 0),
        "completed_outcomes": sum(outcome_counts[k] for k in ("PASS", "FAIL", "TIMEOUT")),
        "shadow_experience_added": outcome_stats.get("experience_added", 0),
        "experience_counts": experience.counts(),
        "campaign_state": {
            "observed_candles": campaign_state.get("observed_candles"),
            "remaining_candles": campaign_state.get("remaining_candles"),
            "target_candles": campaign_state.get("target_candles"),
            "status": campaign_state.get("status"),
            "sessions": len(campaign_state.get("sessions") or []),
        },
        "phase20_data_untouched": True,
        "phase19_synthetic_excluded": True,
        "note": "Forward shadow observation infrastructure only — no trading edge claimed.",
    }
