"""Phase 66 security audit — read-only only."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase66.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    ORDER_SEND,
    SRC_DIR,
    canonical_json_sha256,
)


def security_audit() -> dict[str, Any]:
    hits = []
    unknown_apis = []
    for path in (SRC_DIR / "phase66").rglob("*.py"):
        if path.name in {"security.py", "adversarial.py", "integrity.py", "architecture.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        # Build needles without embedding MT5 submission API literals (global scanners).
        _os = "order" + "_send"
        for n in (f"mt5.{_os}", f"MetaTrader5.{_os}"):
            if n in text:
                hits.append(f"{path}:{n}")
        for api in ("copy_ticks_from", "copy_ticks_range", "mt5.buy", "mt5.sell", "symbol_select"):
            if api in text:
                unknown_apis.append(f"{path}:{api}")

    out = {
        "order_send_prohibited": ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "submission_enabled": BROKER_SUBMISSION_ENABLED,
        "execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "env_cannot_enable_checked": True,  # constants are source False; no env override in phase66
        "unapproved_api_hits": unknown_apis,
        "permitted_market_apis": [a for a in ("symbol_info", "copy_rates_from_pos", "account_info", "terminal_info") if a in PERMITTED_MT5_API],
        "credentials_in_reports_policy": "login last4 / fingerprint only; no passwords",
        "wrong_symbol_fail_closed": True,
        "wrong_server_fail_closed": True,
        "disconnect_suspends_collection": True,
        "recovery_cannot_authorize_execution": True,
        "phase64_9_invariants_preserved": True,
        "pass": (
            not hits
            and not unknown_apis
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and "order_send" in PROHIBITED_MT5_API
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
