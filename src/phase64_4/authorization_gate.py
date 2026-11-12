"""
Authorization gate — IMPLEMENTATION (validation only).

All gates default BLOCKED. No environment variable, config file, fixture, or default
may silently enable broker submission. No executable path reaches order_send.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from phase63.metadata import ACTIVE_XAUUSDM_SPEC, get_active_symbol
from phase64_4.constants import (
    ACTIVE_SYMBOL,
    AUTH_GATE_VERSION,
    AUTH_GATES,
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    ORDER_SEND_REACHABLE,
    SUBMISSION_PATH_EXISTS,
    SUPERSEDED_SYMBOL,
    canonical_json_sha256,
)
from phase64_4.kill_switch import KillSwitch
from phase64_4.risk_spec import UNCONFIGURED, default_broker_risk_config, evaluate_broker_risk_gates

REQUIRED_SYMBOL_METADATA = (
    "tick_size",
    "tick_value",
    "account_currency",
    "account_leverage",
    "server",
    "commission_schedule",
)


@dataclass
class HumanApproval:
    """Explicit human approval object — must be constructed in-process, never inferred from env."""

    approved: bool = False
    approver_id: str = ""
    approval_reference: str = ""
    scope: str = ""
    notes: str = ""


@dataclass
class AuthorizationContext:
    """Inputs under evaluation. Defaults leave every gate blocked."""

    expected_demo_login: str | None = None
    observed_demo_login: str | None = None
    expected_broker_server: str | None = None
    observed_broker_server: str | None = None
    active_symbol: str | None = None
    symbol_metadata: dict[str, Any] = field(default_factory=dict)
    risk_config: dict[str, Any] = field(default_factory=default_broker_risk_config)
    execution_policy_approved: bool = False
    reconciliation_ready: bool = False
    durable_journal_ready: bool = False
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    human_approval: HumanApproval = field(default_factory=HumanApproval)
    # Hard locks — cannot be overridden to create submission
    force_block_submission_path: bool = True


class AuthorizationBlocked(RuntimeError):
    pass


def _gate_demo_account(ctx: AuthorizationContext) -> tuple[bool, str]:
    if not ctx.expected_demo_login or not ctx.observed_demo_login:
        return False, "demo_account_identity_unconfigured"
    if ctx.expected_demo_login != ctx.observed_demo_login:
        return False, "demo_account_identity_mismatch"
    if str(ctx.observed_demo_login).upper() in {"", "UNKNOWN", "LIVE"}:
        return False, "demo_account_identity_invalid"
    return True, "ok"


def _gate_broker_server(ctx: AuthorizationContext) -> tuple[bool, str]:
    if not ctx.expected_broker_server or not ctx.observed_broker_server:
        return False, "broker_server_unconfigured"
    if ctx.expected_broker_server != ctx.observed_broker_server:
        return False, "broker_server_mismatch"
    if ctx.observed_broker_server in ("UNKNOWN", ""):
        return False, "broker_server_unknown"
    return True, "ok"


def _gate_active_symbol(ctx: AuthorizationContext) -> tuple[bool, str]:
    sym = ctx.active_symbol or get_active_symbol()
    if sym == SUPERSEDED_SYMBOL:
        return False, "superseded_xauusd"
    if sym != ACTIVE_SYMBOL:
        return False, f"wrong_symbol:{sym}"
    return True, "ok"


def _gate_symbol_metadata(ctx: AuthorizationContext) -> tuple[bool, str]:
    meta = ctx.symbol_metadata or dict(ACTIVE_XAUUSDM_SPEC)
    missing = []
    for k in REQUIRED_SYMBOL_METADATA:
        v = meta.get(k)
        if v in (None, "", "UNKNOWN", "UNCONFIGURED"):
            missing.append(k)
    # Also require sessions completeness not PARTIAL for authorization
    sessions = meta.get("trading_sessions") or {}
    if sessions.get("completeness") in (None, "PARTIAL", "UNKNOWN"):
        missing.append("complete_trading_sessions")
    if missing:
        return False, "incomplete_symbol_metadata:" + ",".join(missing)
    return True, "ok"


def _gate_risk_config(ctx: AuthorizationContext) -> tuple[bool, str]:
    ev = evaluate_broker_risk_gates(config=ctx.risk_config)
    if not ev["allowed"]:
        return False, "risk_unconfigured_or_blocked:" + ";".join(ev["blocked_reasons"][:5])
    return True, "ok"


def _gate_execution_policy(ctx: AuthorizationContext) -> tuple[bool, str]:
    if not ctx.execution_policy_approved:
        return False, "execution_policy_not_approved"
    return True, "ok"


def _gate_reconciliation(ctx: AuthorizationContext) -> tuple[bool, str]:
    if not ctx.reconciliation_ready:
        return False, "reconciliation_not_ready"
    return True, "ok"


def _gate_durable_journal(ctx: AuthorizationContext) -> tuple[bool, str]:
    if not ctx.durable_journal_ready:
        return False, "durable_journal_not_ready"
    return True, "ok"


def _gate_kill_switch(ctx: AuthorizationContext) -> tuple[bool, str]:
    ks = ctx.kill_switch.snapshot()
    if not ks.get("operational"):
        return False, "kill_switch_not_operational"
    if ks.get("blocks_submission"):
        return False, "kill_switch_engaged"
    return True, "ok"


def _gate_human_approval(ctx: AuthorizationContext) -> tuple[bool, str]:
    # Env must NEVER silently approve
    if os.environ.get("AIBOT_BROKER_SUBMIT", "").lower() in {"1", "true", "yes", "enable"}:
        return False, "env_var_cannot_authorize_submission"
    ha = ctx.human_approval
    if not ha.approved:
        return False, "human_approval_missing"
    if not ha.approver_id or not ha.approval_reference:
        return False, "human_approval_incomplete"
    if ha.scope != "DEMO_EXECUTION_REVIEW_PENDING":
        # Phase64.4 only accepts a design-scope marker; live demo submit scope rejected
        if ha.scope == "BROKER_ORDER_SUBMIT":
            return False, "submit_scope_forbidden_in_phase64_4"
        return False, f"human_approval_scope_invalid:{ha.scope}"
    return True, "ok"


GATE_EVALUATORS = {
    "demo_account_identity": _gate_demo_account,
    "broker_server": _gate_broker_server,
    "active_symbol": _gate_active_symbol,
    "complete_symbol_metadata": _gate_symbol_metadata,
    "complete_risk_configuration": _gate_risk_config,
    "approved_execution_policy": _gate_execution_policy,
    "reconciliation_readiness": _gate_reconciliation,
    "durable_journal_readiness": _gate_durable_journal,
    "kill_switch_operational": _gate_kill_switch,
    "explicit_human_approval": _gate_human_approval,
}


def evaluate_authorization(ctx: AuthorizationContext | None = None) -> dict[str, Any]:
    ctx = ctx or AuthorizationContext()
    gates: dict[str, Any] = {}
    for name in AUTH_GATES:
        ok, why = GATE_EVALUATORS[name](ctx)
        gates[name] = {"pass": ok, "reason": why, "default": "BLOCKED"}

    all_pass = all(g["pass"] for g in gates.values())
    # Absolute hard stop: Phase64.4 never authorizes submission even if gates somehow pass
    submission_authorized = False
    block_reasons = [f"{k}:{v['reason']}" for k, v in gates.items() if not v["pass"]]
    if ctx.force_block_submission_path or SUBMISSION_PATH_EXISTS is False:
        block_reasons.append("phase64_4_submission_path_absent")
    if ORDER_SEND_REACHABLE:
        block_reasons.append("invariant_broken_order_send_reachable")
    if AUTOMATED_ORDERS != "DISABLED":
        block_reasons.append("automated_orders_not_disabled")
    if BROKER_EXECUTION_READY:
        block_reasons.append("broker_execution_ready_flag_true_forbidden")

    out = {
        "auth_gate_version": AUTH_GATE_VERSION,
        "gates": gates,
        "all_design_gates_pass": all_pass,
        "submission_authorized": submission_authorized,
        "broker_order_send_permitted": False,
        "automated_orders": AUTOMATED_ORDERS,
        "broker_execution_ready": False,
        "block_reasons": block_reasons,
        "state": "BLOCKED_BY_AUTHORIZATION" if not submission_authorized else "AUTHORIZED",
        "env_cannot_enable": True,
        "note": "Even if all informational gates pass in a future phase, Phase64.4 hard-blocks submission",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def assert_submission_blocked(ctx: AuthorizationContext | None = None) -> dict[str, Any]:
    result = evaluate_authorization(ctx)
    if result["submission_authorized"] or result["broker_order_send_permitted"]:
        raise AuthorizationBlocked("submission_must_remain_blocked_in_phase64_4")
    return result


def attempt_unauthorized_submit(ctx: AuthorizationContext | None = None) -> dict[str, Any]:
    """
    Adversarial probe: any attempt to 'submit' via this module fails closed.
    There is no order_send call here by construction.
    """
    result = evaluate_authorization(ctx)
    return {
        "attempted": True,
        "reached_order_send": False,
        "submission_authorized": result["submission_authorized"],
        "blocked": True,
        "block_reasons": result["block_reasons"],
        "evidence_type": "SYNTHETIC_UNAUTHORIZED_ATTEMPT",
    }


def conditions_before_demo_execution_review() -> list[str]:
    return [
        "Independent RO verification of XAUUSDm tick size/value, account currency/leverage, server, sessions, commission",
        "All RISK_LIMIT_KEYS explicitly justified, approved, and configured (not UNCONFIGURED)",
        "Durable broker event journal implemented and crash-tested",
        "Reconciliation path able to discover broker orders/deals without blind resubmit",
        "Kill switch proven to block new submissions under failure injection",
        "Separate security review for any MT5 allowlist expansion (orders/deals history and/or order_send)",
        "Explicit human DEMO execution authorization with named approver + reference (not env vars)",
        "Automated Orders remain DISABLED until that review completes",
        "Genuine Exness demo account identity confirmed; no live account",
        "Phase64.3 approved paper runtime remains decision/intent authority",
        "No historical/shadow/demo store merging",
        "Champion stays NO_MODEL / Production WAIT / Live NOT_AUTHORIZED until separately changed",
    ]
