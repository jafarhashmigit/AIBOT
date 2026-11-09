"""Fail-closed permission enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_expired(expiry_utc: str | None, now: datetime | None = None) -> bool:
    exp = _parse_utc(expiry_utc)
    if exp is None:
        return False
    current = now or datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return current >= exp


def evaluate_permission(
    *,
    provider_id: str,
    required_scope: str,
    scope_status: dict[str, str],
    permission_evidence_reference: str | None,
    permission_expiry_utc: str | None,
    requesting_provider_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail-closed authorization decision for a single provider/scope."""
    independence_notes: list[str] = []
    if required_scope == "backtesting_evaluation":
        independence_notes.append("storage_grant_does_not_authorize_backtesting")
    if required_scope == "ai_ml_training":
        independence_notes.append("backtesting_grant_does_not_authorize_ai_ml")
        independence_notes.append("storage_grant_does_not_authorize_ai_ml")

    if requesting_provider_id is not None and requesting_provider_id != provider_id:
        return {
            "decision": "REJECT",
            "provider_id": provider_id,
            "required_scope": required_scope,
            "reasons": ["cross_provider_authorization_forbidden"],
            "independence_notes": independence_notes,
        }

    reasons: list[str] = []
    if not permission_evidence_reference:
        reasons.append("no_permission_evidence")

    if _is_expired(permission_expiry_utc, now=now):
        reasons.append("permission_expired")

    status = scope_status.get(required_scope, "NOT_REQUESTED")
    if status == "REVOKED":
        reasons.append("permission_revoked")
    elif status == "EXPIRED":
        reasons.append("permission_expired")
    elif status == "REJECTED":
        reasons.append("permission_rejected")
    elif status == "PARTIALLY_GRANTED":
        reasons.append(f"scope_only_partial:{required_scope}")
    elif status in ("NOT_REQUESTED", "REQUESTED"):
        reasons.append(f"scope_not_granted:{required_scope}:{status}")
    elif status != "GRANTED":
        reasons.append(f"scope_not_granted:{required_scope}:{status}")

    if not reasons and status == "GRANTED" and permission_evidence_reference:
        return {
            "decision": "ALLOW",
            "provider_id": provider_id,
            "required_scope": required_scope,
            "reasons": [],
            "independence_notes": independence_notes,
        }

    if not reasons:
        reasons.append("fail_closed_default_reject")

    return {
        "decision": "REJECT",
        "provider_id": provider_id,
        "required_scope": required_scope,
        "reasons": reasons,
        "independence_notes": independence_notes,
    }


def assert_scope_independence() -> list[dict[str, Any]]:
    """Demonstrate storage ≠ backtest ≠ AI/ML with synthetic statuses."""
    base = {
        "historical_message_access": "GRANTED",
        "signal_storage": "GRANTED",
        "backtesting_evaluation": "NOT_REQUESTED",
        "data_retention": "GRANTED",
        "ai_ml_training": "NOT_REQUESTED",
    }
    storage = evaluate_permission(
        provider_id="synthetic_alpha",
        required_scope="signal_storage",
        scope_status=base,
        permission_evidence_reference="SYN-IND-1",
        permission_expiry_utc="2099-01-01T00:00:00Z",
    )
    backtest = evaluate_permission(
        provider_id="synthetic_alpha",
        required_scope="backtesting_evaluation",
        scope_status=base,
        permission_evidence_reference="SYN-IND-1",
        permission_expiry_utc="2099-01-01T00:00:00Z",
    )
    ai = evaluate_permission(
        provider_id="synthetic_alpha",
        required_scope="ai_ml_training",
        scope_status={**base, "backtesting_evaluation": "GRANTED"},
        permission_evidence_reference="SYN-IND-1",
        permission_expiry_utc="2099-01-01T00:00:00Z",
    )
    cross = evaluate_permission(
        provider_id="synthetic_alpha",
        required_scope="signal_storage",
        scope_status=base,
        permission_evidence_reference="SYN-IND-1",
        permission_expiry_utc="2099-01-01T00:00:00Z",
        requesting_provider_id="synthetic_beta",
    )
    return [
        {"name": "storage_allowed_when_granted", "result": storage},
        {"name": "backtest_rejected_without_explicit_grant", "result": backtest},
        {"name": "ai_ml_rejected_even_if_backtest_granted", "result": ai},
        {"name": "cross_provider_rejected", "result": cross},
    ]


def run_enforcement_suite(scenarios: dict[str, Any]) -> dict[str, Any]:
    results = []
    for name, sc in scenarios.items():
        checks = {}
        for scope in (
            "signal_storage",
            "backtesting_evaluation",
            "ai_ml_training",
            "historical_message_access",
        ):
            checks[scope] = evaluate_permission(
                provider_id=sc["provider_id"],
                required_scope=scope,
                scope_status=sc["scope_status"],
                permission_evidence_reference=sc.get("permission_evidence_reference"),
                permission_expiry_utc=sc.get("permission_expiry_utc"),
            )
        results.append(
            {
                "scenario": name,
                "description": sc.get("description"),
                "checks": checks,
            }
        )
    return {
        "fail_closed": True,
        "scenario_results": results,
        "independence_cases": assert_scope_independence(),
    }
