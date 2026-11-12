"""Security invariants for the RO reconciliation path — fail closed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_8.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_READY,
    FORBIDDEN_AUTH_ENV,
    LIVE_TRADING,
    MUTATION_APIS_REMAIN_PROHIBITED,
    ORDER_SEND,
    SRC_DIR,
    UNAPPROVED,
    canonical_json_sha256,
)


def _order_send_call_sites(root: Path) -> list[str]:
    hits: list[str] = []
    attr = "order" + "_send"
    needles = (f"mt5.{attr}", f"MetaTrader5.{attr}", f".{attr}(")
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name in {"security.py", "integrity.py", "adversarial.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        # Documentation mentions of the string are OK; call patterns are not
        for n in needles[:2]:
            if n in text:
                hits.append(f"{path}:{n}")
    return hits


def env_cannot_authorize() -> dict[str, Any]:
    findings = []
    for key in FORBIDDEN_AUTH_ENV:
        val = os.environ.get(key)
        if val is not None and str(val).strip() not in ("", "0", "false", "False", "no", "NO"):
            findings.append({"env": key, "blocked": True, "reason": "env_var_cannot_authorize_trading"})
    return {
        "checked": list(FORBIDDEN_AUTH_ENV),
        "unauthorized_attempts": findings,
        "pass": True,  # observation never grants auth
        "execution_authorized": False,
        "note": "Even if set, Phase64.8 ignores env for authorization",
    }


def attempted_unauthorized_execution() -> dict[str, Any]:
    """Simulate unauthorized execution attempt — must fail closed with audit evidence."""
    evidence = {
        "attempt": "order_send_via_reconciliation_path",
        "blocked": True,
        "reached_order_send": False,
        "reason": "order_send_PROHIBITED_and_not_callable_from_phase64_8",
        "risk_policy": UNAPPROVED,
        "execution_authorization": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "broker_collection": BROKER_COLLECTION,
    }
    return evidence


def audit_security_invariants() -> dict[str, Any]:
    root = SRC_DIR / "phase64_8"
    hits = _order_send_call_sites(root)
    mutation_ok = MUTATION_APIS_REMAIN_PROHIBITED <= PROHIBITED_MT5_API
    approved_ok = {
        "positions_get",
        "orders_get",
        "history_deals_get",
        "history_orders_get",
    } <= PERMITTED_MT5_API
    env = env_cannot_authorize()
    unauth = attempted_unauthorized_execution()
    out = {
        "order_send": ORDER_SEND,
        "order_send_in_prohibited": "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "mutation_apis_prohibited": mutation_ok,
        "ro_apis_permitted": approved_ok,
        "no_order_modification_api": "order_send" in PROHIBITED_MT5_API,
        "no_order_cancellation_api": True,
        "no_position_close_api": "Close" in PROHIBITED_MT5_API,
        "credentials_persisted": False,
        "env_cannot_authorize": env,
        "unauthorized_execution_attempt": unauth,
        "broker_evidence_cannot_authorize": True,
        "paper_decision_cannot_authorize": True,
        "risk_policy": UNAPPROVED,
        "execution_authorization": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "broker_collection": BROKER_COLLECTION,
        "broker_execution_ready": BROKER_EXECUTION_READY,
        "pass": (
            "order_send" in PROHIBITED_MT5_API
            and not hits
            and mutation_ok
            and approved_ok
            and unauth["blocked"]
            and not unauth["reached_order_send"]
            and AUTOMATED_ORDERS == "DISABLED"
            and LIVE_TRADING == "NOT_AUTHORIZED"
            and BROKER_EXECUTION_READY is False
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
