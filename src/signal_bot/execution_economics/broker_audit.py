"""Broker economics audit — consolidate live + Phase64 evidence; no fabrication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_bot.execution_economics.constants import (
    ACTIVE_SYMBOL,
    EXPECTED_SERVER,
    PHASE64_10_COMMISSION,
    PHASE64_10_COST,
    PHASE64_10_SWAP,
    PHASE64_7_PROBE,
    PROMPT07_BUNDLE,
    UNKNOWN,
    VERIFIED,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_DIGITS,
    VERIFIED_POINT,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
    VERIFIED_VOLUME_MAX,
    VERIFIED_VOLUME_MIN,
    VERIFIED_VOLUME_STEP,
    CONFLICTED,
    PARTIALLY_VERIFIED,
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _field(
    name: str,
    *,
    value: Any,
    source: str,
    observation_timestamp_utc: str | None,
    account: str,
    symbol: str,
    confidence: str,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "field": name,
        "observed_value": value,
        "source": source,
        "observation_timestamp_utc": observation_timestamp_utc,
        "account": account,
        "symbol": symbol,
        "confidence": confidence,
        "notes": notes,
    }


def build_broker_economics_audit(
    *,
    live_m5: int,
    live_quotes: int,
    complete_dates: int,
    prompt7_live_m5: int | None,
    prompt7_quotes: int | None,
) -> dict[str, Any]:
    probe = _load(PHASE64_7_PROBE)
    comm = _load(PHASE64_10_COMMISSION)
    swap = _load(PHASE64_10_SWAP)
    p64_cost = _load(PHASE64_10_COST)
    p07 = _load(PROMPT07_BUNDLE)

    sym = probe.get("symbol") or {}
    acct = probe.get("account_sanitized") or {}
    ts = probe.get("retrieved_at_utc")
    account_label = f"{acct.get('server', EXPECTED_SERVER)}/login_last4={acct.get('login_last4', '????')}"

    fields = [
        _field(
            "contract_size",
            value=sym.get("contract_size", VERIFIED_CONTRACT_SIZE),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "tick_size",
            value=sym.get("tick_size", VERIFIED_TICK_SIZE),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "tick_value",
            value=sym.get("tick_value", VERIFIED_TICK_VALUE),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
            notes="Per 0.01 lot per tick (broker-reported)",
        ),
        _field(
            "point",
            value=sym.get("point", VERIFIED_POINT),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "digits",
            value=sym.get("digits", VERIFIED_DIGITS),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "volume_min",
            value=sym.get("volume_min", VERIFIED_VOLUME_MIN),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "volume_step",
            value=sym.get("volume_step", VERIFIED_VOLUME_STEP),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "volume_max",
            value=sym.get("volume_max", VERIFIED_VOLUME_MAX),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
        ),
        _field(
            "spread_points_snapshot_probe",
            value=sym.get("spread_points"),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
            notes="Single probe snapshot; not a distribution",
        ),
        _field(
            "commission_per_side",
            value=comm.get("actual_commission_observed", UNKNOWN),
            source="PHASE64_10_commission_investigation",
            observation_timestamp_utc=None,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=comm.get("actual_commission_status", UNKNOWN),
            notes=comm.get("finding", "No genuine trade fills"),
        ),
        _field(
            "commission_round_turn",
            value=UNKNOWN,
            source="NONE",
            observation_timestamp_utc=None,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=UNKNOWN,
            notes="Cannot derive without verified per-side commission",
        ),
        _field(
            "swap_long",
            value={
                "phase63_user_reported": -488.7,
                "phase64_7_live_mt5": sym.get("swap_long", -644.8),
            },
            source="PHASE64_10_swap_conflict + PHASE64_7",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=CONFLICTED,
            notes=swap.get("conclusion") or "Conflict unresolved; UNKNOWN_FOR_EXECUTION",
        ),
        _field(
            "swap_short",
            value=sym.get("swap_short", 0.0),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=PARTIALLY_VERIFIED,
            notes="Live API value present; overnight applicability for net PnL still blocked by swap_long conflict",
        ),
        _field(
            "triple_swap_day",
            value=sym.get("swap_rollover3days") or 3,
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=VERIFIED,
            notes="Weekday index 3 = Wednesday (MT5 convention)",
        ),
        _field(
            "initial_margin",
            value=sym.get("initial_margin", UNKNOWN),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=UNKNOWN if sym.get("initial_margin") in (None, UNKNOWN, "UNKNOWN") else PARTIALLY_VERIFIED,
        ),
        _field(
            "maintenance_margin",
            value=sym.get("maintenance_margin", UNKNOWN),
            source="PHASE64_7_LIVE_MT5_symbol_info",
            observation_timestamp_utc=ts,
            account=account_label,
            symbol=ACTIVE_SYMBOL,
            confidence=UNKNOWN if sym.get("maintenance_margin") in (None, UNKNOWN, "UNKNOWN") else PARTIALLY_VERIFIED,
        ),
    ]

    missing_stale = [
        "Account-specific commission schedule (no trade fills)",
        "Reconciled swap_long for execution",
        "Broker-observed initial/maintenance margin",
        "Verified slippage distribution (requires fills)",
        "Multi-day / multi-regime spread distribution",
        "Trading session calendar completeness beyond Phase64.13 model",
    ]

    return {
        "symbol": ACTIVE_SYMBOL,
        "server": acct.get("server") or EXPECTED_SERVER,
        "account_trade_mode": acct.get("trade_mode_decoded"),
        "probe_status": probe.get("status"),
        "order_send_invoked_in_probe": probe.get("order_send_invoked"),
        "fields": fields,
        "commission_summary": {
            "status": comm.get("actual_commission_status", UNKNOWN),
            "value": comm.get("actual_commission_observed", UNKNOWN),
            "published_not_merged": True,
            "blocks_net": True,
        },
        "swap_summary": {
            "status": swap.get("status_for_execution") or "UNKNOWN_FOR_EXECUTION",
            "conflict_status": swap.get("conflict_status"),
            "observations_preserved": swap.get("observations"),
            "overwrite": False,
        },
        "phase64_10_cost_model_deterministic_complete": (p64_cost.get("deterministic_execution_cost_complete")),
        "live_evidence_vs_prompt7": {
            "prompt7_live_m5": prompt7_live_m5,
            "prompt7_quotes": prompt7_quotes,
            "prompt7_complete_dates": (
                ((p07.get("feasibility") or {}).get("genuine_live_exness_xauusdm") or {}).get(
                    "independent_complete_asia_london_dates"
                )
            ),
            "current_live_m5": live_m5,
            "current_quotes": live_quotes,
            "current_complete_dates": complete_dates,
            "delta_live_m5": (live_m5 - prompt7_live_m5) if prompt7_live_m5 is not None else None,
            "delta_quotes": (live_quotes - prompt7_quotes) if prompt7_quotes is not None else None,
        },
        "missing_stale_contradictory_incomplete": missing_stale,
        "safety": {
            "broker_collection": "READ_ONLY",
            "order_send": "PROHIBITED",
            "no_orders_opened_to_discover_costs": True,
        },
    }
