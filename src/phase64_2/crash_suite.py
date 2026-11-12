"""Crash/recovery matrix for Phase64.2 hardening."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase57_1.journal import CrashInjected as DurableCrash
from phase64_2.constants import STATUS_PAPER_FINALIZED, STATUS_WAIT_FINALIZED, canonical_json_sha256
from phase64_2.engine import make_hardened_engine
from phase64.execution_intent import CrashInjected as IntentJournalCrash
from phase64_2.intent_state import CrashInjected


def _bundle():
    return clean_bundle(day="2099-11-01", move_after_entry=-5.0)


_PROFILE = {
    "symbol": "XAUUSDm",
    "digits": 3,
    "broker": "Exness",
    "environment": "DEMO",
    "platform": "MT5",
    "verification_status": "UNKNOWN",
}


def case_crash(crash_at: str, *, action: str = "BUY") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = _bundle()
        first_crash = crash_at
        # Repair-only crash: first leave incomplete via outcome-before-status, then crash in repair
        if crash_at == "during_intent_status_repair":
            first_crash = "after_durable_outcome_before_intent_status"
        eng = make_hardened_engine(
            work=work,
            policy=EngineeringTestPolicy([action]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            crash_at=first_crash,
            account_profile=dict(_PROFILE),
        )
        raised = None
        try:
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        except (CrashInjected, IntentJournalCrash, DurableCrash) as exc:
            raised = str(exc)

        repair_crash = crash_at if crash_at == "during_intent_status_repair" else None
        eng2 = make_hardened_engine(
            work=work,
            policy=EngineeringTestPolicy([action]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            crash_at=repair_crash,
            account_profile=dict(_PROFILE),
        )
        recovery = None
        try:
            recovery = eng2.recover_pending()
        except (CrashInjected, IntentJournalCrash) as exc:
            raised = raised or str(exc)
            eng3 = make_hardened_engine(
                work=work,
                policy=EngineeringTestPolicy([action]),
                risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
                crash_at=None,
                account_profile=dict(_PROFILE),
            )
            recovery = eng3.recover_pending()
            eng2 = eng3

        # Replay / complete
        eng2.crash_at = None
        eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        intents = eng2.intent_journal.all_intents()
        statuses = [i.get("intent_status") for i in intents]
        closed = set(eng2.state.data.get("closed_position_ids") or [])
        pending_closed = []
        for i in intents:
            st = i.get("intent_status")
            if st == "PENDING":
                for r in eng2.intent_journal.all_records():
                    if r.get("intent_id") == i.get("intent_id") and r.get("stage") == "OUTCOME_RECORDED":
                        pid = (r.get("payload") or {}).get("position_id")
                        if pid in closed:
                            pending_closed.append(i.get("intent_id"))
        if action == "BUY":
            terminal_ok = STATUS_PAPER_FINALIZED in statuses and all(
                s in (STATUS_PAPER_FINALIZED, None) or s != "PENDING" for s in statuses
            )
            # Prefer single finalized intent
            terminal_ok = statuses.count(STATUS_PAPER_FINALIZED) >= 1 and "PENDING" not in statuses
        else:
            terminal_ok = STATUS_WAIT_FINALIZED in statuses and "PENDING" not in statuses
        return {
            "case": crash_at,
            "crash_raised": raised,
            "n_intents": len(intents),
            "statuses": statuses,
            "pending_after_closed": pending_closed,
            "recovery_repaired": (recovery or {}).get("intent_repair", {}).get("n_repaired") if recovery else None,
            "pass": raised is not None
            and len(pending_closed) == 0
            and len(intents) == 1
            and terminal_ok,
            "genuine_broker_evidence": False,
        }


def run_crash_matrix() -> dict[str, Any]:
    cases = [
        case_crash("after_durable_outcome_before_intent_status"),
        case_crash("after_intent_outcome_before_experience_link"),
        case_crash("during_wait_experience_append", action="WAIT"),
        case_crash("after_wait_experience_before_intent_finalize", action="WAIT"),
        case_crash("during_intent_status_repair"),
    ]
    # Happy path BUY finalize
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = _bundle()
        eng = make_hardened_engine(
            work=work,
            policy=EngineeringTestPolicy(["BUY"]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            account_profile={"symbol": "XAUUSDm"},
        )
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        st = (out.get("intent") or {}).get("intent_status")
        cases.append(
            {
                "case": "happy_buy_finalized",
                "intent_status": st,
                "pass": st == STATUS_PAPER_FINALIZED,
                "audit_consistent": (out.get("intent_audit") or {}).get("consistent"),
                "genuine_broker_evidence": False,
            }
        )
    # Happy WAIT
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = _bundle()
        eng = make_hardened_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        st = (out.get("intent") or {}).get("intent_status")
        n_shadow = eng.shadow.n
        out2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        cases.append(
            {
                "case": "happy_wait_finalized_idempotent",
                "intent_status": st,
                "shadow_n": n_shadow,
                "second_skipped": out2.get("skipped"),
                "pass": st == STATUS_WAIT_FINALIZED and n_shadow == 1 and out2.get("skipped"),
                "genuine_broker_evidence": False,
            }
        )

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "broker_order_send": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
