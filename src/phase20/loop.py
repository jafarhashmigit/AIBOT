"""Bounded real-MT5 shadow loop: observe → H13_C → journal → Discord(BUY/SELL) → outcomes."""

from __future__ import annotations

import json
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
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome
from phase18.store import Phase18Store
from phase20.candles import enrich_observation_timestamps, filter_completed_bars, is_complete_m5_bar
from phase20.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_MAX_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    PHASE19_SYNTHETIC,
    SELECTED_HORIZON_DISPLAY,
    SOURCE_TYPE,
    STRATEGY_ID,
    SYMBOL,
    TIMEFRAME,
)
from phase20.messages import build_shadow_outcome_payload, build_shadow_signal_payload

UTC = timezone.utc
BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class Phase20LoopError(RuntimeError):
    pass


def _ensure_wait_final(pred: dict[str, Any]) -> None:
    if pred.get("final_action") != "WAIT":
        raise Phase20LoopError("HARD FAILURE: production final_action must remain WAIT under NO_MODEL")
    if pred.get("champion_status") != CHAMPION_STATUS:
        raise Phase20LoopError("HARD FAILURE: champion status mismatch")


def _assert_isolated_root(root: Path) -> None:
    resolved = Path(root).resolve()
    banned = PHASE19_SYNTHETIC.resolve()
    try:
        resolved.relative_to(banned)
        raise Phase20LoopError("refusing to write real shadow data into Phase 19 synthetic namespace")
    except ValueError:
        pass
    # Also refuse writing into phase19 root generally for real runs
    p19 = (DATA_DIR.parent / "phase19").resolve()
    try:
        resolved.relative_to(p19)
        raise Phase20LoopError("refusing Phase 19 data directory for real AGENT_SHADOW")
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


def append_observation_log(root: Path, row: dict[str, Any]) -> None:
    path = Path(root) / "observation_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in row.items() if "webhook" not in str(k).lower()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, sort_keys=True, default=str) + "\n")


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
    log_root: Path | None = None,
) -> dict[str, Any]:
    if not is_complete_m5_bar(bar, as_of_utc=as_of):
        raise Phase20LoopError("incomplete candle rejected")

    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    quality = "gap" if g == "gap" else "ok"
    pred = predict_h13c_experimental(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    _ensure_wait_final(pred)

    ts = enrich_observation_timestamps(bar)
    obs_id = f"p20_obs_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
    dec_id = f"p20_dec_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"

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
        }

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
        "tp_level": "",
        "sl_level": "",
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": "phase20 real mt5 shadow; production WAIT; AGENT_SHADOW only on BUY/SELL outcomes",
    }
    newly_dec = store.append_decision(dec)
    pending = create_pending_outcomes(dec, atr=float(atr_val) if atr_val else None)
    store.append_outcomes(pending)

    delivery = {"status": "SKIPPED_WAIT_NO_DISCORD"}
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
    elif exp_action == "WAIT":
        delivery = {"status": "SKIPPED_WAIT_NO_DISCORD", "journaled_before_discord": True}

    if log_root is not None:
        append_observation_log(
            log_root,
            {
                **ts,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "experimental_action": exp_action,
                "final_action": pred["final_action"],
                "data_quality_status": quality,
                "decision_id": dec_id,
                "pending_horizons_created": len(pending),
                "discord_status": delivery.get("status"),
                "strategy": STRATEGY_ID,
            },
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
        "selected_horizon": SELECTED_HORIZON_DISPLAY,
        "timestamps": ts,
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
                payload = build_shadow_outcome_payload(updated)
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


def run_bounded_real_shadow_loop(
    *,
    max_candles: int = DEFAULT_MAX_CANDLES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    enable_discord: bool = True,
    dry_run_discord: bool = True,
    store_root=None,
    bar_source: BarSource | None = None,
    terminal_path: str | None = None,
    transport=None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if max_candles <= 0:
        raise Phase20LoopError("max_candles must be positive")

    root = Path(store_root) if store_root is not None else DATA_DIR
    _assert_isolated_root(root)
    store = Phase18Store(root)
    experience = ExperienceStore(root)
    ledger = DeliveryLedger(root / "discord_delivery_ledger.jsonl")
    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase20_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    if store.has_lock():
        raise Phase20LoopError("session lock already present; refusing start")
    store.write_lock(session_id, "real_mt5_shadow_bounded", started)
    store.append_session(
        {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": started,
            "stopped_at_utc": "",
            "mode": "real_mt5_shadow_bounded",
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
    outcome_stats: dict[str, Any] = {"finalized": [], "notifications": [], "experience_added": 0}
    recovery_stats: dict[str, Any] = {"finalized": [], "experience_added": 0}
    stopped = started

    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            path = terminal_path or MT5_TERMINAL_PATH
            conn = open_readonly(path)
            if conn.get("status") != "connected_readonly":
                raise Phase20LoopError(f"mt5 unavailable: {conn.get('reason') or conn.get('status')}")
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

        m5_bars, h1_bars, as_of = source()
        m5_sorted = filter_completed_bars(
            sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"]), as_of_utc=as_of
        )
        store.cache_bars(m5_sorted)
        recovery_stats = resolve_pending_outcomes(
            store=store,
            experience=experience,
            bars=store.load_cached_bars() or m5_sorted,
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
            m5_sorted = filter_completed_bars(
                sorted(m5_bars, key=lambda b: b["bar_open_timestamp_utc"]), as_of_utc=as_of
            )
            store.cache_bars(m5_sorted)
            if h1_bars and "bar_open_timestamp_utc" in h1_bars[0]:
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
                        log_root=root,
                    )
                    if result.get("duplicate"):
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
            outcome_stats["notifications"].extend(resolved.get("notifications", []))
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
                "mode": "real_mt5_shadow_bounded",
                "mt5_connected": False,
                "error": "; ".join(errors[:20]),
                "notes": "graceful stop; lock cleared",
            }
        )

    outcome_counts = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0}
    by_horizon: dict[str, dict[str, int]] = {}
    for o in store.outcomes():
        st = str(o.get("status", "PENDING")).upper()
        if st in outcome_counts:
            outcome_counts[st] += 1
        hid = str(o.get("horizon_id", ""))
        by_horizon.setdefault(hid, {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0})
        if st in by_horizon[hid]:
            by_horizon[hid][st] += 1

    discord_signals = sum(
        1
        for p in processed
        if (p.get("delivery") or {}).get("status") == "SENT"
        and p.get("experimental_action") in {"BUY", "SELL"}
    )

    return {
        "status": "completed",
        "session_id": session_id,
        "started_at_utc": started,
        "stopped_at_utc": stopped,
        "max_candles": max_candles,
        "candles_processed": len(processed),
        "observation_count": len(processed),
        "prediction_counts": counts,
        "processed": processed,
        "errors": errors,
        "lock_remaining": store.has_lock(),
        "mt5_session_started": mt5_started,
        "discord_enabled": enable_discord,
        "dry_run_discord": dry_run_discord,
        "discord_signals_sent": discord_signals,
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
        "outcomes_by_horizon": by_horizon,
        "pending_outcomes": outcome_counts.get("PENDING", 0),
        "completed_outcomes": sum(outcome_counts[k] for k in ("PASS", "FAIL", "TIMEOUT")),
        "shadow_experience_added": outcome_stats.get("experience_added", 0)
        + int(recovery_stats.get("experience_added", 0)),
        "experience_counts": experience.counts(),
        "phase19_synthetic_excluded": True,
        "store_root": str(root),
        "note": "Shadow observations only — not validated trading performance; no edge claimed.",
    }
