"""Phase 29 forward shadow loop — dual observers, concise Discord, recovery-safe."""

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
from phase18.experience import ExperienceStore
from phase18.outcomes import atr_at_signal
from phase20.candles import filter_completed_bars, is_complete_m5_bar
from phase28.frozen_vol import load_frozen_vol_artifact
from phase28.integrity import verify_frozen_vol_ready
from phase28.journals import ObserverJournal, OutcomeStore
from phase28.live_features import predict_vol_at_bar
from phase29.campaign import CampaignStore, campaign_targets_met, evidence_status
from phase29.constants import (
    DATA_DIR,
    DEFAULT_POLL_INTERVAL_SECONDS,
    OBSERVER_A,
    OBSERVER_B,
    PRODUCTION_FINAL_ACTION,
)
from phase29.discord_notify import deliver_decision, make_ledger
from phase29.levels import planned_shadow_levels
from phase29.observers import build_baseline_record, build_high_vol_record, run_h13c_prediction
from phase29.outcomes import pending_from_decision, resolve_observer_outcomes, summarize_outcomes

UTC = timezone.utc
BarSource = Callable[[], tuple[list[dict], list[dict], str]]


class Phase29LoopError(RuntimeError):
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
    ledger,
    discord_enabled: bool,
    dry_run_discord: bool,
    notify_wait: bool,
    transport=None,
) -> dict[str, Any]:
    if not is_complete_m5_bar(bar, as_of_utc=as_of):
        raise Phase29LoopError("incomplete candle rejected")

    g = gap_status(prev_open, bar["bar_open_timestamp_utc"])
    h1_rows = h1_rows_for_trend(h1_bars)
    pred = run_h13c_prediction(
        m5_closes=closes_prefix,
        h1_rows=h1_rows,
        decision_time_utc=bar["bar_close_timestamp_utc"],
    )
    if pred.get("final_action") != PRODUCTION_FINAL_ACTION:
        raise Phase29LoopError("production final_action must remain WAIT")

    atr_val = None
    levels = None
    try:
        opens = [b["bar_open_timestamp_utc"] for b in all_m5]
        signal_pos = opens.index(bar["bar_open_timestamp_utc"])
        atr_val = atr_at_signal(all_m5, signal_pos)
        action = str(pred["experimental_action"]).upper()
        if action in {"BUY", "SELL"}:
            levels = planned_shadow_levels(
                side=action,
                reference_price=float(bar["close"]),
                atr=float(atr_val),
                spread_points=bar.get("spread"),
            )
    except Exception:
        atr_val = None
        levels = None

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
        levels=levels,
    )
    high = build_high_vol_record(
        bar=bar,
        pred=pred,
        vol=vol,
        gap_status=g,
        campaign_id=campaign_id,
        session_id=session_id,
        levels=levels,
    )

    results = {}
    for rec, oid in ((baseline, OBSERVER_A), (high, OBSERVER_B)):
        j = ObserverJournal(_observer_root(root, oid), oid)
        wrote = j.append(rec)
        results[oid] = {
            "written": wrote,
            "duplicate": not wrote,
            "decision_id": rec["decision_id"],
            "experimental_action": rec["experimental_action"],
            "accepted": rec["accepted"],
            "reason_code": rec["reason_code"],
        }
        if wrote:
            ostore = OutcomeStore(_observer_root(root, oid), oid)
            for row in pending_from_decision(rec, atr=atr_val):
                ostore.append(row)

    # Discord only for baseline observer (H13_C shadow signals).
    delivery = {"status": "SKIPPED_NOT_WRITTEN"}
    if results[OBSERVER_A]["written"]:
        delivery = deliver_decision(
            decision=baseline,
            ledger=ledger,
            discord_enabled=discord_enabled,
            dry_run=dry_run_discord,
            notify_wait=notify_wait,
            transport=transport,
        )

    return {
        "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
        "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
        "gap_status": g,
        "h13c_experimental_action": pred["experimental_action"],
        "final_action": pred["final_action"],
        "observers": results,
        "discord": delivery,
        "vol": {
            "ok": vol.get("ok"),
            "pred_vol_regime": vol.get("pred_vol_regime"),
            "pred_fwd_vol_12": vol.get("pred_fwd_vol_12"),
        },
    }


def resolve_all(*, root: Path, bars: list[dict], as_of: str) -> dict[str, Any]:
    out = {}
    for oid in (OBSERVER_A, OBSERVER_B):
        oroot = _observer_root(root, oid)
        decisions = ObserverJournal(oroot, oid).read_all()
        ostore = OutcomeStore(oroot, oid)
        exp = ExperienceStore(oroot)
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
            raise Phase29LoopError("HARD FAILURE: historical hypothetical store mutated")
        out[oid] = {
            **stats,
            "outcome_summary": summarize_outcomes(ostore.read_all()),
            "n_decisions": len(decisions),
            "n_accepted": sum(1 for d in decisions if d.get("accepted")),
            "n_buy_sell": sum(
                1 for d in decisions if str(d.get("h13c_experimental_action", "")).upper() in {"BUY", "SELL"}
            ),
        }
    return out


def _count_campaign_signals(root: Path) -> tuple[int, int, int]:
    """baseline buy/sell accepted, high-only accepted, matured outcome rows (any horizon)."""
    base = ObserverJournal(_observer_root(root, OBSERVER_A), OBSERVER_A).read_all()
    high = ObserverJournal(_observer_root(root, OBSERVER_B), OBSERVER_B).read_all()
    n_buy_sell = sum(1 for d in base if str(d.get("experimental_action", "")).upper() in {"BUY", "SELL"})
    n_high = sum(1 for d in high if d.get("accepted"))
    matured = 0
    for oid in (OBSERVER_A, OBSERVER_B):
        for r in OutcomeStore(_observer_root(root, oid), oid).read_all():
            if r.get("status") not in {None, "PENDING", ""}:
                matured += 1
    return n_buy_sell, n_high, matured


def run_bounded_live_shadow(
    *,
    max_candles: int | None = None,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    store_root: Path | None = None,
    bar_source: BarSource | None = None,
    terminal_path: str | None = None,
    discord_enabled: bool = False,
    dry_run_discord: bool = True,
    notify_wait: bool = False,
    stop_flag: Callable[[], bool] | None = None,
    transport=None,
) -> dict[str, Any]:
    root = Path(store_root) if store_root is not None else DATA_DIR
    root.mkdir(parents=True, exist_ok=True)
    campaign = CampaignStore(root)
    state = campaign.load()
    campaign_id = state["campaign_id"]
    processed = set(state.get("processed_keys") or [])

    started = now_utc_stamp() if bar_source is None else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    session_id = f"phase29_{started.replace(' ', 'T').replace(':', '')}_{uuid.uuid4().hex[:8]}"

    # Persist watermark once; never reset on restart.
    if not state.get("forward_observation_start_utc"):
        if bar_source is None:
            state["forward_observation_start_utc"] = started
            campaign.save(state)
        # Injected bar_source (tests): leave unset unless tests pre-set it.
    forward_start = state.get("forward_observation_start_utc")

    vol_ready = verify_frozen_vol_ready()
    vol_artifact = load_frozen_vol_artifact() if vol_ready.get("ok") else None
    high_vol_blocker = None if vol_artifact else (vol_ready.get("blocker") or "FROZEN_VOL_NOT_READY")

    ledger = make_ledger(root)
    handle = None
    mt5_started = False
    new_count = 0
    batch_results: list[dict] = []
    last_bars: list[dict] = []
    skipped_pre_start = 0
    as_of = started

    try:
        if bar_source is None:
            from phase16a.constants import MT5_TERMINAL_PATH

            conn = open_readonly(terminal_path or MT5_TERMINAL_PATH)
            if conn.get("status") != "connected_readonly":
                raise Phase29LoopError(f"MT5 readonly connect failed: {conn}")
            handle = conn["handle"]
            mt5_started = True

        while True:
            if stop_flag and stop_flag():
                break
            if max_candles is not None and new_count >= max_candles:
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
            prev_open = None
            progressed = False

            for i, bar in enumerate(m5):
                if max_candles is not None and new_count >= max_candles:
                    break
                key = bar["bar_open_timestamp_utc"]
                if prev_open is not None and key < prev_open:
                    raise Phase29LoopError("out-of-order candle open timestamp in feed")
                if prev_open is not None and key == prev_open:
                    raise Phase29LoopError("duplicate candle open timestamp in feed")
                if key in processed:
                    prev_open = key
                    continue
                if forward_start and bar["bar_close_timestamp_utc"] <= forward_start:
                    skipped_pre_start += 1
                    prev_open = key
                    continue

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
                    ledger=ledger,
                    discord_enabled=discord_enabled,
                    dry_run_discord=dry_run_discord,
                    notify_wait=notify_wait,
                    transport=transport,
                )
                processed.add(key)
                state["processed_keys"] = sorted(processed)[-8000:]
                state["new_candles_processed"] = int(state.get("new_candles_processed") or 0) + 1
                state["last_candle_close_utc"] = bar["bar_close_timestamp_utc"]
                if result.get("discord", {}).get("status") == "SENT":
                    action = result["observers"][OBSERVER_A]["experimental_action"]
                    if action in {"BUY", "SELL"}:
                        state["discord_signals_sent"] = int(state.get("discord_signals_sent") or 0) + 1
                    elif action == "WAIT":
                        state["discord_wait_sent"] = int(state.get("discord_wait_sent") or 0) + 1
                new_count += 1
                batch_results.append(result)
                progressed = True
                prev_open = key

            if last_bars:
                resolve_all(root=root, bars=last_bars, as_of=as_of)
            campaign.save(state)

            n_buy_sell, _, n_matured = _count_campaign_signals(root)
            ev = evidence_status(
                n_candles=int(state.get("new_candles_processed") or 0),
                n_buy_sell=n_buy_sell,
                n_matured=n_matured,
            )
            if campaign_targets_met(ev):
                break
            if not progressed:
                if bar_source is not None:
                    break
                time.sleep(max(1, int(poll_interval_seconds)))
            elif bar_source is not None:
                # Injected feeds are single-shot (tests); stop after one pass.
                break

        resolve_stats = resolve_all(root=root, bars=last_bars, as_of=as_of) if last_bars else {}
        n_buy_sell, n_high, n_matured = _count_campaign_signals(root)
        days = set()
        for d in ObserverJournal(_observer_root(root, OBSERVER_A), OBSERVER_A).read_all():
            ts = d.get("decision_timestamp_utc") or ""
            if ts:
                days.add(ts[:10])
        ev = evidence_status(
            n_candles=int(state.get("new_candles_processed") or 0),
            n_buy_sell=n_buy_sell,
            n_matured=n_matured,
            n_days=len(days),
        )
        state.setdefault("batches", []).append(
            {
                "session_id": session_id,
                "new_candles": new_count,
                "ended_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "forward_observation_start_utc": forward_start,
                "skipped_pre_start_candles": skipped_pre_start,
                "high_vol_blocker": high_vol_blocker,
                "discord_enabled": discord_enabled,
                "dry_run_discord": dry_run_discord,
            }
        )
        campaign.save(state)
        return {
            "session_id": session_id,
            "mt5_session_started": mt5_started,
            "mt5_readonly": True,
            "discord_enabled": discord_enabled,
            "dry_run_discord": dry_run_discord,
            "broker_orders": 0,
            "new_candles_processed": new_count,
            "forward_observation_start_utc": forward_start,
            "skipped_pre_start_candles": skipped_pre_start,
            "campaign_state": state,
            "batch_results": batch_results,
            "resolve_stats": resolve_stats,
            "n_buy_sell_baseline": n_buy_sell,
            "n_high_only_accepted": n_high,
            "n_matured_outcomes": n_matured,
            "high_vol_blocker": high_vol_blocker,
            "evidence": ev,
            "production_final_action": PRODUCTION_FINAL_ACTION,
        }
    finally:
        if handle is not None:
            close_readonly(handle)
