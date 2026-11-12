"""Evidence inventory — tag every item; never promote estimates to account facts."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    CALCULATED,
    ESTIMATED,
    INVENTORY_VERSION,
    LIVE_ACCOUNT,
    SYNTHETIC_TEST,
    UNKNOWN,
    USER_REPORTED,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_CURRENCY,
    VERIFIED_DIGITS,
    VERIFIED_LEVERAGE,
    VERIFIED_SERVER,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
    VERIFIED_VOLUME_MAX,
    VERIFIED_VOLUME_MIN,
    VERIFIED_VOLUME_STEP,
    canonical_json_sha256,
)


def _item(
    evidence_id: str,
    *,
    description: str,
    evidence_type: str,
    source: str,
    value: Any = None,
    usable_as_account_execution_fact: bool,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "description": description,
        "evidence_type": evidence_type,
        "source": source,
        "value": value,
        "usable_as_account_execution_fact": usable_as_account_execution_fact,
        "notes": notes,
    }


def build_evidence_inventory() -> dict[str, Any]:
    items = [
        _item(
            "live_account_currency",
            description="Account deposit currency",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 account_info / Phase64.7",
            value=VERIFIED_CURRENCY,
            usable_as_account_execution_fact=True,
        ),
        _item(
            "live_leverage",
            description="Account leverage",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 account_info / Phase64.7",
            value=VERIFIED_LEVERAGE,
            usable_as_account_execution_fact=True,
            notes="Does not alone prove instrument margin formula",
        ),
        _item(
            "live_server",
            description="Broker server identity",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 account_info",
            value=VERIFIED_SERVER,
            usable_as_account_execution_fact=True,
        ),
        _item(
            "live_xauusdm_contract",
            description="XAUUSDm contract size / digits / tick size / tick value / volumes",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info / Phase64.7",
            value={
                "contract_size": VERIFIED_CONTRACT_SIZE,
                "digits": VERIFIED_DIGITS,
                "tick_size": VERIFIED_TICK_SIZE,
                "tick_value": VERIFIED_TICK_VALUE,
                "volume_min": VERIFIED_VOLUME_MIN,
                "volume_step": VERIFIED_VOLUME_STEP,
                "volume_max": VERIFIED_VOLUME_MAX,
            },
            usable_as_account_execution_fact=True,
        ),
        _item(
            "live_spread_snapshot",
            description="Bid/ask spread points at probe time",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info Phase64.7 (~240 points)",
            value=240,
            usable_as_account_execution_fact=True,
            notes="Snapshot only; floating spread",
        ),
        _item(
            "live_swap_long_current",
            description="symbol_info.swap_long at live probe",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info Phase64.7/64.11",
            value=-644.8,
            usable_as_account_execution_fact=True,
            notes="Point-in-time metadata rate; can change; not overnight charged proof",
        ),
        _item(
            "live_swap_short_current",
            description="symbol_info.swap_short",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info",
            value=0.0,
            usable_as_account_execution_fact=True,
        ),
        _item(
            "live_swap_mode_rollover3",
            description="swap_mode=POINTS; swap_rollover3days=Wednesday",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info",
            value={"swap_mode": 1, "rollover3days": 3},
            usable_as_account_execution_fact=True,
        ),
        _item(
            "live_margin_so_levels",
            description="Account margin call / stop-out levels",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 account_info Phase64.11",
            value={"margin_so_call": 60.0, "margin_so_so": 0.0, "margin_mode": 2},
            usable_as_account_execution_fact=True,
            notes="Stop-out policy levels; not required margin for a new XAUUSDm order",
        ),
        _item(
            "live_flat_account_margin",
            description="account.margin when flat",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 account_info",
            value=0.0,
            usable_as_account_execution_fact=True,
            notes="Expected zero with no positions; does not reveal required margin",
        ),
        _item(
            "live_symbol_margin_initial_api",
            description="symbol_info.margin_initial / margin_maintenance",
            evidence_type=LIVE_ACCOUNT,
            source="MT5 symbol_info",
            value={"margin_initial": 0.0, "margin_maintenance": 0.0},
            usable_as_account_execution_fact=False,
            notes="0.0 treated as unusable required-margin fact for metals",
        ),
        _item(
            "live_history_deals",
            description="history_deals_get window",
            evidence_type=LIVE_ACCOUNT,
            source="Phase64.8 RO collector",
            value={"n_trade_deals": 0, "n_balance_ops": 1},
            usable_as_account_execution_fact=True,
            notes="Balance credit only; commission=0 on balance is not trade commission proof",
        ),
        _item(
            "live_positions_orders_empty",
            description="positions_get / orders_get empty",
            evidence_type=LIVE_ACCOUNT,
            source="Phase64.8",
            value={"positions": 0, "orders": 0},
            usable_as_account_execution_fact=True,
        ),
        _item(
            "phase63_swap_long_user",
            description="User-reported XAUUSDm swap_long",
            evidence_type=USER_REPORTED,
            source="Phase63 ACTIVE_XAUUSDM_SPEC",
            value=-488.7,
            usable_as_account_execution_fact=False,
            notes="Preserved; conflicts with live -644.8",
        ),
        _item(
            "phase63_sessions_partial",
            description="User-reported partial trading sessions",
            evidence_type=USER_REPORTED,
            source="Phase63 metadata",
            value="PARTIAL with TRUNCATED segment_2_end",
            usable_as_account_execution_fact=False,
        ),
        _item(
            "phase63_margin_buy_usd_per_lot",
            description="User-reported market buy USD/lot margin",
            evidence_type=USER_REPORTED,
            source="Phase63 margin_rates",
            value=199.28,
            usable_as_account_execution_fact=False,
            notes="Sell rate null; initial/maintenance TRUNCATED",
        ),
        _item(
            "leverage_margin_estimate",
            description="notional/leverage estimate",
            evidence_type=CALCULATED,
            source="Phase64.10 margin_model",
            value="notional/leverage",
            usable_as_account_execution_fact=False,
        ),
        _item(
            "stress_cost_proxies",
            description="Phase64.10 combined stress USD proxies",
            evidence_type=ESTIMATED,
            source="Phase64.10 stress framework",
            usable_as_account_execution_fact=False,
        ),
        _item(
            "fake_broker_fixtures",
            description="Phase64.9 FakeBrokerBackend responses",
            evidence_type=SYNTHETIC_TEST,
            source="phase64_9.fake_broker",
            usable_as_account_execution_fact=False,
        ),
        _item(
            "exness_published_commission_generic",
            description="Generic Exness account-model commission schedules (not Trial15-mapped)",
            evidence_type=UNKNOWN,
            source="Not verified in-repo for this login/account type",
            value=UNKNOWN,
            usable_as_account_execution_fact=False,
            notes="External docs may exist but are not account-specific evidence here",
        ),
        _item(
            "mt5_session_schedule_api",
            description="Weekly symbol session schedule via Python MT5 API",
            evidence_type=UNKNOWN,
            source="MetaTrader5 package in this environment",
            value=UNKNOWN,
            usable_as_account_execution_fact=False,
            notes="No symbol_info_session_* APIs available; symbol_info.session_* are stats not schedules",
        ),
        _item(
            "order_calc_margin_api",
            description="MT5 order_calc_margin",
            evidence_type=UNKNOWN,
            source="Phase12 PROHIBITED",
            value="PROHIBITED_NOT_INVOKED",
            usable_as_account_execution_fact=False,
            notes="Exists on package but must not be called under current allowlist",
        ),
    ]

    by_type: dict[str, int] = {}
    for it in items:
        by_type[it["evidence_type"]] = by_type.get(it["evidence_type"], 0) + 1

    out = {
        "inventory_version": INVENTORY_VERSION,
        "n_items": len(items),
        "counts_by_type": by_type,
        "items": items,
        "rules": [
            "Estimates/synthetic/user-reported are never genuine account-specific execution evidence",
            "Published broker docs require explicit account-type applicability mapping",
            "Historical candle gaps are not session evidence",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
