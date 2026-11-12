"""Phase57 validation suite — evidence for every critical invariant."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.adapter import make_engine, reset_phase57_data
from phase57.constants import CRITICAL_INVARIANTS
from phase57.crash_inject import run_all_crash_stages
from phase57.execution_cases import run_execution_integrity
from phase57.fixtures import clean_bundle
from phase57.invariants import (
    check_buy_sell_prices,
    check_experience_separation,
    check_independent_recompute,
    check_no_double_close,
    check_no_duplicate_decisions,
    check_no_orphans,
    check_null_policy_default,
    check_once_per_observation,
    check_sl_first_same_bar,
    check_sl_tp_before_horizon_trace,
)
from phase57.stress import run_stress


def run_lifecycle_integrity(work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    hist = work / "hist"
    shadow = work / "shadow"
    eng = make_engine(
        state_path=work / "life.json",
        registry_path=work / "life_c.json",
        policy=EngineeringTestPolicy(["BUY", "SELL", "WAIT"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        immediate_monitor_through_horizon=True,
        record_counterfactuals=True,
        hist_root=hist,
        shadow_root=shadow,
    )
    results = []
    traces = []
    closed = []
    accepted = []
    for i, move in enumerate([-5.0, 5.0, 0.0]):
        day, m5, h1, by = clean_bundle(day=f"2099-10-0{i+1}", move_after_entry=move)
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48, require_new_candle=False)
        results.append({"day": day, "idx": 48, **{k: r.get(k) for k in ("skipped", "rejected", "decision", "closed")}})
        if r.get("trace"):
            traces.append(r["trace"])
        if not r.get("skipped") and not r.get("rejected") and r.get("decision"):
            accepted.append({"key": f"{day}:48", "action": r["decision"].get("action")})
        if r.get("closed"):
            closed.append(r["closed"])
        r2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48, require_new_candle=False)
        results.append({"day": day, "idx": 48, "skipped": r2.get("skipped"), "rejected": r2.get("rejected"), "dup_attempt": True})

    firsts = [x for x in results if not x.get("dup_attempt")]
    invs = [
        check_null_policy_default(
            make_engine(
                state_path=work / "null.json",
                registry_path=work / "null_c.json",
                hist_root=work / "null_hist",
                shadow_root=work / "null_shadow",
            )
        ),
        check_once_per_observation(list(eng.state.data.get("processed_decision_keys") or []), accepted),
        check_no_duplicate_decisions(firsts),
        check_sl_tp_before_horizon_trace(traces),
        check_buy_sell_prices(closed),
        check_no_double_close(list(eng.state.data.get("closed_position_ids") or [])),
        check_no_orphans(dict(eng.risk.open_positions), list(eng.state.data.get("closed_position_ids") or [])),
        check_experience_separation(
            str(eng.hist.path),
            str(eng.shadow.path),
            eng.hist.all(),
            eng.shadow.all(),
        ),
    ]
    day, m5, h1, by = clean_bundle(day="2099-10-09")
    invs.append(check_sl_first_same_bar(m5, by, 49))

    day_b, m5b, h1b, byb = clean_bundle(day="2099-10-11", move_after_entry=-5.0)
    eng_b = make_engine(
        state_path=work / "indep.json",
        registry_path=work / "indep_c.json",
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        immediate_monitor_through_horizon=True,
        hist_root=work / "indep_hist",
        shadow_root=work / "indep_shadow",
    )
    rb = eng_b.process_bar(day=day_b, m5=m5b, h1=h1b, ticks_by_bar=byb, idx=48)
    if rb.get("closed"):
        inv_re = check_independent_recompute(rb["closed"], m5b, byb)
        invs.append(inv_re)
    else:
        invs.append({"id": "independent_recompute_match", "ok": False, "error": "no_closed"})

    by_id = {i["id"]: i for i in invs}
    required = (
        "once_per_accepted_observation",
        "no_duplicate_candle_decisions",
        "sl_tp_before_horizon_in_trace",
        "buy_exit_bid_sell_exit_ask",
        "sl_first_same_bar",
        "no_double_close",
        "no_orphaned_opens_after_clean_run",
        "null_policy_default",
        "experience_stores_separated",
        "independent_recompute_match",
    )
    return {
        "invariants": by_id,
        "closed_n": len(closed),
        "accepted_n": len(accepted),
        "actions": [a["action"] for a in accepted],
        "ok": all(by_id.get(k, {}).get("ok") for k in required),
    }


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    crit = payload.get("critical_invariants") or {}
    failed = [k for k, v in crit.items() if not (v or {}).get("ok")]
    high = [
        f
        for f in (payload.get("failures") or [])
        if str(f.get("severity", "")).upper() == "HIGH"
    ]
    # Hard fail: lifecycle price/idempotency/orphan/null policy
    hard = {
        "once_per_accepted_observation",
        "no_duplicate_candle_decisions",
        "buy_exit_bid_sell_exit_ask",
        "sl_first_same_bar",
        "no_double_close",
        "null_policy_default",
        "independent_recompute_match",
    }
    if any(k in hard for k in failed):
        return (
            "AUTONOMOUS_RELIABILITY_FAILED",
            f"Critical hard invariants failed: {failed}",
        )
    if failed:
        return (
            "AUTONOMOUS_RELIABILITY_PARTIAL",
            f"Some critical invariants incomplete or recovery gaps remain: {failed}",
        )
    if high:
        # e.g. experience not rebuildable after post-exit store wipe — not a green wash
        return (
            "AUTONOMOUS_RELIABILITY_PARTIAL",
            "Critical invariants passed, but HIGH residual integrity gaps remain "
            f"({[h.get('id') for h in high]}). Experience rebuild from closed_ids unsupported.",
        )
    if payload.get("critical_ok"):
        return (
            "AUTONOMOUS_RELIABILITY_VALIDATED",
            "All critical invariants evidenced; crash recovery and stress passed without duplicate entry/exit.",
        )
    return (
        "AUTONOMOUS_RELIABILITY_PARTIAL",
        "Insufficient evidence for full validation.",
    )


def run_full_suite() -> dict[str, Any]:
    reset_phase57_data()
    work = Path(tempfile.mkdtemp(prefix="phase57_"))
    lifecycle = run_lifecycle_integrity(work / "life")
    crash = run_all_crash_stages(work / "crash")
    execution = run_execution_integrity(work / "exec")
    stress = run_stress(work / "stress")

    inv_map = dict(lifecycle.get("invariants") or {})
    inv_map["unsafe_data_blocks_entry"] = {
        "id": "unsafe_data_blocks_entry",
        "ok": bool(execution.get("cases", {}).get("stale_blocks_entry", {}).get("ok"))
        and bool(execution.get("cases", {}).get("daily_loss_blocks_entry", {}).get("ok")),
        "stale": execution.get("cases", {}).get("stale_blocks_entry"),
        "daily_loss": execution.get("cases", {}).get("daily_loss_blocks_entry"),
    }
    # Restart integrity: no duplicate opens across crash stages + stress multi-restart
    crash_rows = crash.get("rows") or []
    no_dup_opens = all(not r.get("duplicate_open_after_restart") for r in crash_rows)
    no_dbl_close = all(not r.get("double_close") for r in crash_rows)
    inv_map["restart_no_duplicate_entry"] = {
        "id": "restart_no_duplicate_entry",
        "ok": no_dup_opens and no_dbl_close and bool(stress.get("evidence", {}).get("multi_restart", {}).get("ok")),
        "crash_no_dup_opens": no_dup_opens,
        "crash_no_double_close": no_dbl_close,
        "crash_all_ok": crash.get("all_ok"),
        "stress_restart": stress.get("evidence", {}).get("multi_restart"),
        "outcome_gap_stages": [r["stage"] for r in crash_rows if r.get("lost_outcome_after_gap")],
    }

    critical_results = {k: inv_map.get(k, {"ok": False, "error": "missing"}) for k in CRITICAL_INVARIANTS}
    critical_ok = all(v.get("ok") for v in critical_results.values())

    failures = [
        {"id": k, "severity": "CRITICAL", "detail": v}
        for k, v in critical_results.items()
        if not v.get("ok")
    ]
    if not stress.get("evidence", {}).get("deterministic", {}).get("ok"):
        failures.append(
            {
                "id": "deterministic_replay",
                "severity": "HIGH",
                "detail": stress.get("evidence", {}).get("deterministic"),
            }
        )
    for r in crash_rows:
        if r.get("lost_outcome_after_gap"):
            failures.append(
                {
                    "id": f"outcome_gap:{r['stage']}",
                    "severity": "HIGH",
                    "detail": {
                        "note": "closed_ids durable after wipe; experience not rebuilt from state",
                        "experience_rebuild_supported": False,
                    },
                }
            )

    payload = {
        "lifecycle": lifecycle,
        "crash": {k: crash[k] for k in ("n", "all_ok", "stages") if k in crash},
        "crash_full": crash,
        "execution": execution,
        "stress": stress,
        "critical_invariants": critical_results,
        "critical_ok": critical_ok,
        "failures": failures,
        "work_dir": str(work),
        "null_policy": isinstance(
            make_engine(state_path=work / "np.json", registry_path=work / "np_c.json").policy,
            NullPolicy,
        ),
    }
    verdict, reason = choose_verdict(payload)
    payload["verdict"] = verdict
    payload["verdict_reason"] = reason
    return payload
