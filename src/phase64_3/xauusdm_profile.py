"""Active XAUUSDm profile for paper runtime — read-only from Phase63; no XAUUSD fallback."""

from __future__ import annotations

from typing import Any

from phase63.metadata import ACTIVE_SYMBOL, ACTIVE_XAUUSDM_SPEC, SUPERSEDED_SYMBOL, get_active_symbol
from phase64_3.constants import canonical_json_sha256


UNKNOWN_FIELDS = (
    "tick_size",
    "tick_value",
    "tick_value_profit",
    "tick_value_loss",
    "account_currency",
    "account_leverage",
)


def active_account_profile() -> dict[str, Any]:
    spec = dict(ACTIVE_XAUUSDM_SPEC)
    if spec.get("symbol") != "XAUUSDm":
        raise RuntimeError("active_symbol_not_xauusdm")
    if get_active_symbol() != "XAUUSDm":
        raise RuntimeError("get_active_symbol_mismatch")

    def _unk(key: str) -> Any:
        v = spec.get(key)
        return "UNKNOWN" if v is None else v

    return {
        "broker": spec.get("broker"),
        "environment": spec.get("environment"),
        "platform": spec.get("platform"),
        "symbol": spec.get("symbol"),
        "digits": spec.get("digits"),
        "volume_min": spec.get("volume_min"),
        "volume_max": spec.get("volume_max"),
        "volume_step": spec.get("volume_step"),
        "verification_status": spec.get("verification_status"),
        "calculation_mode": spec.get("calculation_mode"),
        "margin_currency": spec.get("margin_currency"),
        "profit_currency": spec.get("profit_currency"),
        "tick_size": _unk("tick_size"),
        "tick_value": _unk("tick_value"),
        "tick_value_profit": _unk("tick_value_profit"),
        "tick_value_loss": _unk("tick_value_loss"),
        "account_currency": _unk("account_currency"),
        "account_leverage": _unk("account_leverage"),
        "provenance": "USER_REPORTED_FROM_CONNECTED_MT5_SPECIFICATION",
        "superseded_symbol_not_used": SUPERSEDED_SYMBOL,
    }


def audit_xauusdm_integrity() -> dict[str, Any]:
    profile = active_account_profile()
    unknowns = {f: profile.get(f) for f in UNKNOWN_FIELDS}
    invented = [f for f, v in unknowns.items() if v not in ("UNKNOWN", None)]
    # tick etc must remain UNKNOWN strings
    unknown_ok = all(profile.get(f) == "UNKNOWN" for f in UNKNOWN_FIELDS)
    out = {
        "active_symbol": ACTIVE_SYMBOL,
        "get_active_symbol": get_active_symbol(),
        "superseded_symbol": SUPERSEDED_SYMBOL,
        "digits": profile.get("digits"),
        "volume_min": profile.get("volume_min"),
        "volume_step": profile.get("volume_step"),
        "unknown_fields": unknowns,
        "unknown_fields_intact": unknown_ok,
        "no_silent_xauusd_fallback": profile.get("symbol") == "XAUUSDm" and get_active_symbol() == "XAUUSDm",
        "no_invented_missing_specs": unknown_ok and len(invented) == 0,
        "broker_execution_realism_claimed": False,
        "pass": unknown_ok and profile.get("symbol") == "XAUUSDm" and profile.get("digits") == 3,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
