"""Bounded multi-horizon shadow loop: observe → predict → journal → Discord → outcomes."""

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
from phase18.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_ENABLE_DISCORD,
    DEFAULT_MAX_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    SELECTED_HORIZON_DISPLAY,
    SOURCE_TYPE,
    STRATEGY_ID,
    SYMBOL,
    TIMEFRAME,
)
from phase18.daily_report import build_daily_discord_bundle, current_pkt_date
from phase18.experience import ExperienceStore
from phase18.messages import build_outcome_payload, build_signal_payload
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome
from phase18.store import DAILY_FIELDS, Phase18Store

UTC = timezone.utc
BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class Phase18LoopError(RuntimeError):
    pass


def _ensure_wait_final(pred: dict[str, Any]) -> None:
    if pred.get("final_action") != "WAIT":
        raise Phase18LoopError("HARD FAILURE: production final_action must remain WAIT under NO_MODEL")
    if pred.get("champion_status") != CHAMPION_STATUS:
        raise Phase18LoopError("HARD FAILURE: champion status mismatch")


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
    transport=None,
) -> dict[str, Any]:
    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    quality = "gap" if g == "gap" else "ok"
    pred = predict_h13c_experimental(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    _ensure_wait_final(pred)

    obs_id = f"p18_obs_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
    dec_id = f"p18_dec_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"

    atr_val = ""
    tp_level = ""
    sl_level = ""
    try:
        opens = [b["bar_open_timestamp_utc"] for b in all_bars]
        signal_pos = opens.index(bar["bar_open_timestamp_utc"])
        atr = atr_at_signal(all_bars, signal_pos)
        atr_val = f"{atr:.8f}"
        # Preview TP/SL levels using H12 path if enough bars; else ATR-only estimate after entry open unknown
        # Levels relative to entry are finalized at outcome; store ATR for messaging.
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
        "data_source": bar.get("data_source", "synthetic"),
        "data_quality_status": quality,
        "gap_status": g,
        "model_status": CHAMPION_STATUS,
        "decision_id": dec_id,
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
    }
    store.append_observation(obs)

    exp_action = pred["experimental_action"]
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
        "tp_level": tp_level,
        "sl_level": sl_level,
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": "phase18 multi-horizon; journal-before-discord; production WAIT",
    }
    newly_journaled = store.append_decision(dec)

    pending = create_pending_outcomes(dec, atr=float(atr_val) if atr_val else None)
    store.append_outcomes(pending)

    delivery = {"status": "SKIPPED_DISABLED", "journaled_before_discord": True}
    if newly_journaled and discord_enabled:
        event = {
            "event_id": dec_id,
            "decision_id": dec_id,
            "message_type": f"SHADOW_SIGNAL_{exp_action}",
        }
        try:
            payload = build_signal_payload(dec, obs, pending_outcomes=pending)
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

    return {
        "observation_id": obs_id,
        "decision_id": dec_id,
        "experimental_action": exp_action,
        "final_action": pred["final_action"],
        "journaled": newly_journaled,
        "pending_outcomes": len(pending),
        "delivery": delivery,
        "gap_status": g,
        "selected_horizon": SELECTED_HORIZON_DISPLAY,
    }


def resolve_pending_outcomes(
    *,
    store: Phase18Store,
    experience: ExperienceStore,
    bars: list[dict],
    as_of: str,
    discord_enabled: bool,
    dry_run_discord: bool,
    ledger: DeliveryLedger,
    transport=None,
) -> dict[str, Any]:
    """Evaluate eligible pending horizons; send missing outcome Discord; write experience."""
    finalized = []
    notifications = []
    exp_added = 0
    sorted_bars = sorted(bars, key=lambda b: b["bar_open_timestamp_utc"])
    if not sorted_bars:
        return {"finalized": [], "notifications": [], "experience_added": 0}

    for pending in list(store.pending_outcomes()):
        dec = store.decision_by_id(pending["decision_id"])
        if not dec:
            continue
        signal_open = dec.get("signal_bar_open_utc")
        if not signal_open:
            continue
        try:
            opens = [b["bar_open_timestamp_utc"] for b in sorted_bars]
            signal_pos = opens.index(signal_open)
            atr = atr_at_signal(sorted_bars, signal_pos)
        except Exception:
            continue
        updated = evaluate_horizon_outcome(
            pending,
            bars=sorted_bars,
            signal_bar_open_utc=signal_open,
            atr=atr,
            as_of_utc=as_of,
        )
        if updated.get("status") == "PENDING":
            continue
        store.upsert_outcome(updated)
        finalized.append(updated)

        if str(updated.get("discord_notified", "0")) != "1":
            event = {
                "event_id": updated["outcome_event_id"],
                "decision_id": updated["decision_id"],
                "message_type": f"SHADOW_OUTCOME_{updated['horizon_id']}_{updated['status']}",
            }
            try:
                payload = build_outcome_payload(updated)
                delivery = _deliver(
                    ledger=ledger,
                    event=event,
                    payload=payload,
                    dry_run_discord=dry_run_discord,
                    discord_enabled=discord_enabled,
                    transport=transport,
                )
                if delivery.get("status") in {"SENT", "DRY_RUN", "SKIPPED_DUPLICATE"}:
                    updated["discord_notified"] = "1"
                    store.upsert_outcome(updated)
                notifications.append({"outcome_event_id": updated["outcome_event_id"], "delivery": delivery})
            except Exception as exc:
                notifications.append(
                    {
                        "outcome_event_id": updated["outcome_event_id"],
                        "delivery": {"status": "FAILED_ISOLATED", "error": redact_secrets(type(exc).__name__)},
                    }
                )

        if str(updated.get("experience_recorded", "0")) != "1":
            row = experience.add_shadow_from_outcome(
                updated,
                feature_context_ref=dec.get("decision_id", ""),
                selected_horizon=SELECTED_HORIZON_DISPLAY,
            )
            if row is not None:
                updated["experience_recorded"] = "1"
                store.upsert_outcome(updated)
                exp_added += 1

    return {"finalized": finalized, "notifications": notifications, "experience_added": exp_added}


def maybe_send_daily_report(
    *,
    store: Phase18Store,
    ledger: DeliveryLedger,
    as_of: str,
    discord_enabled: bool,
    dry_run_discord: bool,
    transport=None,
    force_date_pkt: str | None = None,
) -> dict[str, Any] | None:
    date_pkt = force_date_pkt or current_pkt_date()
    bundle = build_daily_discord_bundle(
        decisions=store.decisions(),
        outcomes=store.outcomes(),
        date_pkt=date_pkt,
        generated_at_utc=as_of,
    )
    record = bundle["record"]
    if not store.append_daily_report(record):
        return {"status": "SKIPPED_DUPLICATE", "report_id": record["report_id"]}
    event = {
        "event_id": record["report_id"],
        "decision_id": record["report_id"],
        "message_type": "DAILY_SHADOW_REPORT",
    }
    delivery = _deliver(
        ledger=ledger,
        event=event,
        payload=bundle["payload"],
        dry_run_discord=dry_run_discord,
        discord_enabled=discord_enabled,
        transport=transport,
    )
    # update status on daily row
    for row in store._daily:
        if row["report_id"] == record["report_id"]:
            row["discord_status"] = delivery.get("status", "")
    store._save(store.daily_path, store._daily, DAILY_FIELDS)
    return {"status": delivery.get("status"), "report_id": record["report_id"], "report": bundle["report"]}


def recover_on_startup(
    *,
    store: Phase18Store,
    experience: ExperienceStore,
    bars: list[dict],
    as_of: str,
    discord_enabled: bool,
    dry_run_discord: bool,
    ledger: DeliveryLedger,
    transport=None,
) -> dict[str, Any]:
    store.cache_bars(bars)
    return resolve_pending_outcomes(
        store=store,
        experience=experience,
        bars=store.load_cached_bars() or bars,
        as_of=as_of,
        discord_enabled=discord_enabled,
        dry_run_discord=dry_run_discord,
        ledger=ledger,
        transport=transport,
    )


def run_bounded_multihorizon_loop(
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
    send_daily_report: bool = False,
    daily_date_pkt: str | None = None,
) -> dict[str, Any]:
    if max_candles <= 0:
        raise Phase18LoopError("max_candles must be positive")

    root = store_root or DATA_DIR
    store = Phase18Store(root)
    experience = ExperienceStore(root)
    ledger = DeliveryLedger(Path(root) / "discord_delivery_ledger.jsonl")
    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase18_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    if store.has_lock():
        raise Phase18LoopError("session lock already present; refusing start")
    store.write_lock(session_id, "multihorizon_shadow_bounded", started)
    store.append_session(
        {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": started,
            "stopped_at_utc": "",
            "mode": "multihorizon_shadow_bounded",
            "mt5_connected": bar_source is None,
            "error": "",
            "notes": f"max_candles={max_candles}; dry_run_discord={dry_run_discord}; strategy={STRATEGY_ID}",
        }
    )

    handle = None
    ts_mode = None
    processed = []
    counts = {"BUY": 0, "SELL": 0, "WAIT": 0}
    errors: list[str] = []
    last_open = store.last_open_utc()
    mt5_started = False
    recovery_stats: dict[str, Any] = {}
    outcome_stats: dict[str, Any] = {"finalized": [], "notifications": [], "experience_added": 0}
    daily_result = None
    stopped = started

    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            path = terminal_path or MT5_TERMINAL_PATH
            conn = open_readonly(path)
            if conn.get("status") != "connected_readonly":
                raise Phase18LoopError(f"mt5 unavailable: {conn.get('reason') or conn.get('status')}")
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

        # Startup recovery using first poll bars
        m5_bars, h1_bars, as_of = source()
        m5_sorted = sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"])
        store.cache_bars(m5_sorted)
        recovery_stats = recover_on_startup(
            store=store,
            experience=experience,
            bars=m5_sorted,
            as_of=as_of,
            discord_enabled=enable_discord,
            dry_run_discord=dry_run_discord,
            ledger=ledger,
            transport=transport,
        )

        while len(processed) < max_candles:
            if stop_flag and stop_flag():
                break
            m5_bars, h1_bars, as_of = source()
            m5_sorted = sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"])
            store.cache_bars(m5_sorted)
            if h1_bars and h1_bars and "bar_open_timestamp_utc" in h1_bars[0]:
                h1_rows = h1_rows_for_trend(h1_bars)
            else:
                h1_rows = list(h1_bars)

            new_bars = [
                b for b in m5_sorted if last_open is None or b["bar_open_timestamp_utc"] > last_open
            ]
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
                        transport=transport,
                    )
                    processed.append(result)
                    counts[result["experimental_action"]] = counts.get(result["experimental_action"], 0) + 1
                    last_open = bar["bar_open_timestamp_utc"]
                    prev = last_open
                    made_progress = True
                except Exception as exc:
                    errors.append(redact_secrets(f"{bar.get('bar_open_timestamp_utc')}: {exc}"))

            # After journaling new signals, resolve any newly eligible outcomes
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
            outcome_stats["notifications"].extend(resolved.get("notifications", []))
            outcome_stats["experience_added"] += int(resolved.get("experience_added", 0))

            if not made_progress:
                if bar_source is not None:
                    break
                time.sleep(max(1, int(poll_interval_seconds)))

        if send_daily_report:
            daily_result = maybe_send_daily_report(
                store=store,
                ledger=ledger,
                as_of=as_of,
                discord_enabled=enable_discord,
                dry_run_discord=dry_run_discord,
                transport=transport,
                force_date_pkt=daily_date_pkt,
            )
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
                "mode": "multihorizon_shadow_bounded",
                "mt5_connected": False,
                "error": "; ".join(errors[:20]),
                "notes": "graceful stop; lock cleared",
            }
        )

    outcome_counts = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0}
    for o in store.outcomes():
        st = str(o.get("status", "PENDING")).upper()
        if st in outcome_counts:
            outcome_counts[st] += 1

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
        "selected_horizon_policy": SELECTED_HORIZON_DISPLAY,
        "any_final_non_wait": any(p["final_action"] != "WAIT" for p in processed),
        "recovery": {
            "finalized_n": len(recovery_stats.get("finalized", [])),
            "experience_added": recovery_stats.get("experience_added", 0),
        },
        "outcomes": outcome_counts,
        "outcome_notifications_n": len(outcome_stats.get("notifications", [])),
        "shadow_experience_added": outcome_stats.get("experience_added", 0)
        + int(recovery_stats.get("experience_added", 0)),
        "experience_counts": experience.counts(),
        "daily_report": daily_result,
        "pending_outcomes": outcome_counts.get("PENDING", 0),
    }
