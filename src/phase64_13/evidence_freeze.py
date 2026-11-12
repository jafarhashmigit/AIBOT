"""Freeze Phase 64.11 broker-economics evidence boundaries — sessions updated via 64.12."""

from __future__ import annotations

from typing import Any

from phase64_13.constants import (
    COST_MODEL_INCOMPLETE,
    EVIDENCE_FREEZE_VERSION,
    UNAPPROVED,
    canonical_json_sha256,
)


def broker_evidence_freeze() -> dict[str, Any]:
    """
    Preserve Phase 64.11 classifications. Sessions elevated to VALIDATED by Phase 64.12
    (hours) + Phase 64.13 (CLOSE_ONLY semantics). Do not re-investigate commission/margin/swap.
    """
    rows = [
        {
            "blocker": "Commission",
            "status": "UNKNOWN",
            "evidence_boundary": "REQUIRES_GENUINE_ACCOUNT_EVENT",
            "preserved_from": "phase64_11",
            "closure_condition": (
                "Genuine XAUUSDm trade deal commission field OR verified account-type schedule binding"
            ),
            "future_genuine_evidence": "Trade deal on this account with commission field",
            "manufactured": False,
        },
        {
            "blocker": "Margin",
            "status": "INCOMPLETE",
            "evidence_boundary": "STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT",
            "preserved_from": "phase64_11",
            "closure_condition": (
                "Observed margin on real position/order OR approved read-only margin-calc API"
            ),
            "future_genuine_evidence": "Open position showing account.margin for known volume/price",
            "manufactured": False,
        },
        {
            "blocker": "Swap",
            "status": "UNKNOWN_FOR_EXECUTION",
            "evidence_boundary": "REQUIRES_GENUINE_ACCOUNT_EVENT",
            "preserved_from": "phase64_11",
            "closure_condition": (
                "Overnight charged swap on genuine deal and/or dated swap-history reconciling "
                "-488.7 vs -644.8"
            ),
            "future_genuine_evidence": "Overnight XAUUSDm deal with swap field",
            "manufactured": False,
            "conflict_preserved": True,
        },
        {
            "blocker": "Sessions",
            "status": "VALIDATED",
            "evidence_boundary": "AUTHORITATIVE_EXTERNAL_EVIDENCE",
            "preserved_from": "phase64_12 + phase64_13 CLOSE_ONLY semantics",
            "closure_condition": "Satisfied for schedule + CLOSE_ONLY distinction",
            "future_genuine_evidence": "Optional holiday instrument-specific notices",
            "manufactured": False,
        },
        {
            "blocker": "Cost model",
            "status": "INCOMPLETE",
            "evidence_boundary": "REQUIRES_GENUINE_ACCOUNT_EVENT",
            "preserved_from": "phase64_11",
            "closure_condition": "COST_MODEL_VALIDATED requirements (commission/swap/conversion…)",
            "future_genuine_evidence": "Close commission + swap (+ conversion) boundaries first",
            "manufactured": False,
        },
        {
            "blocker": "Risk policy",
            "status": UNAPPROVED,
            "evidence_boundary": "PARTIALLY_DEPENDENT_ON_UNRESOLVED_ECONOMICS",
            "preserved_from": "phase64_11",
            "closure_condition": (
                "All critical safety deps deterministic; blocked params unblocked — "
                "session validation alone is insufficient"
            ),
            "future_genuine_evidence": "Resolve commission/margin/swap then re-evaluate APPROVED_FOR_DEMO",
            "manufactured": False,
            "session_validation_approves_policy": False,
        },
    ]
    out = {
        "freeze_version": EVIDENCE_FREEZE_VERSION,
        "source_matrix": "reports/phase64_11/EVIDENCE_BOUNDARY_MATRIX.md",
        "repeated_commission_margin_swap_search": False,
        "cost_model": COST_MODEL_INCOMPLETE,
        "risk_policy": UNAPPROVED,
        "rows": rows,
        "n_rows": len(rows),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def risk_policy_status() -> dict[str, Any]:
    return {
        "overall": UNAPPROVED,
        "session_validation_alone_insufficient": True,
        "engineering_safety_controls": "PROPOSED_SEPARATE",
        "broker_dependent_controls": "BLOCKED_BY_UNKNOWN",
        "strategy_dependent_controls": "NOT_APPROVED",
        "research_parameters": "NOT_APPROVAL_EVIDENCE",
        "thresholds_modified_for_approval": False,
        "authorizes_execution": False,
    }
