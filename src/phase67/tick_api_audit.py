"""Tick API approval audit — do not call unapproved APIs."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase67.constants import canonical_json_sha256

TICK_CANDIDATES = ("copy_ticks_from", "copy_ticks_range", "symbol_info_tick")


def audit_tick_api_approval() -> dict[str, Any]:
    rows = []
    for api in TICK_CANDIDATES:
        permitted = api in PERMITTED_MT5_API
        prohibited = api in PROHIBITED_MT5_API
        status = "PERMITTED" if permitted else ("PROHIBITED" if prohibited else "NOT_APPROVED_UNKNOWN")
        rows.append(
            {
                "api": api,
                "in_permitted": permitted,
                "in_prohibited": prohibited,
                "status": status,
                "safe_to_call_in_phase67": False,
                "reason": (
                    "On Phase12 allowlist"
                    if permitted
                    else (
                        "Explicitly prohibited"
                        if prohibited
                        else "Absent from PERMITTED_MT5_API; Phase12 audit treats unknown attrs as fail-closed"
                    )
                ),
            }
        )
    out = {
        "permitted_market_apis": sorted(
            a for a in PERMITTED_MT5_API if a.startswith("copy_rates") or a in ("symbol_info", "account_info", "terminal_info")
        ),
        "tick_candidates": rows,
        "any_tick_api_approved": any(r["in_permitted"] for r in rows),
        "phase67_uses_ticks": False,
        "approval_requirement": (
            "To collect a genuine Exness tick stream, a new security phase must explicitly add "
            "copy_ticks_from and/or copy_ticks_range to PERMITTED_MT5_API after read-only risk review. "
            "Until then Phase67 collects bid/ask via symbol_info snapshots and M5 via copy_rates_* only."
        ),
        "symbol_info_tick_blocked": True,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
