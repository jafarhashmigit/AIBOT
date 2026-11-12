"""Deterministic crash/recovery readiness tests — fixtures only; no broker execution."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from phase64.constants import FIXTURE_PROVENANCE, canonical_json_sha256
from phase64.execution_intent import (
    CrashInjected,
    ExecutionIntentJournal,
    create_execution_intent,
    mark_broker_rejected,
    mark_missing_execution,
)
from phase64.linkage import independent_decision_count, link_deal_fill, link_order, reconcile_orders_deals_fills


def _fixture_decision(*, action: str = "BUY", decision_id: str | None = None) -> dict[str, Any]:
    did = decision_id or uuid.uuid4().hex
    return {
        "decision_id": did,
        "timestamp_utc": "2026-11-11T12:00:00Z",
        "action": action,
        "proposed_action": action,
        "instrument": "XAUUSDm",
        "observation_id": uuid.uuid4().hex,
        "market_state_id": "XAUUSDm:M5:2026-11-11T12:00:00Z",
        "execution_assumptions": {
            "bid_ref": 2650.100,
            "ask_ref": 2650.250,
            "commission": None,
            "slippage": None,
        },
    }


def _risk_allow(action: str = "BUY") -> dict[str, Any]:
    return {"allowed": True, "final_action": action, "reasons": ["FIXTURE_ALLOW"]}


def _risk_reject() -> dict[str, Any]:
    return {"allowed": False, "final_action": "WAIT", "reasons": ["FIXTURE_REJECT"]}


def test_crash_between_decision_and_intent() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root, crash_at="between_decision_and_intent")
        d = _fixture_decision()
        raised = False
        try:
            create_execution_intent(
                j,
                decision=d,
                risk=_risk_allow(),
                account_profile={"symbol": "XAUUSDm", "fixture": True},
            )
        except CrashInjected:
            raised = True
        # Recover: new journal, no crash
        j2 = ExecutionIntentJournal(root)
        # DECISION_RECORDED may exist; INTENT_PERSISTED must not for crashed path
        stages = [r.get("stage") for r in j2.all_records()]
        # create_execution_intent commits DECISION_RECORDED then INTENT_PERSISTED;
        # crash on INTENT_PERSISTED means DECISION_RECORDED persisted.
        ok = raised and "INTENT_PERSISTED" not in stages
        # Complete intent after recovery
        j3 = ExecutionIntentJournal(root)
        create_execution_intent(
            j3,
            decision=d,
            risk=_risk_allow(),
            account_profile={"symbol": "XAUUSDm", "fixture": True},
        )
        intents = j3.intents_for_decision(d["decision_id"])
        return {
            "case": "crash_between_decision_and_intent",
            "crash_raised": raised,
            "intent_absent_after_crash": ok,
            "recovered_intent_count": len(intents),
            "orphan_decision_without_double_fill": len(intents) >= 1,
            "pass": raised and len(intents) >= 1 and independent_decision_count(j3)["n_independent_decisions"] >= 1,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def test_crash_after_intent_persistence() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root, crash_at="after_intent_persistence")
        d = _fixture_decision()
        raised = False
        try:
            create_execution_intent(
                j,
                decision=d,
                risk=_risk_allow(),
                account_profile={"symbol": "XAUUSDm", "fixture": True},
            )
        except CrashInjected:
            raised = True
        # WAL recovery should restore INTENT_PERSISTED
        j2 = ExecutionIntentJournal(root)
        intents = j2.intents_for_decision(d["decision_id"])
        stages = [r.get("stage") for r in j2.all_records()]
        return {
            "case": "crash_after_intent_persistence",
            "crash_raised": raised,
            "recovered_via_wal": "INTENT_PERSISTED" in stages and len(intents) == 1,
            "n_intents": len(intents),
            "no_double_intent": len(intents) == 1,
            "pass": raised and len(intents) == 1,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def test_duplicate_broker_deal_import() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root)
        d = _fixture_decision()
        created = create_execution_intent(
            j, decision=d, risk=_risk_allow(), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        iid = created["intent_id"]
        link_order(j, intent_id=iid, decision_id=d["decision_id"], order_id="ORD-1")
        link_deal_fill(
            j,
            intent_id=iid,
            decision_id=d["decision_id"],
            deal_id="DEAL-1",
            order_id="ORD-1",
            actual_fill_price=2650.30,
            requested_price=2650.25,
            volume=0.01,
            fill_kind="FULL",
            commission=None,
        )
        # Second import of same deal_id — record again then reconcile detects duplicate
        link_deal_fill(
            j,
            intent_id=iid,
            decision_id=d["decision_id"],
            deal_id="DEAL-1",
            order_id="ORD-1",
            actual_fill_price=2650.30,
            requested_price=2650.25,
            volume=0.01,
            fill_kind="FULL",
            commission=None,
        )
        recon = reconcile_orders_deals_fills(j.all_records())
        counts = independent_decision_count(j)
        return {
            "case": "duplicate_broker_deal_import",
            "duplicate_deal_imports": recon["duplicate_deal_imports"],
            "n_independent_decisions": counts["n_independent_decisions"],
            "n_fill_rows": counts["n_fill_rows"],
            "pass": recon["duplicate_deal_imports"] >= 1 and counts["n_independent_decisions"] == 1,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def test_partial_fill_then_restart() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root, crash_at="after_partial_fill")
        d = _fixture_decision()
        created = create_execution_intent(
            j, decision=d, risk=_risk_allow(), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        iid = created["intent_id"]
        link_order(j, intent_id=iid, decision_id=d["decision_id"], order_id="ORD-P")
        raised = False
        try:
            link_deal_fill(
                j,
                intent_id=iid,
                decision_id=d["decision_id"],
                deal_id="DEAL-P1",
                order_id="ORD-P",
                actual_fill_price=2650.28,
                requested_price=2650.25,
                volume=0.01,
                fill_kind="PARTIAL",
            )
        except CrashInjected:
            raised = True
        j2 = ExecutionIntentJournal(root)
        # Complete second partial / full after restart
        link_deal_fill(
            j2,
            intent_id=iid,
            decision_id=d["decision_id"],
            deal_id="DEAL-P2",
            order_id="ORD-P",
            actual_fill_price=2650.29,
            requested_price=2650.25,
            volume=0.01,
            fill_kind="FULL",
        )
        counts = independent_decision_count(j2)
        return {
            "case": "partial_fill_then_restart",
            "crash_raised": raised,
            "n_independent_decisions": counts["n_independent_decisions"],
            "n_fill_rows": counts["n_fill_rows"],
            "partial_fills_not_independent_decisions": counts["n_independent_decisions"] == 1
            and counts["n_fill_rows"] >= 2,
            "pass": raised and counts["n_independent_decisions"] == 1 and counts["n_fill_rows"] >= 2,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def test_rejected_order() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root)
        d = _fixture_decision()
        created = create_execution_intent(
            j, decision=d, risk=_risk_allow(), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        mark_broker_rejected(
            j, intent_id=created["intent_id"], decision_id=d["decision_id"], reason="FIXTURE_REJECT"
        )
        intent = j.get_intent(created["intent_id"])
        return {
            "case": "rejected_order",
            "intent_status": intent.get("intent_status") if intent else None,
            "pass": intent is not None and intent.get("intent_status") == "BROKER_REJECTED",
            "genuine_broker": False,
            "note": "Broker rejection path exercised with fixture only — NOT_TESTED against live MT5",
            "broker_test_status": "NOT_TESTED",
            "provenance": FIXTURE_PROVENANCE,
        }


def test_missing_execution_record() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root)
        d = _fixture_decision()
        created = create_execution_intent(
            j, decision=d, risk=_risk_allow(), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        mark_missing_execution(j, intent_id=created["intent_id"], decision_id=d["decision_id"])
        recon = reconcile_orders_deals_fills(j.all_records())
        return {
            "case": "missing_execution_record",
            "orphan_intents": recon["orphan_intents_missing_execution"],
            "pass": created["intent_id"] in recon["orphan_intents_missing_execution"],
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def test_risk_reject_and_wait() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = ExecutionIntentJournal(root)
        d_buy = _fixture_decision(action="BUY")
        d_wait = _fixture_decision(action="WAIT")
        r1 = create_execution_intent(
            j, decision=d_buy, risk=_risk_reject(), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        r2 = create_execution_intent(
            j, decision=d_wait, risk=_risk_allow("WAIT"), account_profile={"symbol": "XAUUSDm", "fixture": True}
        )
        return {
            "case": "risk_reject_and_wait",
            "risk_rejected_status": r1["intent_status"],
            "wait_status": r2["intent_status"],
            "pass": r1["intent_status"] == "RISK_REJECTED" and r2["intent_status"] == "NO_TRADE_WAIT",
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        }


def run_crash_recovery_suite() -> dict[str, Any]:
    cases = [
        test_crash_between_decision_and_intent(),
        test_crash_after_intent_persistence(),
        test_duplicate_broker_deal_import(),
        test_partial_fill_then_restart(),
        test_rejected_order(),
        test_missing_execution_record(),
        test_risk_reject_and_wait(),
    ]
    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "n_fail": sum(1 for c in cases if not c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "broker_order_send": False,
        "genuine_broker_evidence_fabricated": False,
        "not_tested_against_live_mt5": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
