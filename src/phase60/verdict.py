"""Evidence-based Phase 60 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    phase59_audit: dict[str, Any],
    remaining: dict[str, Any],
    coverage: dict[str, Any],
    commission: dict[str, Any],
    slippage_method: dict[str, Any],
    experience: dict[str, Any],
    holdout_sealed: bool,
    null_ok: bool,
    tests_ok: bool,
) -> tuple[str, str]:
    if not holdout_sealed or not null_ok:
        return "EXECUTION_REALITY_BLOCKED", "Holdout seal or NullPolicy safety check failed"
    if not phase59_audit.get("all_critical_checks_pass"):
        return "EXECUTION_REALITY_BLOCKED", "Phase59 independent artifact audit failed critical checks"
    if not experience.get("checks_pass", True):
        return "EXECUTION_REALITY_BLOCKED", "Experience store integrity failure"
    if not tests_ok:
        return "EXECUTION_REALITY_BLOCKED", "Phase60 tests failed"

    remaining_fail = int(remaining.get("n_fail") or 0)
    commission_unknown = commission.get("commission_status") == "UNKNOWN"
    slippage_actual_unknown = slippage_method.get("actual_slippage_status") == "UNKNOWN"
    hundred = bool(coverage.get("hundred_day_coverage_claim_permitted"))

    # VALIDATED only if critical execution assumptions genuinely established
    if (
        hundred
        and not commission_unknown
        and not slippage_actual_unknown
        and remaining_fail == 0
    ):
        return (
            "EXECUTION_REALITY_VALIDATED",
            "All critical execution evidence established including commission and actual slippage",
        )

    # BLOCKED if remaining days cannot be audited at all / not locatable
    if not phase59_audit.get("all_remaining_locatable"):
        return (
            "EXECUTION_REALITY_BLOCKED",
            "One or more of the remaining 10 union days could not be located for deep audit",
        )

    # PARTIAL is expected when commission/slippage remain UNKNOWN even if audits pass
    reasons = []
    if commission_unknown:
        reasons.append("commission UNKNOWN")
    if slippage_actual_unknown:
        reasons.append("actual slippage UNKNOWN")
    if not hundred:
        reasons.append("100-day deep coverage claim not permitted")
    if remaining_fail:
        reasons.append(f"{remaining_fail} remaining-day audit failures")
    return (
        "EXECUTION_REALITY_PARTIAL",
        "Material unknowns remain: " + "; ".join(reasons),
    )
