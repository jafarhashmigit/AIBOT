"""Deterministic tests for Phase 64.11 evidence boundary."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_11.boundary_matrix import build_evidence_boundary_matrix
from phase64_11.commission_boundary import investigate_commission_boundary
from phase64_11.constants import (
    BOUNDARY_CLASSES,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE,
    LIVE_ACCOUNT,
    ORDER_SEND,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    SYNTHETIC_TEST,
    UNAPPROVED,
    UNKNOWN,
    USER_REPORTED,
    canonical_json_sha256,
)
from phase64_11.cost_taxonomy import build_cost_taxonomy
from phase64_11.inventory import build_evidence_inventory
from phase64_11.margin_boundary import build_margin_boundary
from phase64_11.risk_policy_evidence import BLOCKED_BY_UNKNOWN, build_risk_policy_evidence
from phase64_11.session_boundary import investigate_session_boundary
from phase64_11.swap_forensic import forensic_swap_reconciliation


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    inv = build_evidence_inventory()
    types = {i["evidence_type"] for i in inv["items"]}
    add("evidence_type_classification", LIVE_ACCOUNT in types and USER_REPORTED in types and SYNTHETIC_TEST in types)

    # published vs account-specific
    c = investigate_commission_boundary()
    add(
        "account_specific_vs_published",
        c["merged"] is False
        and c["account_specific"]["status"] == UNKNOWN
        and c["published"]["mapped_to_trial15_xauusdm"] is False,
    )

    add("unknown_commission_blocking", c["can_close_without_fill"] is False and c["classification"] == REQUIRES_GENUINE_ACCOUNT_EVENT)

    m = build_margin_boundary()
    add(
        "calculated_vs_broker_observed_margin",
        m["layers"]["A_broker_observed"]["evidence_type"] == LIVE_ACCOUNT
        and m["layers"]["C_leverage_estimate"]["usable_as_broker_fact"] is False
        and m["classification"] == STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT,
    )

    s = investigate_session_boundary()
    add(
        "session_evidence_classification",
        s["inferred_from_gaps"] is False
        and s["classification"] == CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE
        and s["can_close_without_fill"] is True,
    )

    sw = forensic_swap_reconciliation()
    add(
        "swap_conflict_preservation",
        sw["overwrite"] is False
        and sw["forensic_table"][0]["value"] == SWAP_LONG_PHASE63
        and sw["forensic_table"][1]["value"] == SWAP_LONG_PHASE64_7
        and sw["reconciled"] is False,
    )

    tax = build_cost_taxonomy()
    add("cost_taxonomy", len(tax["costs"]) == 7 and tax["COST_MODEL_VALIDATED"] is False)

    # unknown-cost propagation
    gating = [x for x in tax["costs"] if x["cost"] == "commission"][0]
    add("unknown_cost_propagation", gating["demo_risk_gating_eligible"] is False and gating["verification_status"] == UNKNOWN)

    pol = build_risk_policy_evidence()
    add(
        "risk_policy_dependency_blocking",
        pol["overall_approval_status"] == UNAPPROVED
        and "margin_safety_threshold" in pol["blocked_parameters"]
        and any(p["status"] == BLOCKED_BY_UNKNOWN for p in pol["parameters"]),
    )

    # conservative bounded-cost: spread eligible, commission not
    spread = next(x for x in tax["costs"] if x["cost"] == "spread")
    add(
        "conservative_bounded_cost_handling",
        spread["demo_risk_gating_eligible"] is True
        and tax["conservative_bounds"]["commission"].startswith("NOT_SAFELY"),
    )

    matrix = build_evidence_boundary_matrix()
    add(
        "evidence_boundary_matrix_consistency",
        matrix["matrix_consistent"]
        and matrix["forced_closure"] is False
        and all(r["classification"] in BOUNDARY_CLASSES for r in matrix["rows"]),
    )

    add("no_order_invariant", "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED")
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    # inventory never marks synthetic as account fact
    syn = [i for i in inv["items"] if i["evidence_type"] == SYNTHETIC_TEST]
    add("synthetic_not_account_fact", all(not i["usable_as_account_execution_fact"] for i in syn))

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
