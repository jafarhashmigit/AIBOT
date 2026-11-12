"""Conservative DEMO risk policy — PROPOSED components; overall UNAPPROVED while critical deps unresolved."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    APPROVED_FOR_DEMO,
    BLOCKED_BY_UNKNOWN,
    PROPOSED,
    RISK_POLICY_VERSION,
    UNAPPROVED,
    UNKNOWN,
    VERIFIED_CURRENCY,
    VERIFIED_DEMO_BALANCE,
    canonical_json_sha256,
)


def _limit(
    *,
    name: str,
    value: Any,
    unit: str,
    formula: str,
    rationale: str,
    source: str,
    conservative_interpretation: str,
    status: str,
    test_id: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "formula": formula,
        "rationale": rationale,
        "source": source,
        "conservative_interpretation": conservative_interpretation,
        "status": status,
        "test_coverage_id": test_id,
    }


def build_demo_risk_policy(
    *,
    balance: float = VERIFIED_DEMO_BALANCE,
    currency: str = VERIFIED_CURRENCY,
    commission_resolved: bool = False,
    margin_complete: bool = False,
    sessions_verified: bool = False,
    swap_resolved: bool = False,
) -> dict[str, Any]:
    """
    Numerical proposals derived only from verified demo balance/currency.
    Critical unknown deps keep components BLOCKED_BY_UNKNOWN or overall UNAPPROVED.
    """
    bal = float(balance)
    # Conservative fractions of verified demo equity/balance
    per_trade_pct = 0.005  # 0.5%
    aggregate_pct = 0.015  # 1.5%
    daily_loss_pct = 0.02  # 2%
    drawdown_pct = 0.08  # 8%

    components = [
        _limit(
            name="per_trade_risk",
            value=round(bal * per_trade_pct, 4),
            unit=currency,
            formula=f"{per_trade_pct} * verified_demo_balance",
            rationale="Cap single SL risk at 0.5% of verified demo balance",
            source="VERIFIED_DEMO_BALANCE + conservative research default",
            conservative_interpretation="Reject if computed SL monetary risk exceeds value",
            status=PROPOSED if (commission_resolved and margin_complete) else BLOCKED_BY_UNKNOWN,
            test_id="excessive_aggregate_or_per_trade_risk",
        ),
        _limit(
            name="aggregate_risk",
            value=round(bal * aggregate_pct, 4),
            unit=currency,
            formula=f"{aggregate_pct} * verified_demo_balance",
            rationale="Cap simultaneous open SL risk at 1.5%",
            source="VERIFIED_DEMO_BALANCE",
            conservative_interpretation="Sum open SL risks must not exceed",
            status=PROPOSED if margin_complete else BLOCKED_BY_UNKNOWN,
            test_id="excessive_aggregate_risk",
        ),
        _limit(
            name="daily_loss_limit",
            value=round(bal * daily_loss_pct, 4),
            unit=currency,
            formula=f"{daily_loss_pct} * verified_demo_balance",
            rationale="Halt after 2% realized+unrealized daily loss",
            source="VERIFIED_DEMO_BALANCE",
            conservative_interpretation="Include unrealized; fail closed",
            status=PROPOSED,
            test_id="daily_loss_limit",
        ),
        _limit(
            name="drawdown_limit",
            value=round(bal * drawdown_pct, 4),
            unit=currency,
            formula=f"{drawdown_pct} * peak_equity_or_starting_balance",
            rationale="8% peak-to-trough demo circuit",
            source="VERIFIED_DEMO_BALANCE",
            conservative_interpretation="Disable trading until explicit recovery",
            status=PROPOSED,
            test_id="drawdown_limit",
        ),
        _limit(
            name="position_count",
            value=1,
            unit="positions",
            formula="constant_1",
            rationale="Single position until fill recon validated with genuine deals",
            source="Phase64.8 ZERO trade fills + conservative posture",
            conservative_interpretation="Block second concurrent position",
            status=PROPOSED,
            test_id="position_count",
        ),
        _limit(
            name="spread_guard",
            value={"max_spread_points": 500, "max_spread_atr_ratio": 0.35},
            unit="points_and_ratio",
            formula="reject if spread_points > max OR spread/ATR > ratio when ATR known",
            rationale="Block abnormal floating spread; ATR ratio when ATR available",
            source="Live probe observed ~240 points; guard above normal with headroom",
            conservative_interpretation="Missing ATR → use absolute points only; still fail closed on explosion",
            status=PROPOSED,
            test_id="spread_guard",
        ),
        _limit(
            name="stale_data_guard",
            value=120,
            unit="seconds",
            formula="tick_age_sec <= 120",
            rationale="Reject stale quotes",
            source="Phase64.6/64.9 preflight precedent",
            conservative_interpretation="Unknown tick age → reject",
            status=PROPOSED,
            test_id="stale_tick",
        ),
        _limit(
            name="daily_trade_limit",
            value=3,
            unit="execution_attempts",
            formula="count(submission_attempts_per_utc_day) <= 3",
            rationale="Hard cap demo attempts until economics complete",
            source="Conservative DEMO posture",
            conservative_interpretation="Count attempts not only fills",
            status=PROPOSED,
            test_id="daily_trade_limit",
        ),
        _limit(
            name="consecutive_loss_circuit_breaker",
            value=2,
            unit="consecutive_losing_outcomes",
            formula="pause if consecutive_losses >= 2",
            rationale="Early circuit on demo until cost model complete",
            source="Conservative DEMO posture",
            conservative_interpretation="Paper losses do not trip broker breaker; broker outcomes only when authorized",
            status=PROPOSED,
            test_id="consecutive_loss_lockout",
        ),
        _limit(
            name="margin_safety",
            value={"min_free_margin_usd": round(bal * 0.5, 2), "min_margin_level_pct": 500},
            unit="usd_and_percent",
            formula="free_margin >= min AND (margin_level >= min OR no_open_margin)",
            rationale="Require substantial free margin buffer; exact broker margin still INCOMPLETE",
            source="VERIFIED equity + incomplete margin model",
            conservative_interpretation="If required margin UNKNOWN, block orders that depend on margin safety",
            status=BLOCKED_BY_UNKNOWN if not margin_complete else PROPOSED,
            test_id="insufficient_free_margin",
        ),
        _limit(
            name="session_guard",
            value="REQUIRE_VERIFIED_IN_SESSION",
            unit="enum",
            formula="sessions_verified AND in_session",
            rationale="Do not trade on UNKNOWN/PARTIAL schedules",
            source="Phase63 PARTIAL + live API UNKNOWN",
            conservative_interpretation="Always block while programmatic sessions UNKNOWN",
            status=BLOCKED_BY_UNKNOWN if not sessions_verified else PROPOSED,
            test_id="session_unknown",
        ),
        _limit(
            name="swap_guard",
            value="UNKNOWN_FOR_EXECUTION_BLOCKS_OVERNIGHT_HOLD",
            unit="enum",
            formula="block overnight holds while swap conflicting",
            rationale="Conflicting swap_long observations",
            source="Phase63 -488.7 vs Phase64.7 -644.8",
            conservative_interpretation="Intraday-only would still need commission/session; overall policy stays UNAPPROVED",
            status=BLOCKED_BY_UNKNOWN if not swap_resolved else PROPOSED,
            test_id="swap_conflict",
        ),
        _limit(
            name="emergency_shutdown",
            value="ENGAGE_KILL_SWITCH_BLOCK_ALL_SUBMISSIONS",
            unit="enum",
            formula="any(critical_incident) → kill_switch",
            rationale="Immediate block; require explicit recovery",
            source="Phase64.4 kill switch design",
            conservative_interpretation="Disengage does not authorize order_send",
            status=PROPOSED,
            test_id="emergency_shutdown",
        ),
    ]

    critical_blockers = [
        c["name"] for c in components if c["status"] == BLOCKED_BY_UNKNOWN
    ]
    deps_ok = commission_resolved and margin_complete and sessions_verified and swap_resolved
    overall = APPROVED_FOR_DEMO if deps_ok and not critical_blockers else UNAPPROVED

    out = {
        "risk_policy_version": RISK_POLICY_VERSION,
        "environment": "DEMO_ONLY",
        "authorizes_execution": False,
        "approval_status": overall,
        "verified_balance": bal,
        "verified_currency": currency,
        "components": components,
        "critical_blockers": critical_blockers,
        "dependency_flags": {
            "commission_resolved": commission_resolved,
            "margin_complete": margin_complete,
            "sessions_verified": sessions_verified,
            "swap_resolved": swap_resolved,
        },
        "note": (
            "PROPOSED numeric thresholds are research defaults from verified balance; "
            "overall remains UNAPPROVED while commission/margin/sessions/swap unresolved"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def evaluate_policy_gates(
    policy: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed against policy + runtime context."""
    ctx = context or {}
    reasons: list[str] = []
    if policy.get("approval_status") != APPROVED_FOR_DEMO:
        reasons.append("risk_policy_unapproved")
    if policy.get("authorizes_execution"):
        reasons.append("invariant_broken_policy_authorizes")

    # Component lookups
    by_name = {c["name"]: c for c in policy.get("components") or []}

    if ctx.get("stale_tick"):
        reasons.append("stale_data_guard")
    if ctx.get("spread_explosion"):
        reasons.append("spread_guard")
    if ctx.get("insufficient_free_margin"):
        reasons.append("margin_safety")
    if ctx.get("excessive_aggregate_risk"):
        reasons.append("aggregate_risk")
    if ctx.get("daily_loss_breached"):
        reasons.append("daily_loss_limit")
    if ctx.get("drawdown_breached"):
        reasons.append("drawdown_limit")
    if ctx.get("consecutive_loss_lockout"):
        reasons.append("consecutive_loss_circuit_breaker")
    if ctx.get("session_unknown") or ctx.get("outside_session"):
        reasons.append("session_guard")
    if ctx.get("unknown_cost"):
        reasons.append("unknown_cost_blocking")
    if ctx.get("swap_unresolved"):
        reasons.append("swap_guard")

    # Numeric checks when provided
    per = by_name.get("per_trade_risk") or {}
    if ctx.get("per_trade_risk") is not None and isinstance(per.get("value"), (int, float)):
        if float(ctx["per_trade_risk"]) > float(per["value"]):
            reasons.append("per_trade_risk_exceeded")

    allowed = len(reasons) == 0
    return {
        "allowed": allowed,
        "reasons": reasons,
        "fail_closed": True,
        "execution_authorized": False,
    }
