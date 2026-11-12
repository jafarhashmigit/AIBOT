"""Phase57.1 validation suite."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase57_1.adversarial import run_all_inject_stages, run_rebuild_adversarial, run_subprocess_suite
from phase57_1.constants import EXPECTED_NULL_POLICY
from phase57_1.durable_engine import make_durable_engine
from phase57_1.reconcile import reconcile


def before_after_gap_comparison(work: Path) -> dict[str, Any]:
    """
    Reproduce Phase57 gap (wipe shadow after close) and show Phase57.1 recovery.
    """
    work.mkdir(parents=True, exist_ok=True)
    day, m5, h1, by = directional_path(day="2099-12-01", move_after_entry=-5.0)
    eng = make_durable_engine(
        work=work,
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
    )
    r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    eng.persist()
    assert r.get("closed") is not None
    before = {
        "shadow_n": eng.shadow.n,
        "journal_exits": len(eng.journal.committed_exits()),
        "exit_fill": r["closed"].get("exit_fill"),
        "exit_reason": r["closed"].get("exit_reason"),
        "net_r": r["closed"].get("net_r"),
        "position_id": r["closed"].get("position_id"),
    }
    # Wipe derived experience (Phase57 HIGH gap scenario)
    eng.shadow.path.write_text("", encoding="utf-8")
    eng.shadow._records = []
    eng.state.save()
    mid = {"shadow_n": eng.shadow.n, "closed_ids": list(eng.state.data.get("closed_position_ids") or [])}
    # Recover from journal
    eng2 = make_durable_engine(work=work, policy=NullPolicy())
    rec = eng2.recover_pending()
    after = {
        "shadow_n": eng2.shadow.n,
        "recovery": rec,
        "exit_fill": None,
        "net_r": None,
        "experience_id": None,
    }
    if eng2.shadow.n:
        sh = eng2.shadow.all()[0]
        after["net_r"] = sh.get("actual_costed_outcome_net_r")
        after["experience_id"] = sh.get("experience_id")
        after["exit_reason"] = (sh.get("decision_context") or {}).get("exit_reason")
    # Match journal payload
    payload = eng2.journal.committed_exits()[0]["payload"]
    match = (
        after["shadow_n"] >= 1
        and after["net_r"] == before["net_r"]
        and after.get("exit_reason") == before["exit_reason"]
        and payload.get("exit_fill") == before["exit_fill"]
    )
    rep = reconcile(journal=eng2.journal, state=eng2.state, shadow=eng2.shadow, hist=eng2.hist)
    return {
        "before": before,
        "after_wipe": mid,
        "after_recovery": after,
        "values_match": match,
        "reconcile": rep,
        "ok": match and rep.get("ok"),
    }


def null_policy_check(work: Path) -> dict[str, Any]:
    eng = make_durable_engine(work=work)
    ok = isinstance(eng.policy, NullPolicy) and eng.policy.version == EXPECTED_NULL_POLICY
    return {"ok": ok, "version": getattr(eng.policy, "version", None)}


def choose_verdict(p: dict[str, Any]) -> tuple[str, str]:
    need = [
        p.get("gap_fixed"),
        p.get("rebuild_ok"),
        p.get("inject_ok"),
        p.get("subprocess_ok"),
        p.get("reconcile_ok"),
        p.get("null_ok"),
        (p.get("tests") or {}).get("ok"),
    ]
    if all(need):
        return (
            "DURABLE_EXPERIENCE_RECOVERY_VALIDATED",
            "Journal-backed EXIT_COMMITTED survives experience wipe; rebuild/reconcile/adversarial/subprocess passed.",
        )
    hard = [p.get("gap_fixed"), p.get("null_ok"), (p.get("tests") or {}).get("ok")]
    if not all(hard):
        return (
            "DURABLE_EXPERIENCE_RECOVERY_FAILED",
            f"Hard criteria failed: gap_fixed={p.get('gap_fixed')} null={p.get('null_ok')} tests={p.get('tests')}",
        )
    return (
        "DURABLE_EXPERIENCE_RECOVERY_PARTIAL",
        "Core gap mitigated but some adversarial/subprocess/reconcile criteria incomplete.",
    )


def run_full_suite() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="phase57_1_"))
    gap = before_after_gap_comparison(root / "gap")
    rebuild = run_rebuild_adversarial(root / "rebuild")
    inject = run_all_inject_stages(root / "inject")
    sub = run_subprocess_suite(root / "subproc")
    null = null_policy_check(root / "null")

    # Final reconcile on gap workdir after recovery
    reconcile_ok = bool(gap.get("ok")) and bool(rebuild.get("ok"))

    return {
        "work_root": str(root),
        "gap": gap,
        "rebuild": rebuild,
        "inject": inject,
        "subprocess": sub,
        "null_policy": null,
        "gap_fixed": bool(gap.get("ok")),
        "rebuild_ok": bool(rebuild.get("ok")),
        "inject_ok": bool(inject.get("all_ok")),
        "subprocess_ok": bool(sub.get("all_ok")),
        "reconcile_ok": reconcile_ok,
        "null_ok": bool(null.get("ok")),
    }
