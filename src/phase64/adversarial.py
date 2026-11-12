"""Adversarial checks for Phase64 readiness scaffold."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64.constants import FIXTURE_PROVENANCE, canonical_json_sha256
from phase64.evidence_integrity import audit_cost_fields, audit_fill_versus_request
from phase64.execution_intent import ExecutionIntentJournal, create_execution_intent
from phase64.linkage import independent_decision_count, link_deal_fill, link_order


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # 1) Unknown costs must not become zero
    c1 = audit_cost_fields(
        {"commission": 0, "commission_source": "MISSING", "fee": None, "swap": None, "slippage": None, "latency_ms": None}
    )
    cases.append(
        {
            "name": "unknown_commission_not_zero",
            "pass": (not c1["unknown_not_zero"]) or c1["normalized"]["commission"] == "UNKNOWN",
            # Prefer: detecting issue OR normalizing to UNKNOWN
            "detail": c1,
        }
    )
    # Tighten: if source MISSING and value 0 → issue flagged and normalized UNKNOWN
    cases[-1]["pass"] = "commission_zero_without_evidence" in c1["issues"] and c1["normalized"]["commission"] == "UNKNOWN"

    # 2) Partial fills must not inflate independent decisions
    with tempfile.TemporaryDirectory() as td:
        j = ExecutionIntentJournal(Path(td))
        d = {
            "decision_id": "dec_partial_adv",
            "timestamp_utc": "2026-11-11T12:00:00Z",
            "action": "BUY",
            "proposed_action": "BUY",
            "instrument": "XAUUSDm",
            "observation_id": "obs1",
            "market_state_id": "XAUUSDm:M5:t",
            "execution_assumptions": {"bid_ref": 1.0, "ask_ref": 1.1},
        }
        created = create_execution_intent(
            j,
            decision=d,
            risk={"allowed": True, "final_action": "BUY", "reasons": []},
            account_profile={"symbol": "XAUUSDm", "fixture": True},
        )
        link_order(j, intent_id=created["intent_id"], decision_id=d["decision_id"], order_id="O1")
        link_deal_fill(
            j,
            intent_id=created["intent_id"],
            decision_id=d["decision_id"],
            deal_id="D1",
            order_id="O1",
            actual_fill_price=1.11,
            requested_price=1.1,
            volume=0.01,
            fill_kind="PARTIAL",
        )
        link_deal_fill(
            j,
            intent_id=created["intent_id"],
            decision_id=d["decision_id"],
            deal_id="D2",
            order_id="O1",
            actual_fill_price=1.12,
            requested_price=1.1,
            volume=0.01,
            fill_kind="FULL",
        )
        counts = independent_decision_count(j)
        cases.append(
            {
                "name": "partial_fills_one_decision",
                "pass": counts["n_independent_decisions"] == 1 and counts["n_fill_rows"] == 2,
                "detail": counts,
            }
        )

    # 3) Cannot claim genuine broker linkage via fabrication
    with tempfile.TemporaryDirectory() as td:
        j = ExecutionIntentJournal(Path(td))
        blocked = False
        try:
            link_order(
                j,
                intent_id="x",
                decision_id="y",
                order_id="Z",
                genuine_broker=True,
            )
        except ValueError as e:
            blocked = "genuine_broker" in str(e)
        cases.append({"name": "block_fabricated_genuine_broker_flag", "pass": blocked})

    # 4) order_send remains prohibited
    cases.append(
        {
            "name": "order_send_prohibited",
            "pass": "order_send" in PROHIBITED_MT5_API,
        }
    )

    # 5) Contradictory rejected+fill flagged
    c5 = audit_fill_versus_request(
        {
            "side": "BUY",
            "requested_price": 10.0,
            "actual_fill_price": 10.1,
            "rejection_or_execution_status": "REJECTED",
            "commission": None,
            "fee": None,
            "swap": None,
        }
    )
    cases.append(
        {
            "name": "rejected_with_fill_contradiction",
            "pass": "fill_present_on_rejected_order" in c5["contradictions"],
            "detail": c5,
        }
    )

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "pass": all(c.get("pass") for c in cases),
        "provenance": FIXTURE_PROVENANCE,
        "fabricated_genuine_evidence": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
