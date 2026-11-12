"""Crash/recovery simulation at lifecycle boundaries — Phase57 only."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.shutdown import graceful_shutdown
from phase57.adapter import make_engine
from phase57.constants import CRASH_DIR
from phase57.fixtures import clean_bundle
from phase57.progress import write_json


CrashStage = str

STAGES = (
    "after_observation",
    "after_decision",
    "after_risk",
    "after_paper_entry",
    "during_monitoring",
    "after_exit_before_outcome",
    "during_experience",
)


def _snapshot(engine, label: str) -> dict[str, Any]:
    engine.persist()
    return {
        "label": label,
        "processed_keys": list(engine.state.data.get("processed_decision_keys") or []),
        "closed_ids": list(engine.state.data.get("closed_position_ids") or []),
        "open_ids": sorted(engine.risk.open_positions),
        "open_positions": copy.deepcopy(dict(engine.risk.open_positions)),
        "shadow_n": engine.shadow.n,
        "hist_n": engine.hist.n,
        "cursor": dict(engine.state.data.get("cursor") or {}),
    }


def run_crash_stage(
    stage: CrashStage,
    *,
    work_dir: Path,
) -> dict[str, Any]:
    """
    Simulate interruption at `stage` then restart from persisted state.
    Uses EngineeringTestPolicy BUY only for entry stages; evidence-tagged.
    """
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    state_path = work_dir / f"{stage}_state.json"
    reg_path = work_dir / f"{stage}_candles.json"
    if state_path.exists():
        state_path.unlink()
    if reg_path.exists():
        reg_path.unlink()

    day, m5, h1, by = clean_bundle(day="2099-08-01", move_after_entry=-5.0)
    hist_root = work_dir / f"{stage}_hist"
    shadow_root = work_dir / f"{stage}_shadow"
    eng = make_engine(
        state_path=state_path,
        registry_path=reg_path,
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        immediate_monitor_through_horizon=False,
        record_counterfactuals=True,
        hist_root=hist_root,
        shadow_root=shadow_root,
    )

    pre = _snapshot(eng, "pre")
    crashed = False
    result: dict[str, Any] = {}
    outcome_gap = False

    # Manual staged pipeline mirroring IntegratedLifecycleEngine without modifying it:
    # We call process_bar for most stages; for fine-grained mid-pipeline crashes we
    # persist after partial operations using engine primitives.

    if stage == "after_observation":
        obs = eng.observer.observe(day=day, m5=m5, idx=48, h1=h1, ticks_by_bar=by, require_new_candle=False)
        eng.persist()
        crashed = True
        result = {"obs_accepted": obs.get("accepted")}
    elif stage == "after_decision":
        # can't stop mid process_bar; approximate: observe+decide then persist without mark_processed
        from phase54.decision import decide

        obs = eng.observer.observe(day=day, m5=m5, idx=48, h1=h1, ticks_by_bar=by, require_new_candle=False)
        dec = decide(obs, obs.get("features") or {}, None, eng.risk.snapshot(), policy=eng.policy)
        eng.state.data["crash_pending_decision"] = dec
        eng.persist()
        crashed = True
        result = {"decision": dec.get("action")}
    elif stage == "after_risk":
        from phase54.decision import decide

        obs = eng.observer.observe(day=day, m5=m5, idx=48, h1=h1, ticks_by_bar=by, require_new_candle=False)
        dec = decide(obs, obs.get("features") or {}, None, eng.risk.snapshot(), policy=eng.policy)
        gate = eng.risk.evaluate(dec, obs)
        eng.state.data["crash_pending_gate"] = gate
        eng.persist()
        crashed = True
        result = {"gate": gate}
    elif stage == "after_paper_entry":
        # Full open without exit
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        crashed = True
        result = {"action": (r.get("decision") or {}).get("action"), "open_n": len(eng.risk.open_positions), "closed": r.get("closed")}
        graceful_shutdown(eng, reason=f"CRASH_{stage}")
    elif stage == "during_monitoring":
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.persist()
        crashed = True
        result = {"open_n": len(eng.risk.open_positions)}
        graceful_shutdown(eng, reason=f"CRASH_{stage}")
    elif stage == "after_exit_before_outcome":
        # Phase56 process_bar finalizes close + persist atomically. Probe the
        # gap: truncate shadow AFTER close while keeping closed_ids — recovery
        # must not double-close; outcome rebuild unsupported (integrity gap).
        eng.immediate_monitor_through_horizon = True
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.persist()
        body = eng.shadow.path.read_text(encoding="utf-8") if eng.shadow.path.is_file() else ""
        eng.shadow.path.write_text("", encoding="utf-8")
        eng.shadow._records = []
        eng.state.save()
        crashed = True
        outcome_gap = True
        result = {
            "closed": (r.get("closed") or {}).get("exit_reason"),
            "shadow_bytes_before_wipe": len(body),
            "outcome_gap_injected": True,
        }
    elif stage == "during_experience":
        eng.immediate_monitor_through_horizon = True
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.persist()
        eng.shadow.flush()
        crashed = True
        result = {"shadow_n": eng.shadow.n}
        graceful_shutdown(eng, reason=f"CRASH_{stage}")
    else:
        return {"stage": stage, "ok": False, "error": "unknown_stage"}

    mid = _snapshot(eng, "crash_point")

    # Restart
    eng2 = make_engine(
        state_path=state_path,
        registry_path=reg_path,
        policy=EngineeringTestPolicy(["WAIT"]),  # no new directional spam
        risk=RiskManager({"max_spread_atr": 2.0}),
        immediate_monitor_through_horizon=False,
        record_counterfactuals=False,
        hist_root=hist_root,
        shadow_root=shadow_root,
    )
    # Continue monitoring if open
    closed_after = []
    if eng2.risk.open_positions:
        # drop price to hit SL
        for pid, pos in list(eng2.risk.open_positions.items()):
            pos["stop_loss"] = float(pos["entry_fill"]) - 0.01
            pos["take_profit"] = float(pos["entry_fill"]) + 100
            eng2.risk.open_positions[pid] = pos
            for j in range(49, 55):
                ts = str(m5[j]["timestamp_utc"])
                px = float(pos["entry_fill"]) - 1.0
                by[ts] = [{"epoch_ms": j, "timestamp_utc": ts, "bid": px, "ask": px + 0.1}]
        closed_after = eng2.monitor_open_positions(day=day, m5=m5, ticks_by_bar=by, current_idx=54)

    # Idempotent re-process: if already marked before restart, must skip;
    # if crash was before mark_processed, first completion is allowed then second must skip.
    keys_before = list(eng2.state.data.get("processed_decision_keys") or [])
    was_processed = any(k.endswith(":48") for k in keys_before)
    again = eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    if was_processed:
        idempotent = again.get("skipped") is True
    else:
        again2 = eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        idempotent = again2.get("skipped") is True
    post = _snapshot(eng2, "recovered")

    # Integrity checks — >1 open means duplicate entry for this single-symbol test
    dup_entry = len(eng2.risk.open_positions) > 1

    closed_ids = eng2.state.data.get("closed_position_ids") or []
    double_close = len(closed_ids) != len(set(closed_ids))
    shadow_after = eng2.shadow.n
    lost_outcome = bool(outcome_gap) and bool(closed_ids) and shadow_after == 0
    experience_ok = (not lost_outcome) if stage == "during_experience" else True
    recovery_ok = (not dup_entry) and (not double_close) and idempotent and experience_ok

    report = {
        "stage": stage,
        "crashed": crashed,
        "pre": pre,
        "mid": mid,
        "post": post,
        "result": result,
        "closed_after_restart": [c.get("exit_reason") for c in closed_after],
        "idempotent_reprocess": idempotent,
        "duplicate_open_after_restart": dup_entry,
        "double_close": double_close,
        "shadow_n_after_restart": shadow_after,
        "outcome_gap_injected": outcome_gap,
        "lost_outcome_after_gap": lost_outcome,
        "experience_rebuild_supported": False if outcome_gap else None,
        "ok": recovery_ok,
    }
    write_json(CRASH_DIR / f"{stage}.json", report)
    return report


def run_all_crash_stages(work_dir: Path) -> dict[str, Any]:
    rows = [run_crash_stage(s, work_dir=work_dir) for s in STAGES]
    return {
        "n": len(rows),
        "all_ok": all(r.get("ok") for r in rows),
        "stages": {r["stage"]: {"ok": r.get("ok"), "idempotent": r.get("idempotent_reprocess")} for r in rows},
        "rows": rows,
    }
