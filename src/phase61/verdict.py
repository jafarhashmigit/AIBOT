"""Evidence-based Phase 61 verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    identity: dict[str, Any],
    commission: dict[str, Any],
    slippage: dict[str, Any],
    sufficiency: dict[str, Any],
    integrity: dict[str, Any],
    capability: dict[str, Any],
    holdout_sealed: bool,
    null_ok: bool,
    tests_ok: bool,
) -> tuple[str, str]:
    if not holdout_sealed or not null_ok:
        return "EXNESS_EXECUTION_EVIDENCE_BLOCKED", "Holdout seal or NullPolicy check failed"
    if not integrity.get("checks_pass"):
        return "EXNESS_EXECUTION_EVIDENCE_BLOCKED", "Phase integrity audit failed"
    if not tests_ok:
        return "EXNESS_EXECUTION_EVIDENCE_BLOCKED", "Phase61 tests failed"

    account_unknown = identity.get("account_type") == "UNKNOWN"
    commission_unknown = commission.get("commission_status") == "UNKNOWN"
    slippage_unknown = slippage.get("actual_slippage_status") == "UNKNOWN"
    sufficient = bool(sufficiency.get("sufficient_for_account_specific_cost_model"))

    if (
        not account_unknown
        and identity.get("verification_status") == "VERIFIED"
        and not commission_unknown
        and not slippage_unknown
        and sufficient
        and capability.get("can_collect_actual_demo_fills_without_live_orders")
    ):
        return (
            "EXNESS_EXECUTION_EVIDENCE_VALIDATED",
            "Account-specific Exness execution-cost evidence sufficient for stated claims",
        )

    reasons = []
    if account_unknown:
        reasons.append("account_type UNKNOWN")
    if commission_unknown:
        reasons.append("commission_status UNKNOWN")
    if slippage_unknown:
        reasons.append("actual_slippage UNKNOWN")
    if not sufficient:
        reasons.append("evidence sample insufficient")
    if not capability.get("can_collect_actual_demo_fills_without_live_orders"):
        reasons.append("demo fill collection integration missing")
    return "EXNESS_EXECUTION_EVIDENCE_PARTIAL", "Material unknowns remain: " + "; ".join(reasons)
