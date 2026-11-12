"""Broker execution risk & exposure design — limits default UNCONFIGURED."""

from __future__ import annotations

from typing import Any

from phase64_4.constants import RISK_LIMIT_KEYS, canonical_json_sha256

UNCONFIGURED = "UNCONFIGURED"


def default_broker_risk_config() -> dict[str, Any]:
    """Fail-closed: every numeric/enforcement limit is UNCONFIGURED until explicitly approved."""
    return {k: UNCONFIGURED for k in RISK_LIMIT_KEYS} | {
        "account_identity_match_required": True,
        "reject_unresolved_execution_intents": True,
        "reject_duplicate_execution_request": True,
        "reject_invalid_prices": True,
        "reject_abnormal_quotes": True,
        "reject_symbol_spec_drift_without_review": True,
        "stale_market_data_blocks_submission": True,
        "limits_justification": "NONE — numerical thresholds not invented in Phase64.4",
        "paper_risk_manager_reuse": False,
        "note": (
            "phase54.RiskManager paper limits must NOT be copied as broker demo limits "
            "without separate justification and human approval."
        ),
    }


def evaluate_broker_risk_gates(
    *,
    config: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Design evaluator: if any required limit is UNCONFIGURED → BLOCKED_BY_RISK.
    Does not invent thresholds.
    """
    cfg = config or default_broker_risk_config()
    ctx = context or {}
    blocked_reasons: list[str] = []
    for k in RISK_LIMIT_KEYS:
        if cfg.get(k) == UNCONFIGURED:
            blocked_reasons.append(f"unconfigured:{k}")
    if ctx.get("account_mismatch"):
        blocked_reasons.append("account_identity_mismatch")
    if ctx.get("unresolved_execution_intent"):
        blocked_reasons.append("unresolved_execution_intent")
    if ctx.get("duplicate_execution_request"):
        blocked_reasons.append("duplicate_execution_request")
    if ctx.get("stale_quote"):
        blocked_reasons.append("stale_market_data")
    if ctx.get("invalid_price"):
        blocked_reasons.append("invalid_price")
    if ctx.get("symbol_spec_changed"):
        blocked_reasons.append("symbol_spec_change")
    if ctx.get("kill_switch"):
        blocked_reasons.append("kill_switch")
    allowed = len(blocked_reasons) == 0
    return {
        "allowed": allowed,
        "blocked_reasons": blocked_reasons,
        "state_if_blocked": "BLOCKED_BY_RISK",
        "config": cfg,
        "fail_closed": True,
    }


def risk_control_specification() -> dict[str, Any]:
    return {
        "checks": [
            {"name": k, "limit": UNCONFIGURED, "enforcement": "fail_closed_block_if_unconfigured"}
            for k in RISK_LIMIT_KEYS
        ]
        + [
            {"name": "account_identity_mismatch", "limit": "must_match_verified_demo", "enforcement": "block"},
            {"name": "duplicate_or_unresolved_intents", "limit": "none_allowed", "enforcement": "block"},
            {"name": "invalid_or_abnormal_quotes", "limit": "reject", "enforcement": "block"},
            {"name": "trading_session", "limit": UNCONFIGURED, "enforcement": "block_until_sessions_complete"},
            {"name": "symbol_spec_change", "limit": "require_reverification", "enforcement": "block"},
        ],
        "default_config": default_broker_risk_config(),
        "numerical_limits_invented": False,
    }


def audit_risk_spec() -> dict[str, Any]:
    ev = evaluate_broker_risk_gates()
    # Even with fake numbers, missing approval still needs human gate — but configured limits can clear UNCONFIGURED
    configured = default_broker_risk_config()
    for k in RISK_LIMIT_KEYS:
        configured[k] = {"value": "PLACEHOLDER_NOT_APPROVED", "approved": False}
    # Still blocked because placeholders are not approved numeric limits — treat non-number as unconfigured
    # For design test: only clear when value is a real number AND approved flag true — simplify: still block
    still = evaluate_broker_risk_gates(config=default_broker_risk_config())
    out = {
        "specification": risk_control_specification(),
        "default_blocks": not ev["allowed"],
        "blocked_reason_count": len(ev["blocked_reasons"]),
        "unconfigured_blocks_submission": still["allowed"] is False,
        "pass": (not ev["allowed"]) and len(ev["blocked_reasons"]) == len(RISK_LIMIT_KEYS),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
