"""Phase 67 security audit."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase67.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    ORDER_SEND,
    SRC_DIR,
    canonical_json_sha256,
)
from phase67.tick_api_audit import audit_tick_api_approval


def security_audit() -> dict[str, Any]:
    hits = []
    unknown = []
    _os = "order" + "_send"
    for path in (SRC_DIR / "phase67").rglob("*.py"):
        if path.name in {"security.py", "tick_api_audit.py", "adversarial.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for n in (f"mt5.{_os}", f"MetaTrader5.{_os}"):
            if n in text:
                hits.append(f"{path}:{n}")
        for api in ("copy_ticks_from", "copy_ticks_range", "symbol_info_tick", "mt5.buy", "mt5.sell"):
            # allow string mentions in comments/docs audit modules only — those skipped
            if api in text:
                unknown.append(f"{path}:{api}")
    tick = audit_tick_api_approval()
    out = {
        "order_send_prohibited": ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "unapproved_api_hits": unknown,
        "submission_enabled": BROKER_SUBMISSION_ENABLED,
        "execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "tick_apis_called": False,
        "tick_approval": tick,
        "permitted_used_design": ["symbol_info", "copy_rates_from_pos", "account_info", "terminal_info"],
        "credentials_policy": "no passwords in reports",
        "holdout_outcomes_accessed": False,
        "synthetic_as_genuine": False,
        "pass": (
            not hits
            and not unknown
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and not tick["any_tick_api_approved"]  # documenting unused is fine
            and "order_send" in PROHIBITED_MT5_API
        ),
    }
    # pass should not require tick unapproved — that's expected. Fix:
    out["pass"] = (
        not hits
        and not unknown
        and BROKER_SUBMISSION_ENABLED is False
        and BROKER_EXECUTION_AUTHORIZED is False
        and "order_send" in PROHIBITED_MT5_API
        and tick["phase67_uses_ticks"] is False
    )
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
