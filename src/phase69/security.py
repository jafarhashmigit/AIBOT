"""Phase 69 security audit."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase69.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    ORDER_SEND,
    SRC_DIR,
    canonical_json_sha256,
)


def security_audit() -> dict[str, Any]:
    hits = []
    unknown = []
    _os = "order" + "_send"
    for path in (SRC_DIR / "phase69").rglob("*.py"):
        if path.name in {"security.py", "audit.py", "adversarial.py"} or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for n in (f"mt5.{_os}", f"MetaTrader5.{_os}"):
            if n in text:
                hits.append(f"{path.name}:{n}")
        for api in ("copy_ticks_from", "copy_ticks_range", "symbol_info_tick"):
            if api in text:
                unknown.append(f"{path.name}:{api}")
    out = {
        "order_send_prohibited": ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "unapproved_api_hits": unknown,
        "submission_enabled": BROKER_SUBMISSION_ENABLED,
        "execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "pass": (
            not hits
            and not unknown
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and "order_send" in PROHIBITED_MT5_API
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
