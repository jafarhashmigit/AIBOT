"""Canonical evidence-boundary matrix — primary Phase 64.11 deliverable."""

from __future__ import annotations

from typing import Any

from phase64_11.commission_boundary import investigate_commission_boundary
from phase64_11.constants import (
    ALREADY_VALIDATED,
    BOUNDARY_CLASSES,
    BOUNDARY_VERSION,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    canonical_json_sha256,
)
from phase64_11.cost_taxonomy import build_cost_taxonomy
from phase64_11.margin_boundary import build_margin_boundary
from phase64_11.risk_policy_evidence import build_risk_policy_evidence
from phase64_11.session_boundary import investigate_session_boundary
from phase64_11.swap_forensic import forensic_swap_reconciliation


def build_evidence_boundary_matrix(*, observed_spread_points: float = 240.0) -> dict[str, Any]:
    commission = investigate_commission_boundary(n_trade_deals=0)
    margin = build_margin_boundary()
    sessions = investigate_session_boundary()
    swap = forensic_swap_reconciliation()
    cost = build_cost_taxonomy(observed_spread_points=observed_spread_points)
    policy = build_risk_policy_evidence()

    # Cost model classification: incomplete because deps require events / external / both
    cost_classification = REQUIRES_GENUINE_ACCOUNT_EVENT
    cost_reasoning = (
        "COST_MODEL_VALIDATED requires commission and swap (and conversion) resolved or safely bounded. "
        "Those account-specific cash costs are not closable from current evidence without genuine deals "
        "(and/or verified account-type docs). Spread alone is insufficient."
    )

    # Overall policy approval blocked until broker-dependent economics close.
    policy_classification = REQUIRES_GENUINE_ACCOUNT_EVENT

    already = [
        {
            "blocker": "Live XAUUSDm contract metadata (tick/contract/volumes)",
            "current_state": "VERIFIED",
            "required_evidence": "Already obtained via live RO symbol_info",
            "can_close_without_fill": "YES",
            "classification": ALREADY_VALIDATED,
            "next_evidence": "None for these fields",
            "reasoning": "Phase64.7 LIVE_MT5_METADATA_VERIFIED",
        },
        {
            "blocker": "Preflight architecture",
            "current_state": "PASS",
            "required_evidence": "Phase64.9",
            "can_close_without_fill": "YES",
            "classification": ALREADY_VALIDATED,
            "next_evidence": "None",
            "reasoning": "EXECUTION_PREFLIGHT_VALIDATED",
        },
        {
            "blocker": "RO reconciliation layer",
            "current_state": "PASS",
            "required_evidence": "Phase64.8",
            "can_close_without_fill": "YES",
            "classification": ALREADY_VALIDATED,
            "next_evidence": "Genuine trade fills for fill-recon validation later",
            "reasoning": "BROKER_RO_RECONCILIATION_VALIDATED (empty/balance path)",
        },
    ]

    rows = [
        {
            "blocker": "Commission",
            "current_state": commission["current_state"],
            "required_evidence": "Genuine trade deal commission field OR verified account-type schedule binding",
            "can_close_without_fill": "NO",
            "classification": commission["classification"],
            "next_evidence": commission["next_evidence"],
            "reasoning": commission["reasoning"],
        },
        {
            "blocker": "Margin",
            "current_state": margin["current_state"],
            "required_evidence": "Observed margin on real position/order OR approved margin-calc API",
            "can_close_without_fill": "NO",
            "classification": margin["classification"],
            "next_evidence": margin["next_evidence"],
            "reasoning": margin["reasoning"],
        },
        {
            "blocker": "Sessions",
            "current_state": sessions["current_state"],
            "required_evidence": "Authoritative dated session schedule with timezone/DST OR permitted session API",
            "can_close_without_fill": "YES",
            "classification": sessions["classification"],
            "next_evidence": sessions["next_evidence"],
            "reasoning": sessions["reasoning"],
        },
        {
            "blocker": "Swap",
            "current_state": swap["current_state"],
            "required_evidence": "Overnight charged swap on genuine deal and/or dated swap-history reconciling conflict",
            "can_close_without_fill": "NO",
            "classification": swap["classification"],
            "next_evidence": swap["next_evidence"],
            "reasoning": swap["reasoning"],
        },
        {
            "blocker": "Cost model",
            "current_state": cost["current_state"],
            "required_evidence": "COST_MODEL_VALIDATED requirements (spread+bounded slippage+commission+swap+conversion)",
            "can_close_without_fill": "NO",
            "classification": cost_classification,
            "next_evidence": "Close commission + swap (+ conversion) evidence boundaries first",
            "reasoning": cost_reasoning,
        },
        {
            "blocker": "Risk policy",
            "current_state": policy["overall_approval_status"],
            "required_evidence": "All critical safety deps deterministic; blocked params unblocked",
            "can_close_without_fill": "PARTIAL — engineering PROPOSED ok; APPROVED_FOR_DEMO needs economics",
            "classification": policy_classification,
            "next_evidence": (
                "Resolve commission/margin/sessions/swap blockers; then re-evaluate APPROVED_FOR_DEMO. "
                "Do not treat unit-test green as approval."
            ),
            "reasoning": (
                "Several ENGINEERING_SAFETY_POLICY params are PROPOSED from verified balance without fills. "
                "Critical broker-dependent params remain BLOCKED_BY_UNKNOWN → overall UNAPPROVED."
            ),
        },
    ] + already

    consistent = all(r["classification"] in BOUNDARY_CLASSES for r in rows)

    out = {
        "boundary_version": BOUNDARY_VERSION,
        "rows": rows,
        "n_rows": len(rows),
        "artifacts": {
            "commission": commission,
            "margin": margin,
            "sessions": sessions,
            "swap": swap,
            "cost": cost,
            "risk_policy": policy,
        },
        "matrix_consistent": consistent,
        "forced_closure": False,
        "primary_deliverable": True,
    }
    out["sha256"] = canonical_json_sha256(
        {k: v for k, v in out.items() if k not in ("sha256", "artifacts")}
    )
    return out
