"""Read-only MT5 security/permission matrix — Phase12 allowlist unchanged."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_6.constants import canonical_json_sha256

# Original Phase12 restriction rationale (from design intent + code comments)
RESTRICTION_RATIONALE = {
    "order_send": "Prevents any broker order submission; core safety invariant",
    "order_check": "Pre-trade validation still implies trading pipeline; kept out of RO surface",
    "order_calc_margin": "Could be used to size live risk; deferred pending security review",
    "order_calc_profit": "Trading-economics helper adjacent to execution; deferred",
    "positions_get": "Exposes live positions; useful for recon but not authorized in Phase12 RO",
    "positions_total": "Same class as positions_get",
    "orders_get": "Exposes open orders; recon need; currently PROHIBITED",
    "orders_total": "Same class as orders_get",
    "history_orders_get": "Historical order pull; recon need; currently PROHIBITED",
    "history_deals_get": "Historical deal pull; recon need; currently PROHIBITED",
    "buy": "High-level trade wrapper — submission risk",
    "sell": "High-level trade wrapper — submission risk",
    "Close": "Position close — mutates broker state",
    "symbol_select": "Mutates Market Watch (Phase12B correction removed enable=True)",
}


def api_row(name: str) -> dict[str, Any]:
    permitted = name in PERMITTED_MT5_API
    prohibited = name in PROHIBITED_MT5_API
    readiness_role = {
        "initialize": "Connect terminal session (RO)",
        "shutdown": "Close session",
        "last_error": "Diagnose connect/read failures",
        "terminal_info": "Connection/trade-allowed flags",
        "account_info": "Account identity, currency, leverage, trade mode",
        "symbol_info": "XAUUSDm contract specs + bid/ask/time when broker provides",
        "copy_rates_from": "Historical rates (staleness context)",
        "copy_rates_from_pos": "Recent bars for freshness proxy",
        "copy_rates_range": "Range rates",
        "version": "Terminal/API version provenance",
        "positions_get": "Open positions for exposure/recon — BLOCKED today",
        "orders_get": "Open orders for recon — BLOCKED today",
        "history_orders_get": "Historical orders — BLOCKED today",
        "history_deals_get": "Historical deals — BLOCKED today",
        "order_calc_margin": "Margin estimate helper — BLOCKED today",
        "order_calc_profit": "Profit calc helper — BLOCKED today",
        "order_send": "ORDER SUBMISSION — must remain blocked",
        "symbol_select": "Market Watch mutation — blocked",
    }.get(name, "See matrix")

    data_exposure = {
        "account_info": "login, server, company, currency, leverage, balance, equity, margin, trade_mode (no password)",
        "terminal_info": "connected, trade_allowed, path, community flags",
        "symbol_info": "digits, point, trade_tick_size/value, volumes, sessions fields, bid/ask/time if present",
        "copy_rates_*": "OHLCV bars — not order books",
        "positions_get": "Open position tickets, volumes, prices, profit",
        "orders_get": "Pending/open order tickets",
        "history_*": "Historical tickets/deals — high sensitivity for evidence",
        "order_send": "Would submit orders — highest risk",
    }
    key = name if name in data_exposure else (
        "copy_rates_*" if name.startswith("copy_rates") else name
    )

    failure_modes = [
        "terminal_disconnected",
        "initialize_timeout",
        "null_info_objects",
        "stale_or_zero_quotes",
        "symbol_not_visible_without_symbol_select",
        "account_switch_mid_session",
    ]

    return {
        "api": name,
        "phase12_status": "PERMITTED" if permitted else ("PROHIBITED" if prohibited else "UNLISTED"),
        "phase64_6_may_use": permitted and not prohibited,
        "readiness_role": readiness_role,
        "data_exposure": data_exposure.get(key, "See MT5 docs; no credentials"),
        "failure_modes": failure_modes,
        "security_implications": RESTRICTION_RATIONALE.get(name, "Unlisted — treat as forbidden until reviewed"),
        "allowlist_change_in_phase64_6": False,
    }


def build_security_matrix() -> dict[str, Any]:
    names = sorted(set(PERMITTED_MT5_API) | set(PROHIBITED_MT5_API))
    rows = [api_row(n) for n in names]
    needed_blocked = [
        r
        for r in rows
        if r["api"]
        in (
            "positions_get",
            "orders_get",
            "history_orders_get",
            "history_deals_get",
            "order_calc_margin",
            "order_calc_profit",
        )
        and r["phase12_status"] == "PROHIBITED"
    ]
    out = {
        "title": "Phase64.6 Read-only MT5 security/permission matrix",
        "allowlist_modified": False,
        "permitted_count": len(PERMITTED_MT5_API),
        "prohibited_count": len(PROHIBITED_MT5_API),
        "rows": rows,
        "minimum_ro_capabilities_available_now": sorted(PERMITTED_MT5_API),
        "minimum_ro_capabilities_blocked_pending_review": [r["api"] for r in needed_blocked],
        "separate_security_review_proposal": {
            "status": "PROPOSAL_ONLY_NOT_APPROVED",
            "proposed_additions_for_future_review": [
                {
                    "api": "positions_get",
                    "purpose": "Read open exposure for recon/risk without submission",
                    "mitigations": ["RO wrapper only", "no Close", "AST allowlist audit", "demo-login gate"],
                },
                {
                    "api": "orders_get",
                    "purpose": "Discover open orders after crash/timeout without resubmit",
                    "mitigations": ["RO wrapper", "idempotent journal", "no order_send"],
                },
                {
                    "api": "history_deals_get",
                    "purpose": "Native deal evidence vs CSV export",
                    "mitigations": ["append-only evidence journal", "no live/hist store merge"],
                },
                {
                    "api": "history_orders_get",
                    "purpose": "Order history for recon",
                    "mitigations": ["same as history_deals_get"],
                },
            ],
            "explicitly_never_proposed_here": ["order_send", "buy", "sell", "Close"],
            "note": "Phase64.6 does NOT expand allowlist; proposal is for a separate approval phase",
        },
        "pass": "order_send" in PROHIBITED_MT5_API and "symbol_info" in PERMITTED_MT5_API,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
