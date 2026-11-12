"""Exness MT5 broker metadata — active XAUUSDm; superseded XAUUSD preserved for audit."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase63.constants import (
    FORBIDDEN_KEYS,
    META_DIR,
    VERIFICATION_STATUS,
    canonical_json_sha256,
)
from phase63.progress import write_json

SUPERSESSION_REASON = "PREVIOUS_ACCOUNT_CONNECTION_WAS_NOT_THE_CORRECT_ACTIVE_EXNESS_ACCOUNT"
ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"

# Historical profile (audit only) — original Phase 63 registration; do not use as active
SUPERSEDED_XAUUSD_SPEC: dict[str, Any] = {
    "broker": "Exness",
    "environment": "DEMO",
    "account_type": "Standard",
    "account_currency": "USD",
    "demo_balance_at_setup": 500,
    "platform": "MT5",
    "server": "Exness-MT5Trial15",
    "account_mode": "HEDGE",
    "leverage": "1:2000",
    "symbol": "XAUUSD",
    "sector": "Commodities",
    "industry": "Precious Metals",
    "digits": 2,
    "contract_size": 100,
    "spread_mode": "FLOATING",
    "stops_level": 0,
    "margin_currency": "USD",
    "profit_currency": "USD",
    "calculation_mode": "CFD_LEVERAGE",
    "tick_size": 0.01,
    "tick_value": 0.10,
    "hedged_margin": "LARGER_LEG",
    "chart_mode": "BID",
    "trade_mode": "FULL",
    "execution_mode": "INSTANT",
    "gtc_mode": "GOOD_TILL_CANCELLED",
    "filling_modes": ["FOK", "IOC"],
    "expiration_modes": ["ALL"],
    "order_modes": ["ALL"],
    "volume_min": 0.01,
    "volume_max": 100,
    "volume_step": 0.01,
    "swap_type": "POINTS",
    "swap_long": -12.6,
    "swap_short": -4.6,
    "swap_multipliers": {
        "monday": 1,
        "tuesday": 1,
        "wednesday": 3,
        "thursday": 1,
        "friday": 1,
    },
    "quote_and_trade_sessions": {
        "monday_to_friday": "00:00-24:00",
        "saturday": "CLOSED",
        "sunday": "CLOSED",
    },
    "verification_status": VERIFICATION_STATUS,
}

# New active profile — do not inherit tick/account fields from SUPERSEDED
ACTIVE_XAUUSDM_SPEC: dict[str, Any] = {
    "broker": "Exness",
    "environment": "DEMO",
    "platform": "MT5",
    "symbol": "XAUUSDm",
    "category": "Metals",
    "digits": 3,
    "contract_size": 100,
    "contract_size_unit": "XAU",
    "spread_mode": "FLOATING",
    "stops_level": 0,
    "margin_currency": "XAU",
    "profit_currency": "USD",
    "calculation_mode": "FOREX",
    "chart_mode": "BID",
    "trade_mode": "FULL",
    "execution_mode": "MARKET",
    "gtc_mode": "GOOD_TILL_CANCELLED",
    "filling_modes": ["FOK", "IOC"],
    "expiration_modes": ["ALL"],
    "order_modes": ["ALL"],
    "volume_min": 0.01,
    "volume_max": 200,
    "volume_step": 0.01,
    "swap_type": "POINTS",
    "swap_long": -488.7,
    "swap_short": 0,
    "swap_multipliers": {
        "monday": 1,
        "tuesday": 1,
        "wednesday": 3,
        "thursday": 1,
        "friday": 1,
    },
    "margin_rates": {
        "market_buy_usd_per_lot": 199.28,
        "market_sell_usd_per_lot": None,
        "initial_rate": "TRUNCATED",
        "maintenance_rate": "TRUNCATED",
    },
    # Explicitly UNKNOWN — must not inherit from XAUUSD
    "tick_size": "UNKNOWN",
    "tick_value": "UNKNOWN",
    "tick_value_profit": "UNKNOWN",
    "tick_value_loss": "UNKNOWN",
    "account_currency": "UNKNOWN",
    "account_leverage": "UNKNOWN",
    "account_type": "UNKNOWN",
    "server": "UNKNOWN",
    "trading_sessions": {
        "completeness": "PARTIAL",
        "sunday": "23:01-24:00",
        "monday_to_thursday": {
            "segment_1": "00:00-21:58",
            "segment_2_start": "23:00",
            "segment_2_end": "TRUNCATED_UNKNOWN",
        },
        "friday": "00:00-21:58",
        "saturday": "CLOSED",
        "missing_closing_times_invented": False,
    },
    "verification_status": VERIFICATION_STATUS,
}

# Back-compat alias — points to ACTIVE only (never superseded)
USER_REPORTED_MT5_SPEC = ACTIVE_XAUUSDM_SPEC


def _reject_forbidden(spec: dict[str, Any]) -> None:
    for k in spec:
        if str(k).lower() in FORBIDDEN_KEYS:
            raise ValueError(f"forbidden_key:{k}")


def _load_existing_active() -> dict[str, Any] | None:
    p = META_DIR / "exness_mt5_spec_user_reported.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def supersede_previous_xauusd(*, observation_timestamp_utc: str) -> dict[str, Any]:
    """Preserve prior XAUUSD profile as SUPERSEDED audit history."""
    existing = _load_existing_active()
    # Prefer on-disk previous if it was XAUUSD; else use baked SUPERSEDED_XAUUSD_SPEC
    if existing and (existing.get("values") or {}).get("symbol") == "XAUUSD":
        values = dict(existing.get("values") or {})
        prior_sha = existing.get("sha256")
        prior_obs = existing.get("observation_timestamp_utc")
    else:
        values = dict(SUPERSEDED_XAUUSD_SPEC)
        prior_sha = None
        prior_obs = None

    superseded = {
        "schema_version": "phase63_exness_mt5_spec_v1",
        "profile_status": "SUPERSEDED",
        "supersession_reason": SUPERSESSION_REASON,
        "superseded_at_utc": observation_timestamp_utc,
        "observation_timestamp_utc": prior_obs or observation_timestamp_utc,
        "verification_status": VERIFICATION_STATUS,
        "independently_verified_via_api": False,
        "active": False,
        "symbol": "XAUUSD",
        "values": values,
        "prior_active_sha256": prior_sha,
        "provenance": {
            "source": "user_provided_MT5_Specification_panel",
            "symbol": "XAUUSD",
            "environment": "DEMO",
            "note": "Incorrect active account connection; retained for audit only",
        },
        "do_not_use_for_active_selection": True,
        "do_not_transfer_specs_to_xauusdm": True,
    }
    superseded["sha256"] = canonical_json_sha256({k: v for k, v in superseded.items() if k != "sha256"})
    META_DIR.mkdir(parents=True, exist_ok=True)
    write_json(META_DIR / "exness_mt5_spec_SUPERSEDED_XAUUSD.json", superseded)
    return superseded


def register_metadata(*, observation_timestamp_utc: str | None = None) -> dict[str, Any]:
    """Register active XAUUSDm profile; supersede prior XAUUSD without deleting it."""
    ts = observation_timestamp_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _reject_forbidden(ACTIVE_XAUUSDM_SPEC)
    superseded = supersede_previous_xauusd(observation_timestamp_utc=ts)

    values = dict(ACTIVE_XAUUSDM_SPEC)
    # Guard: never copy tick_value / CFD_LEVERAGE from superseded
    assert values.get("tick_value") == "UNKNOWN"
    assert values.get("calculation_mode") == "FOREX"
    assert values.get("margin_currency") == "XAU"
    assert values.get("symbol") == "XAUUSDm"
    assert superseded["values"].get("tick_value") == 0.10  # historical only
    assert superseded["values"].get("calculation_mode") == "CFD_LEVERAGE"

    record = {
        "schema_version": "phase63_exness_mt5_spec_v1",
        "profile_status": "ACTIVE",
        "active": True,
        "observation_timestamp_utc": ts,
        "verification_status": VERIFICATION_STATUS,
        "independently_verified_via_api": False,
        "silently_converted_to_api_verified": False,
        "tick_value_inferred_from_contract_size": False,
        "tick_fields_status": "UNKNOWN",
        "credentials_stored": False,
        "supersedes_symbol": "XAUUSD",
        "supersession_reason": SUPERSESSION_REASON,
        "superseded_profile_sha256": superseded.get("sha256"),
        "missing_specifications": [
            "tick_size",
            "tick_value",
            "tick_value_profit",
            "tick_value_loss",
            "account_currency",
            "account_leverage",
            "market_sell_usd_per_lot",
            "complete_trading_session_schedules",
        ],
        "values": values,
        "provenance": {
            "source": "user_provided_MT5_Specification_panel",
            "symbol": "XAUUSDm",
            "environment": "DEMO",
            "category": "Metals",
        },
        "leakage_guards": {
            "old_tick_value_0_10_not_copied": values.get("tick_value") != 0.10,
            "old_cfd_leverage_not_copied": values.get("calculation_mode") != "CFD_LEVERAGE",
            "old_margin_currency_usd_not_copied": values.get("margin_currency") != "USD",
            "old_instant_execution_not_copied": values.get("execution_mode") != "INSTANT",
        },
    }
    record["sha256"] = canonical_json_sha256({k: v for k, v in record.items() if k != "sha256"})

    META_DIR.mkdir(parents=True, exist_ok=True)
    write_json(META_DIR / "exness_mt5_spec_user_reported.json", record)  # active pointer
    write_json(META_DIR / "exness_mt5_spec_ACTIVE_XAUUSDm.json", record)
    stamp = ts.replace(":", "").replace("-", "")[:15]
    write_json(META_DIR / f"exness_mt5_spec_ACTIVE_XAUUSDm_{stamp}.json", record)

    # Selection pointer — sole active config
    selection = {
        "active_symbol": ACTIVE_SYMBOL,
        "active_profile_path": str(META_DIR / "exness_mt5_spec_ACTIVE_XAUUSDm.json"),
        "active_sha256": record["sha256"],
        "superseded_symbol": SUPERSEDED_SYMBOL,
        "superseded_profile_path": str(META_DIR / "exness_mt5_spec_SUPERSEDED_XAUUSD.json"),
        "superseded_sha256": superseded["sha256"],
        "fallback_to_superseded_allowed": False,
        "selection_utc": ts,
    }
    selection["sha256"] = canonical_json_sha256({k: v for k, v in selection.items() if k != "sha256"})
    write_json(META_DIR / "active_broker_selection.json", selection)

    intake = {
        "broker": "Exness",
        "environment": "DEMO",
        "platform": "MT5",
        "platform__status": "USER_PROVIDED_UNVERIFIED",
        "exact_broker_symbol": "XAUUSDm",
        "exact_broker_symbol__status": "USER_PROVIDED_UNVERIFIED",
        "contract_size": 100,
        "contract_size__status": "USER_PROVIDED_UNVERIFIED",
        "tick_size": "UNKNOWN",
        "tick_size__status": "UNKNOWN",
        "tick_value": "UNKNOWN",
        "tick_value__status": "UNKNOWN",
        "account_currency": "UNKNOWN",
        "account_currency__status": "UNKNOWN",
        "account_type": "UNKNOWN",
        "account_type__status": "UNKNOWN",
        "volume_minimum": 0.01,
        "volume_step": 0.01,
        "execution_mode": "MARKET",
        "execution_mode__status": "USER_PROVIDED_UNVERIFIED",
        "margin_currency": "XAU",
        "profit_currency": "USD",
        "calculation_mode": "FOREX",
        "applicable_commission_schedule": "UNKNOWN",
        "applicable_commission_schedule__status": "UNKNOWN",
        "swap_configuration": {
            "swap_type": "POINTS",
            "swap_long": -488.7,
            "swap_short": 0,
            "swap_multipliers": ACTIVE_XAUUSDM_SPEC["swap_multipliers"],
        },
        "swap_configuration__status": "USER_PROVIDED_UNVERIFIED",
        "verification_source": VERIFICATION_STATUS,
        "verification_timestamp_utc": ts,
        "pseudonymous_account_ref": "exness-mt5-demo-xauusdm",
        "verified_via_suffix_only": False,
        "phase63_metadata_sha256": record["sha256"],
        "superseded_xauusd_sha256": superseded["sha256"],
    }
    write_json(META_DIR / "phase62_compatible_intake.json", intake)
    return record


def get_active_symbol() -> str:
    sel = META_DIR / "active_broker_selection.json"
    if sel.is_file():
        obj = json.loads(sel.read_text(encoding="utf-8"))
        if obj.get("fallback_to_superseded_allowed"):
            raise RuntimeError("invalid_selection_allows_superseded_fallback")
        return str(obj.get("active_symbol") or ACTIVE_SYMBOL)
    return ACTIVE_SYMBOL


def get_active_profile() -> dict[str, Any]:
    p = META_DIR / "exness_mt5_spec_ACTIVE_XAUUSDm.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    # Ensure registration
    return register_metadata()


def assert_no_xauusd_leakage(active: dict[str, Any]) -> list[str]:
    """Return list of leakage failures (empty = ok)."""
    v = active.get("values") or {}
    fails = []
    if v.get("symbol") != "XAUUSDm":
        fails.append("active_symbol_not_xauusdm")
    if v.get("tick_value") == 0.10:
        fails.append("old_tick_value_leaked")
    if v.get("tick_size") == 0.01 and v.get("tick_size") != "UNKNOWN":
        # 0.01 was old; new must be UNKNOWN
        fails.append("old_tick_size_leaked")
    if v.get("calculation_mode") == "CFD_LEVERAGE":
        fails.append("old_cfd_leverage_leaked")
    if v.get("margin_currency") == "USD":
        fails.append("old_margin_currency_usd_leaked")
    if v.get("execution_mode") == "INSTANT":
        fails.append("old_instant_execution_leaked")
    if v.get("digits") == 2:
        fails.append("old_digits_2_leaked")
    return fails
