"""
Multi-condition authorization model.

BROKER_EXECUTION_AUTHORIZED remains FALSE.
No single flag / env / connection / preflight success can authorize.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phase64_9.constants import (
    AUTH_MODEL_VERSION,
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    FORBIDDEN_AUTH_ENV,
    LIVE_TRADING,
    MODE_BROKER_AUTHORIZED,
    MODE_BROKER_PREPARED,
    MODE_BROKER_RO,
    MODE_EMERGENCY,
    MODE_PAPER,
    MODE_RESEARCH,
    UNAPPROVED,
    canonical_json_sha256,
)


REQUIRED_GATES = (
    "demo_account_verified",
    "broker_server_verified",
    "symbol_metadata_complete",
    "risk_policy_approved",
    "execution_policy_approved",
    "reconciliation_ready",
    "durable_journal_ready",
    "kill_switch_disengaged",
    "human_approval_present",
    "broker_submission_source_enabled",  # source constant True — currently False
    "phase65_authorization_complete",  # not started
)


@dataclass
class AuthorizationBundle:
    """All gates default False / blocked."""

    mode: str = MODE_BROKER_RO
    demo_account_verified: bool = False
    broker_server_verified: bool = False
    symbol_metadata_complete: bool = False
    risk_policy_approved: bool = False
    execution_policy_approved: bool = False
    reconciliation_ready: bool = False
    durable_journal_ready: bool = False
    kill_switch_disengaged: bool = False
    human_approval_present: bool = False
    broker_submission_source_enabled: bool = False
    phase65_authorization_complete: bool = False
    # Inference traps — must never alone authorize
    production_mode: bool = False
    paper_mode: bool = False
    mt5_connected: bool = False
    metadata_valid: bool = False
    preflight_passed: bool = False
    fake_broker_tests_passed: bool = False
    credentials_present: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def evaluate_authorization(bundle: AuthorizationBundle | None = None) -> dict[str, Any]:
    b = bundle or AuthorizationBundle()
    if b.mode == MODE_EMERGENCY:
        return _result(False, ["emergency_shutdown"], b)

    gate_values = {g: bool(getattr(b, g)) for g in REQUIRED_GATES}
    failed = [g for g, v in gate_values.items() if not v]

    # Explicitly prove inference traps do not authorize
    inference = {
        "production_mode": b.production_mode,
        "paper_mode": b.paper_mode,
        "mt5_connected": b.mt5_connected,
        "metadata_valid": b.metadata_valid,
        "preflight_passed": b.preflight_passed,
        "fake_broker_tests_passed": b.fake_broker_tests_passed,
        "credentials_present": b.credentials_present,
        "env_vars": {k: os.environ.get(k) for k in FORBIDDEN_AUTH_ENV},
    }
    inference_alone_cannot_authorize = True

    # Source constants always win
    if BROKER_EXECUTION_AUTHORIZED:
        failed.append("invariant_broken_BROKER_EXECUTION_AUTHORIZED_true")
    if BROKER_SUBMISSION_ENABLED:
        failed.append("invariant_broken_BROKER_SUBMISSION_ENABLED_true")

    authorized = len(failed) == 0 and BROKER_EXECUTION_AUTHORIZED and BROKER_SUBMISSION_ENABLED
    # Current phase: always False
    authorized = False

    return _result(authorized, failed, b, gate_values=gate_values, inference=inference,
                   inference_alone_cannot_authorize=inference_alone_cannot_authorize)


def _result(
    authorized: bool,
    failed: list[str],
    b: AuthorizationBundle,
    **extra: Any,
) -> dict[str, Any]:
    out = {
        "auth_model_version": AUTH_MODEL_VERSION,
        "mode": b.mode,
        "authorized": authorized,
        "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
        "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
        "failed_gates": failed,
        "required_gates": list(REQUIRED_GATES),
        "risk_policy": UNAPPROVED,
        "live_trading": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "modes": [
            MODE_RESEARCH,
            MODE_PAPER,
            MODE_BROKER_RO,
            MODE_BROKER_PREPARED,
            MODE_BROKER_AUTHORIZED,
            MODE_EMERGENCY,
        ],
        "current_mode": MODE_BROKER_RO,
        "note": "No single configuration flag can bypass the complete authorization model",
        **extra,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def config_file_cannot_authorize(path: Path) -> dict[str, Any]:
    """Even if a config claims authorization, ignore it."""
    claimed = False
    raw = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            claimed = bool(raw.get("broker_execution_authorized") or raw.get("BROKER_SUBMISSION_ENABLED"))
        except Exception:
            raw = {"error": "unreadable"}
    result = evaluate_authorization(
        AuthorizationBundle(
            # Even if config claims everything:
            demo_account_verified=True,
            broker_server_verified=True,
            symbol_metadata_complete=True,
            risk_policy_approved=True,
            execution_policy_approved=True,
            reconciliation_ready=True,
            durable_journal_ready=True,
            kill_switch_disengaged=True,
            human_approval_present=True,
            broker_submission_source_enabled=True,
            phase65_authorization_complete=True,
        )
    )
    return {
        "config_path": str(path),
        "config_claimed_auth": claimed,
        "config_raw_keys": sorted((raw or {}).keys()) if isinstance(raw, dict) else [],
        "system_authorized": result["authorized"],
        "pass": result["authorized"] is False,
        "note": "Config file cannot override source constants / incomplete Phase65 gates",
    }


def authorization_model_spec() -> dict[str, Any]:
    return {
        "version": AUTH_MODEL_VERSION,
        "required_gates": list(REQUIRED_GATES),
        "inference_traps_ignored": [
            "production_mode",
            "paper_mode",
            "mt5_connection",
            "valid_metadata",
            "successful_preflight",
            "fake_broker_tests",
            "environment_variables",
            "credentials_presence",
        ],
        "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
        "current_mode": MODE_BROKER_RO,
    }
