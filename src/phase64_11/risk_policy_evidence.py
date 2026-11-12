"""DEMO risk-policy evidence classification — engineering vs broker-dependent."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    POLICY_EVIDENCE_VERSION,
    UNAPPROVED,
    VERIFIED_CURRENCY,
    VERIFIED_DEMO_BALANCE,
    canonical_json_sha256,
)

BROKER_FACT = "BROKER_FACT"
ENGINEERING_SAFETY_POLICY = "ENGINEERING_SAFETY_POLICY"
STRATEGY_POLICY = "STRATEGY_POLICY"
RESEARCH_PARAMETER = "RESEARCH_PARAMETER"
UNKNOWN = "UNKNOWN"

APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"
PROPOSED = "PROPOSED"
BLOCKED_BY_UNKNOWN = "BLOCKED_BY_UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"


def _param(
    name: str,
    *,
    unit: str,
    formula: str,
    rationale: str,
    source: str,
    broker_dependency: str,
    strategy_dependency: str,
    safety_policy_dependency: str,
    experimental_validation: str,
    determinism: str,
    kind: str,
    status: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "parameter": name,
        "value": value,
        "unit": unit,
        "formula": formula,
        "rationale": rationale,
        "source": source,
        "broker_dependency": broker_dependency,
        "strategy_dependency": strategy_dependency,
        "safety_policy_dependency": safety_policy_dependency,
        "experimental_validation_status": experimental_validation,
        "determinism": determinism,
        "kind": kind,
        "status": status,
    }


def build_risk_policy_evidence(*, balance: float = VERIFIED_DEMO_BALANCE) -> dict[str, Any]:
    bal = float(balance)
    cur = VERIFIED_CURRENCY
    params = [
        _param(
            "max_risk_per_trade",
            value=round(bal * 0.005, 4),
            unit=cur,
            formula="0.005 * verified_demo_balance",
            rationale="Cap single SL risk at 0.5% demo balance",
            source="VERIFIED_DEMO_BALANCE",
            broker_dependency="Requires computable SL monetary risk (tick_value VERIFIED; commission UNKNOWN affects total)",
            strategy_dependency="Independent of edge claim",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED_FOR_ENGINEERING_SAFETY_DEFAULT",
            determinism="Deterministic given balance + SL risk inputs; blocked if cost incompleteness hides true downside",
            kind=ENGINEERING_SAFETY_POLICY,
            status=BLOCKED_BY_UNKNOWN,
        ),
        _param(
            "max_aggregate_open_risk",
            value=round(bal * 0.015, 4),
            unit=cur,
            formula="0.015 * verified_demo_balance",
            rationale="Cap simultaneous open SL risk",
            source="VERIFIED_DEMO_BALANCE",
            broker_dependency="Margin incompleteness affects whether aggregate exposure is safe",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED_FOR_ENGINEERING_SAFETY_DEFAULT",
            determinism="Deterministic formula; gated by margin UNKNOWN",
            kind=ENGINEERING_SAFETY_POLICY,
            status=BLOCKED_BY_UNKNOWN,
        ),
        _param(
            "daily_loss_limit",
            value=round(bal * 0.02, 4),
            unit=cur,
            formula="0.02 * verified_demo_balance",
            rationale="Halt after 2% daily loss",
            source="VERIFIED_DEMO_BALANCE",
            broker_dependency="None for limit definition",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED_FOR_ENGINEERING_SAFETY_DEFAULT",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "max_drawdown",
            value=round(bal * 0.08, 4),
            unit=cur,
            formula="0.08 * starting_or_peak_equity",
            rationale="8% drawdown circuit",
            source="VERIFIED_DEMO_BALANCE",
            broker_dependency="None for limit definition",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED_FOR_ENGINEERING_SAFETY_DEFAULT",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "max_concurrent_positions",
            value=1,
            unit="positions",
            formula="constant_1",
            rationale="Single position until genuine fill recon exists",
            source="Phase64.8 NONE_TRADE_FILLS",
            broker_dependency="None",
            strategy_dependency="Conservative until multi-position recon proven",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "spread_guard",
            value={"max_spread_points": 500, "max_spread_atr_ratio": 0.35},
            unit="points_and_ratio",
            formula="reject if spread_points>max",
            rationale="Block abnormal floating spread",
            source="Live spread snapshot ~240 + headroom",
            broker_dependency="Uses LIVE_ACCOUNT spread",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED",
            determinism="Deterministic on live quote",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "stale_tick_threshold",
            value=120,
            unit="seconds",
            formula="tick_age_sec <= 120",
            rationale="Reject stale quotes",
            source="Phase64.6/64.9 precedent",
            broker_dependency="Uses LIVE_ACCOUNT tick time",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="NOT_REQUIRED",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "daily_trade_limit",
            value=3,
            unit="execution_attempts",
            formula="attempts_per_utc_day <= 3",
            rationale="Hard cap while economics incomplete",
            source="Conservative DEMO posture",
            broker_dependency="None",
            strategy_dependency="Research throttle",
            safety_policy_dependency="Safety + research",
            experimental_validation="NOT_REQUIRED",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "consecutive_loss_breaker",
            value=2,
            unit="consecutive_losses",
            formula="pause if consecutive_losses >= 2",
            rationale="Early circuit on DEMO",
            source="Conservative DEMO posture",
            broker_dependency="Requires broker outcomes when live; paper must not trip broker breaker",
            strategy_dependency="Research",
            safety_policy_dependency="Safety",
            experimental_validation="NOT_REQUIRED",
            determinism="Deterministic given outcome stream",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "margin_safety_threshold",
            value={"min_free_margin_usd": round(bal * 0.5, 2), "min_margin_level_pct": 500},
            unit="usd_and_percent",
            formula="free_margin>=min; margin_level>=min when margin_used>0",
            rationale="Buffer free margin; exact required margin UNKNOWN",
            source="VERIFIED equity + INCOMPLETE margin model",
            broker_dependency="CRITICAL — required margin UNKNOWN",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="BLOCKED — depends on unknown broker margin",
            determinism="Incomplete without required margin",
            kind=ENGINEERING_SAFETY_POLICY,
            status=BLOCKED_BY_UNKNOWN,
        ),
        _param(
            "session_guard",
            value="REQUIRE_VERIFIED_IN_SESSION",
            unit="enum",
            formula="sessions_verified AND in_session",
            rationale="Do not trade on UNKNOWN schedule",
            source="Sessions UNKNOWN",
            broker_dependency="CRITICAL — sessions unknown",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="BLOCKED",
            determinism="Fail-closed while UNKNOWN",
            kind=ENGINEERING_SAFETY_POLICY,
            status=BLOCKED_BY_UNKNOWN,
        ),
        _param(
            "swap_overnight_guard",
            value="UNKNOWN_FOR_EXECUTION_BLOCKS_UNBOUNDED_OVERNIGHT",
            unit="enum",
            formula="block unbounded overnight while swap unresolved",
            rationale="Swap conflict / charged swap unproven",
            source="Swap UNKNOWN_FOR_EXECUTION",
            broker_dependency="CRITICAL",
            strategy_dependency="Hold horizon",
            safety_policy_dependency="Core safety",
            experimental_validation="BLOCKED",
            determinism="Fail-closed",
            kind=ENGINEERING_SAFETY_POLICY,
            status=BLOCKED_BY_UNKNOWN,
        ),
        _param(
            "emergency_shutdown",
            value="ENGAGE_KILL_SWITCH_BLOCK_ALL_SUBMISSIONS",
            unit="enum",
            formula="critical_incident → kill_switch",
            rationale="Immediate block; disengage ≠ authorize order_send",
            source="Phase64.4 kill switch",
            broker_dependency="None",
            strategy_dependency="None",
            safety_policy_dependency="Core safety",
            experimental_validation="Design-validated",
            determinism="Deterministic",
            kind=ENGINEERING_SAFETY_POLICY,
            status=PROPOSED,
        ),
        _param(
            "stopout_call_level_observed",
            value=60.0,
            unit="percent",
            formula="account.margin_so_call",
            rationale="Broker-observed margin call level",
            source="LIVE_ACCOUNT account_info",
            broker_dependency="BROKER_FACT",
            strategy_dependency="None",
            safety_policy_dependency="Informational for margin stress",
            experimental_validation="LIVE_OBSERVED",
            determinism="Observed",
            kind=BROKER_FACT,
            status=PROPOSED,
        ),
    ]

    blocked = [p["parameter"] for p in params if p["status"] == BLOCKED_BY_UNKNOWN]
    overall = APPROVED_FOR_DEMO if not blocked else UNAPPROVED

    out = {
        "policy_evidence_version": POLICY_EVIDENCE_VERSION,
        "overall_approval_status": overall,
        "authorizes_execution": False,
        "note": (
            "Engineering safety defaults may be PROPOSED without trading history; "
            "parameters depending on unknown broker economics remain BLOCKED_BY_UNKNOWN. "
            "Passing software tests is not approval evidence."
        ),
        "parameters": params,
        "blocked_parameters": blocked,
        "kinds": [BROKER_FACT, ENGINEERING_SAFETY_POLICY, STRATEGY_POLICY, RESEARCH_PARAMETER, UNKNOWN],
        "statuses": [APPROVED_FOR_DEMO, PROPOSED, BLOCKED_BY_UNKNOWN, NOT_APPLICABLE],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
