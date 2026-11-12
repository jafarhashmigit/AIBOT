"""XAUUSDm account/symbol verification — user-reported vs required RO procedure."""

from __future__ import annotations

from typing import Any

from phase63.metadata import ACTIVE_SYMBOL, ACTIVE_XAUUSDM_SPEC, SUPERSEDED_SYMBOL, get_active_symbol
from phase64_4.constants import canonical_json_sha256

USER_REPORTED_FIELDS = {
    "category": "Metals",
    "digits": 3,
    "contract_size": 100,
    "spread": "FLOATING",
    "margin_currency": "XAU",
    "profit_currency": "USD",
    "calculation": "FOREX",
    "execution": "MARKET",
    "filling": ["FOK", "IOC"],
    "volume_min": 0.01,
    "volume_max": 200,
    "volume_step": 0.01,
    "swap_long": -488.7,
    "swap_short": 0,
}

EXPLICIT_UNKNOWN = (
    "tick_size",
    "tick_value",
    "tick_value_profit",
    "tick_value_loss",
    "account_currency",
    "account_leverage",
    "complete_trading_sessions",
    "market_sell_margin_details",
    "commission_schedule",
    "actual_slippage",
    "actual_execution_latency",
    "server",
    "login",
)


def readonly_verification_checklist() -> list[dict[str, Any]]:
    """
    Exact RO procedure required before demo-execution authorization review.
    Uses only currently PERMITTED APIs conceptually; history_deals_get remains prohibited
    until a separate allowlist security review.
    """
    return [
        {
            "step": 1,
            "action": "Connect MT5 demo terminal manually; do not store credentials in AIBOT files",
            "api": "human / terminal UI",
            "records": ["server_name", "account_login_last4_only", "account_trade_mode=DEMO"],
        },
        {
            "step": 2,
            "action": "Read account_info (RO) — currency, leverage, company, server, trade_mode",
            "api": "account_info (permitted)",
            "must_match_or_record": ["currency", "leverage", "server", "login", "trade_mode"],
            "forbid": "Never write password; never infer DEMO from filename",
        },
        {
            "step": 3,
            "action": "Read symbol_info for exact name XAUUSDm (reject XAUUSD)",
            "api": "symbol_info (permitted)",
            "must_capture": [
                "digits",
                "point",
                "trade_tick_size",
                "trade_tick_value",
                "trade_contract_size",
                "volume_min/max/step",
                "trade_mode",
                "filling_mode",
                "swap_long/short",
                "currency_profit",
                "currency_margin",
            ],
        },
        {
            "step": 4,
            "action": "Capture bid/ask quote freshness timestamps from RO market data",
            "api": "copy_rates_* / terminal quotes (permitted market data)",
            "unknown_if_missing": ["actual_slippage", "actual_execution_latency"],
        },
        {
            "step": 5,
            "action": "Export trading sessions from Specification UI if API incomplete; mark PARTIAL if truncated",
            "api": "UI + optional symbol_info session fields",
            "rule": "Never invent closing times",
        },
        {
            "step": 6,
            "action": "Record commission schedule from account/broker documents; else UNKNOWN",
            "api": "human documentation — not invented",
            "rule": "Economics remain INCOMPLETE until account-specific commission known",
        },
        {
            "step": 7,
            "action": "Persist verification bundle with sha256; set verification_status=INDEPENDENTLY_VERIFIED only if all required fields present",
            "api": "AIBOT metadata writer (future phase)",
            "rule": "No silent fallback to XAUUSD profile",
        },
        {
            "step": 8,
            "action": "Deal/order history reconciliation requires SEPARATE allowlist review (history_deals_get currently PROHIBITED)",
            "api": "NOT AVAILABLE in Phase64.4",
            "rule": "Manual CSV History→Deals export remains the interim RO evidence path (Phase63)",
        },
    ]


def audit_symbol_configuration() -> dict[str, Any]:
    spec = dict(ACTIVE_XAUUSDM_SPEC)
    unknowns = {k: "UNKNOWN" for k in EXPLICIT_UNKNOWN}
    # From active spec where already UNKNOWN
    for k in ("tick_size", "tick_value", "account_currency", "account_leverage", "server"):
        unknowns[k] = spec.get(k, "UNKNOWN")
    invented = [k for k, v in unknowns.items() if v not in ("UNKNOWN", "TRUNCATED_UNKNOWN", None) and k in (
        "tick_size",
        "tick_value",
        "account_currency",
        "account_leverage",
    )]
    # tick fields must be UNKNOWN strings in active spec
    tick_ok = all(spec.get(f) == "UNKNOWN" for f in ("tick_size", "tick_value", "tick_value_profit", "tick_value_loss"))
    out = {
        "active_symbol": get_active_symbol(),
        "expected": ACTIVE_SYMBOL,
        "superseded": SUPERSEDED_SYMBOL,
        "user_reported_specifications": USER_REPORTED_FIELDS,
        "user_reported_not_independently_verified": True,
        "provenance": "USER_REPORTED_FROM_CONNECTED_MT5_SPECIFICATION",
        "verification_status_current": spec.get("verification_status"),
        "explicit_unknown": unknowns,
        "unknown_intact": tick_ok and spec.get("account_currency") == "UNKNOWN",
        "no_xauusd_fallback": get_active_symbol() == "XAUUSDm" and spec.get("symbol") == "XAUUSDm",
        "readonly_verification_checklist": readonly_verification_checklist(),
        "broker_execution_realism_claimed": False,
        "no_invented_fields": tick_ok and len(invented) == 0,
        "pass": get_active_symbol() == "XAUUSDm" and tick_ok and spec.get("digits") == 3,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
