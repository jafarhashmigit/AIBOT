"""Conservative DEMO-only risk policy design — numerical limits UNAPPROVED."""

from __future__ import annotations

from typing import Any

from phase64_6.constants import RISK_POLICY_VERSION, UNAPPROVED, UNKNOWN, canonical_json_sha256


def propose_demo_risk_policy(*, account_balance: Any = UNKNOWN, account_currency: Any = UNKNOWN) -> dict[str, Any]:
    """
    Derive *proposed* numerical limits only when balance is verified; otherwise leave UNAPPROVED placeholders.
    Never authorizes execution.
    """
    balance_ok = isinstance(account_balance, (int, float)) and float(account_balance) > 0
    currency_ok = account_currency not in (None, "", UNKNOWN)

    # Rationale-based proposals (fractions of balance) — still UNAPPROVED
    proposed = {
        "max_risk_per_decision": {
            "value": round(0.005 * float(account_balance), 4) if balance_ok else UNKNOWN,
            "unit": account_currency if currency_ok else UNKNOWN,
            "rationale": "0.5% of verified demo balance per decision (conservative)",
            "status": UNAPPROVED,
        },
        "max_aggregate_open_risk": {
            "value": round(0.02 * float(account_balance), 4) if balance_ok else UNKNOWN,
            "unit": account_currency if currency_ok else UNKNOWN,
            "rationale": "2% aggregate open risk",
            "status": UNAPPROVED,
        },
        "max_daily_loss": {
            "value": round(0.03 * float(account_balance), 4) if balance_ok else UNKNOWN,
            "unit": account_currency if currency_ok else UNKNOWN,
            "rationale": "3% daily loss halt",
            "status": UNAPPROVED,
        },
        "max_drawdown": {
            "value": round(0.10 * float(account_balance), 4) if balance_ok else UNKNOWN,
            "unit": account_currency if currency_ok else UNKNOWN,
            "rationale": "10% peak-to-trough demo drawdown circuit",
            "status": UNAPPROVED,
        },
        "max_simultaneous_positions": {
            "value": 1,
            "rationale": "Single position until recon/positions_get authorized",
            "status": UNAPPROVED,
        },
        "max_spread_atr": {
            "value": 0.35,
            "rationale": "Reject when spread exceeds 0.35 ATR (paper-era conservative)",
            "status": UNAPPROVED,
        },
        "stale_data_max_age_sec": {
            "value": 120,
            "rationale": "Reject ticks older than 120s",
            "status": UNAPPROVED,
        },
        "market_session_restrictions": {
            "value": "REQUIRE_COMPLETE_SESSIONS_AND_IN_SESSION_ONLY",
            "rationale": "Block when sessions incomplete or outside session",
            "status": UNAPPROVED,
        },
        "daily_trade_limit": {
            "value": 5,
            "rationale": "Hard cap demo trades/day until economics verified",
            "status": UNAPPROVED,
        },
        "consecutive_loss_circuit_breaker": {
            "value": 3,
            "rationale": "Pause after 3 consecutive losing closed trades",
            "status": UNAPPROVED,
        },
        "emergency_shutdown": {
            "value": "ENGAGE_KILL_SWITCH_BLOCK_ALL_SUBMISSIONS",
            "rationale": "Immediate block; reconcile open exposure when RO APIs allow",
            "status": UNAPPROVED,
        },
    }

    all_unapproved = all(
        (v.get("status") == UNAPPROVED) for v in proposed.values() if isinstance(v, dict)
    )
    return {
        "risk_policy_version": RISK_POLICY_VERSION,
        "environment": "DEMO_ONLY",
        "authorizes_execution": False,
        "approval_status": UNAPPROVED,
        "account_balance_used": account_balance if balance_ok else UNKNOWN,
        "account_currency_used": account_currency if currency_ok else UNKNOWN,
        "limits_derived_from_verified_balance": balance_ok and currency_ok,
        "proposed_limits": proposed,
        "all_limits_unapproved": all_unapproved,
        "note": "UNAPPROVED limits must not enable order submission",
    }


def evaluate_risk_policy_blocks(
    *,
    policy: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed: UNAPPROVED policy always blocks execution authorization."""
    policy = policy or propose_demo_risk_policy()
    ctx = context or {}
    reasons = []
    if policy.get("approval_status") == UNAPPROVED:
        reasons.append("risk_policy_unapproved")
    if policy.get("authorizes_execution"):
        reasons.append("invariant_broken_policy_authorizes")
    if ctx.get("stale_tick"):
        reasons.append("stale_data")
    if ctx.get("spread_explosion"):
        reasons.append("spread_explosion")
    if ctx.get("outside_session"):
        reasons.append("market_session_restriction")
    if ctx.get("incomplete_sessions"):
        reasons.append("incomplete_trading_sessions")
    return {
        "allowed": False,  # never allow in 64.6
        "blocked_reasons": reasons or ["default_fail_closed"],
        "approval_status": policy.get("approval_status"),
    }


def audit_risk_policy() -> dict[str, Any]:
    # Without verified currency, proposals stay UNKNOWN for money fields
    p1 = propose_demo_risk_policy(account_balance=UNKNOWN, account_currency=UNKNOWN)
    p2 = propose_demo_risk_policy(account_balance=500.0, account_currency="USD")
    ev = evaluate_risk_policy_blocks(policy=p2, context={"stale_tick": True})
    out = {
        "without_verified_balance": p1,
        "with_demo_balance_still_unapproved": p2,
        "evaluation_blocks": ev,
        "pass": (
            p1["approval_status"] == UNAPPROVED
            and p2["approval_status"] == UNAPPROVED
            and p2["all_limits_unapproved"]
            and not p2["authorizes_execution"]
            and ev["allowed"] is False
            and p2["proposed_limits"]["max_risk_per_decision"]["value"] == 2.5
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
