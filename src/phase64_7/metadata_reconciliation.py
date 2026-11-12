"""Reconcile live RO observations against Phase63 user-reported ACTIVE_XAUUSDm profile."""

from __future__ import annotations

from typing import Any

from phase63.metadata import ACTIVE_XAUUSDM_SPEC
from phase64_7.constants import (
    CRITICAL_ACCOUNT_FIELDS,
    CRITICAL_SYMBOL_FIELDS,
    RECON_META_VERSION,
    UNKNOWN,
    canonical_json_sha256,
)


def _norm(v: Any) -> Any:
    if v is None or v == "":
        return UNKNOWN
    return v


def _comparable(a: Any, b: Any) -> bool:
    if a == UNKNOWN or b == UNKNOWN:
        return False
    try:
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            return abs(float(a) - float(b)) < 1e-9
    except Exception:
        pass
    return str(a) == str(b)


def _row(*, field: str, existing: Any, observed: Any, source: str, ts: str) -> dict[str, Any]:
    existing_n = _norm(existing)
    observed_n = _norm(observed)
    if existing_n == UNKNOWN and observed_n != UNKNOWN:
        status = "PREVIOUSLY_UNKNOWN_NOW_OBSERVED"
    elif observed_n == UNKNOWN and existing_n != UNKNOWN:
        status = "OBSERVED_UNKNOWN_EXISTING_PRESENT"
    elif existing_n == UNKNOWN and observed_n == UNKNOWN:
        status = "STILL_UNKNOWN"
    elif _comparable(existing_n, observed_n):
        status = "MATCH"
    else:
        status = "MISMATCH_CONFLICT"
    safe = status in ("MATCH", "PREVIOUSLY_UNKNOWN_NOW_OBSERVED") and observed_n != UNKNOWN
    return {
        "field": field,
        "existing_value": existing_n,
        "observed_value": observed_n,
        "existing_provenance": "USER_REPORTED_PHASE63_ACTIVE_XAUUSDM_SPEC",
        "observed_source": source,
        "verification_timestamp_utc": ts,
        "status": status,
        "safe_for_calculations": safe,
        "both_preserved_on_conflict": status == "MISMATCH_CONFLICT",
    }


def reconcile_metadata(probe: dict[str, Any]) -> dict[str, Any]:
    raw = probe.get("raw") or {}
    if probe.get("status") != "LIVE_PROBE_OK" or raw.get("status") != "LIVE_PROBE_OK":
        return {
            "status": "NOT_RECONCILED",
            "reason": probe.get("block_reason") or probe.get("status"),
            "recon_version": RECON_META_VERSION,
            "rows": [],
            "conflicts": [],
            "pass": False,
        }

    ts = raw.get("retrieved_at_utc") or UNKNOWN
    base = dict(ACTIVE_XAUUSDM_SPEC)
    acct = raw.get("account") or {}
    sym = raw.get("symbol") or {}
    source = "LIVE_MT5_API_symbol_info_account_info"

    field_map = [
        ("symbol", base.get("symbol"), sym.get("name")),
        ("digits", base.get("digits"), sym.get("digits")),
        ("contract_size", base.get("contract_size"), sym.get("contract_size")),
        ("point", UNKNOWN, sym.get("point")),
        ("tick_size", base.get("tick_size"), sym.get("tick_size")),
        ("tick_value", base.get("tick_value"), sym.get("tick_value")),
        ("tick_value_profit", base.get("tick_value_profit"), sym.get("tick_value_profit")),
        ("tick_value_loss", base.get("tick_value_loss"), sym.get("tick_value_loss")),
        ("volume_min", base.get("volume_min"), sym.get("volume_min")),
        ("volume_max", base.get("volume_max"), sym.get("volume_max")),
        ("volume_step", base.get("volume_step"), sym.get("volume_step")),
        ("profit_currency", base.get("profit_currency"), sym.get("profit_currency")),
        ("margin_currency", base.get("margin_currency"), sym.get("margin_currency")),
        ("execution_mode", base.get("execution_mode"), sym.get("execution_mode")),
        ("filling_modes", str(base.get("filling_modes")), str(sym.get("filling_modes"))),
        ("swap_type", base.get("swap_type"), sym.get("swap_type")),
        ("swap_long", base.get("swap_long"), sym.get("swap_long")),
        ("swap_short", base.get("swap_short"), sym.get("swap_short")),
        ("stops_level", base.get("stops_level"), sym.get("stops_level")),
        ("account_currency", base.get("account_currency"), acct.get("currency")),
        ("account_leverage", base.get("account_leverage"), acct.get("leverage")),
        ("server", base.get("server"), acct.get("server")),
        ("trading_sessions", "PARTIAL_USER_REPORTED", sym.get("trading_sessions")),
        ("commission_schedule", UNKNOWN, sym.get("commission_schedule")),
        ("initial_margin", UNKNOWN, sym.get("initial_margin")),
        ("maintenance_margin", UNKNOWN, sym.get("maintenance_margin")),
        ("current_spread_points", UNKNOWN, sym.get("spread_points")),
    ]

    rows = [
        _row(field=f, existing=ex, observed=ob, source=source, ts=ts) for f, ex, ob in field_map
    ]
    conflicts = [r for r in rows if r["status"] == "MISMATCH_CONFLICT"]
    newly = [r for r in rows if r["status"] == "PREVIOUSLY_UNKNOWN_NOW_OBSERVED"]

    # Completeness from critical fields using OBSERVED values
    observed_flat = {
        "account_currency": acct.get("currency"),
        "account_leverage": acct.get("leverage"),
        "server": acct.get("server"),
        "tick_size": sym.get("tick_size"),
        "tick_value": sym.get("tick_value"),
        "contract_size": sym.get("contract_size"),
        "digits": sym.get("digits"),
        "volume_min": sym.get("volume_min"),
        "volume_step": sym.get("volume_step"),
        "volume_max": sym.get("volume_max"),
        "profit_currency": sym.get("profit_currency"),
        "margin_currency": sym.get("margin_currency"),
    }
    acct_complete = all(
        observed_flat.get(k) not in (None, "", UNKNOWN) for k in CRITICAL_ACCOUNT_FIELDS
    )
    sym_complete = all(
        observed_flat.get(k) not in (None, "", UNKNOWN) for k in CRITICAL_SYMBOL_FIELDS
    )
    # Sessions / commission still unknown — note but not in critical calc set for tick money
    remaining_unknown = [
        r["field"] for r in rows if r["observed_value"] == UNKNOWN or r["status"] == "STILL_UNKNOWN"
    ]

    out = {
        "recon_version": RECON_META_VERSION,
        "status": "RECONCILED_WITH_CONFLICTS" if conflicts else "RECONCILED",
        "rows": rows,
        "conflicts": conflicts,
        "previously_unknown_now_observed": newly,
        "n_conflicts": len(conflicts),
        "account_metadata_complete": acct_complete,
        "xauusdm_critical_metadata_complete": sym_complete,
        "remaining_unknown_or_unobserved": remaining_unknown,
        "authoritative_overwrite": False,
        "note": "Conflicts preserve both existing user-reported and live API observations; no silent overwrite of Phase63 records",
        "pass": acct_complete and sym_complete and raw.get("evidence_type") == "LIVE_MT5_API",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k not in ("sha256", "rows")})
    return out
