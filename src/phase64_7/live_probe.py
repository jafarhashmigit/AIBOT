"""
Bounded live read-only MT5 probe — reuses Phase64.6 LiveMt5Backend / adapter patterns.
Only Phase12 PERMITTED APIs. Never order_send / positions_get / history_* / symbol_select.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_6.readonly_adapter import LiveMt5Backend, ReadOnlyMetadataAdapter, account_identity_fingerprint
from phase64_7.constants import (
    ACTIVE_SYMBOL,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    PROBE_VERSION,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    canonical_json_sha256,
)

# Filling mode bit flags (MT5): 1=FOK, 2=IOC, 4=RETURN
_FILLING_FLAGS = {1: "FOK", 2: "IOC", 4: "RETURN"}
# trade_exemode: 0=request, 1=instant, 2=market, 3=exchange
_EXEC_MODES = {0: "REQUEST", 1: "INSTANT", 2: "MARKET", 3: "EXCHANGE"}
# account trade_mode: 0=demo, 1=contest, 2=real (MetaTrader5 docs)
_ACCT_TRADE_MODES = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
# swap_mode: 0=disabled, 1=points, 2=symbol currency, ...
_SWAP_MODES = {0: "DISABLED", 1: "POINTS", 2: "SYMBOL_CURRENCY", 3: "MARGIN_CURRENCY", 4: "DEPOSIT_CURRENCY"}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _g(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)


def _decode_filling(mask: Any) -> list[str] | str:
    if mask is None:
        return UNKNOWN
    try:
        m = int(mask)
    except Exception:
        return UNKNOWN
    out = [name for bit, name in _FILLING_FLAGS.items() if m & bit]
    return out or UNKNOWN


def sanitize_account(account: dict[str, Any]) -> dict[str, Any]:
    """Reports get fingerprint + last4 login only — never full raw login in sanitized view."""
    login = account.get("login")
    last4 = str(login)[-4:] if login is not None else UNKNOWN
    return {
        "login_last4": last4,
        "login_full_in_raw_only": True,
        "server": account.get("server"),
        "company": account.get("company"),
        "currency": account.get("currency"),
        "leverage": account.get("leverage"),
        "balance": account.get("balance"),
        "equity": account.get("equity"),
        "margin": account.get("margin"),
        "margin_free": account.get("margin_free"),
        "trade_mode": account.get("trade_mode"),
        "trade_mode_decoded": account.get("trade_mode_decoded"),
        "trade_allowed": account.get("trade_allowed"),
        "name": account.get("name"),
        "account_identity_fingerprint": account.get("account_identity_fingerprint"),
    }


def extended_live_capture(backend: LiveMt5Backend, *, symbol: str = ACTIVE_SYMBOL) -> dict[str, Any]:
    """Capture extended fields from same permitted APIs (symbol_info/account_info/terminal_info)."""
    retrieved_at = _utc()
    if not backend.initialize():
        return {
            "status": "PROBE_BLOCKED",
            "block_reason": "initialize_failed",
            "detail": str(backend.last_error()),
            "retrieved_at_utc": retrieved_at,
            "evidence_type": "LIVE_PROBE_ATTEMPT",
        }
    try:
        term = backend.terminal_info()
        acct = backend.account_info()
        sym = backend.symbol_info(symbol)
        ver = backend.version()
        rates = backend.copy_rates_from_pos(symbol, 5, 0, 1)

        if not bool(_g(term, "connected", False)):
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "terminal_disconnected",
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if acct is None:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "account_info_missing",
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if symbol == SUPERSEDED_SYMBOL:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "superseded_symbol_requested",
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if sym is None:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "symbol_unavailable",
                "note": "symbol_select PROHIBITED — cannot enable Market Watch",
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if _g(sym, "name") != symbol:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "wrong_symbol",
                "observed": _g(sym, "name"),
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }

        login = _g(acct, "login")
        server = _g(acct, "server")
        if str(login) != str(EXPECTED_DEMO_LOGIN):
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "account_identity_mismatch",
                "expected_login": EXPECTED_DEMO_LOGIN,
                "observed_login_last4": str(login)[-4:] if login is not None else None,
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if server != EXPECTED_SERVER:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "server_mismatch",
                "expected_server": EXPECTED_SERVER,
                "observed_server": server,
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }

        trade_mode = _g(acct, "trade_mode")
        account = {
            "login": login,
            "server": server or UNKNOWN,
            "company": _g(acct, "company") or UNKNOWN,
            "currency": _g(acct, "currency") or UNKNOWN,
            "leverage": _g(acct, "leverage") if _g(acct, "leverage") not in (None, 0) else UNKNOWN,
            "balance": _g(acct, "balance"),
            "equity": _g(acct, "equity"),
            "margin": _g(acct, "margin"),
            "margin_free": _g(acct, "margin_free"),
            "trade_mode": trade_mode,
            "trade_mode_decoded": _ACCT_TRADE_MODES.get(int(trade_mode), UNKNOWN)
            if trade_mode is not None
            else UNKNOWN,
            "trade_allowed": _g(acct, "trade_allowed"),
            "name": _g(acct, "name") or UNKNOWN,
        }
        account["account_identity_fingerprint"] = account_identity_fingerprint(account)

        tick_time = _g(sym, "time")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        age = (now_ts - int(tick_time)) if tick_time not in (None, 0) else UNKNOWN
        stale = age == UNKNOWN or (isinstance(age, int) and age > 120)

        tick_size = _g(sym, "trade_tick_size")
        tick_value = _g(sym, "trade_tick_value")
        tick_value_profit = _g(sym, "trade_tick_value_profit")
        tick_value_loss = _g(sym, "trade_tick_value_loss")
        # Treat broker-reported 0.0 margin fields as UNKNOWN (not usable as margin requirement)
        margin_initial = _g(sym, "margin_initial")
        margin_maintenance = _g(sym, "margin_maintenance")
        if margin_initial in (0, 0.0):
            margin_initial = UNKNOWN
        if margin_maintenance in (0, 0.0):
            margin_maintenance = UNKNOWN

        symbol_obs = {
            "name": _g(sym, "name"),
            "digits": _g(sym, "digits"),
            "point": _g(sym, "point"),
            "contract_size": _g(sym, "trade_contract_size"),
            "tick_size": tick_size if tick_size not in (None, 0) else UNKNOWN,
            "tick_value": tick_value if tick_value not in (None, 0) else UNKNOWN,
            "tick_value_profit": tick_value_profit if tick_value_profit not in (None, 0) else UNKNOWN,
            "tick_value_loss": tick_value_loss if tick_value_loss not in (None, 0) else UNKNOWN,
            "volume_min": _g(sym, "volume_min"),
            "volume_max": _g(sym, "volume_max"),
            "volume_step": _g(sym, "volume_step"),
            "profit_currency": _g(sym, "currency_profit") or UNKNOWN,
            "margin_currency": _g(sym, "currency_margin") or UNKNOWN,
            "execution_mode_raw": _g(sym, "trade_exemode"),
            "execution_mode": _EXEC_MODES.get(int(_g(sym, "trade_exemode")), UNKNOWN)
            if _g(sym, "trade_exemode") is not None
            else UNKNOWN,
            "filling_mode_bitmask": _g(sym, "filling_mode"),
            "filling_modes": _decode_filling(_g(sym, "filling_mode")),
            "stops_level": _g(sym, "trade_stops_level")
            if _g(sym, "trade_stops_level") is not None
            else (_g(sym, "stops_level") if _g(sym, "stops_level") is not None else UNKNOWN),
            "swap_mode_raw": _g(sym, "swap_mode"),
            "swap_type": _SWAP_MODES.get(int(_g(sym, "swap_mode")), UNKNOWN)
            if _g(sym, "swap_mode") is not None
            else UNKNOWN,
            "swap_long": _g(sym, "swap_long"),
            "swap_short": _g(sym, "swap_short"),
            "bid": _g(sym, "bid"),
            "ask": _g(sym, "ask"),
            "spread_points": _g(sym, "spread"),
            "spread_float": _g(sym, "spread_float"),
            "tick_time": tick_time,
            "tick_age_sec": age,
            "stale_tick": stale,
            "initial_margin": margin_initial,
            "maintenance_margin": margin_maintenance,
            "trading_sessions": UNKNOWN,  # not available via permitted APIs
            "commission_schedule": UNKNOWN,  # not on symbol_info
        }

        if stale:
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "stale_tick",
                "tick_age_sec": age,
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }
        if symbol_obs["bid"] in (None, 0) or symbol_obs["ask"] in (None, 0):
            return {
                "status": "PROBE_BLOCKED",
                "block_reason": "malformed_quotes",
                "retrieved_at_utc": retrieved_at,
                "evidence_type": "LIVE_PROBE_ATTEMPT",
            }

        terminal = {
            "connected": bool(_g(term, "connected", False)),
            "trade_allowed": bool(_g(term, "trade_allowed", False)),
            "tradeapi_disabled": _g(term, "tradeapi_disabled"),
            "path": _g(term, "path"),
            "build": _g(term, "build"),
            "company": _g(term, "company"),
        }

        raw = {
            "status": "LIVE_PROBE_OK",
            "probe_version": PROBE_VERSION,
            "retrieved_at_utc": retrieved_at,
            "evidence_type": "LIVE_MT5_API",
            "provenance": {
                "apis_used": sorted(
                    a
                    for a in (
                        "initialize",
                        "shutdown",
                        "last_error",
                        "terminal_info",
                        "account_info",
                        "symbol_info",
                        "copy_rates_from_pos",
                        "version",
                    )
                    if a in PERMITTED_MT5_API
                ),
                "prohibited_apis_called": [],
                "fixture_used": False,
                "allowlist_unchanged": True,
            },
            "mt5_version": ver,
            "account": account,
            "terminal": terminal,
            "symbol": symbol_obs,
            "rates_proxy_ok": rates is not None and len(list(rates)) > 0,
            "expected_symbol": ACTIVE_SYMBOL,
            "superseded_rejected": SUPERSEDED_SYMBOL,
        }
        return raw
    finally:
        backend.shutdown()


def run_live_probe() -> dict[str, Any]:
    """Attempt live probe; on import/init failure return PROBE_BLOCKED (no fabrication)."""
    try:
        backend = LiveMt5Backend()
    except Exception as exc:
        return {
            "status": "PROBE_BLOCKED",
            "block_reason": "backend_construct_failed",
            "detail": str(exc),
            "retrieved_at_utc": _utc(),
            "evidence_type": "LIVE_PROBE_ATTEMPT",
            "fixture_used": False,
        }
    try:
        raw = extended_live_capture(backend)
    except Exception as exc:
        return {
            "status": "PROBE_BLOCKED",
            "block_reason": "probe_exception",
            "detail": f"{type(exc).__name__}: {exc}",
            "retrieved_at_utc": _utc(),
            "evidence_type": "LIVE_PROBE_ATTEMPT",
            "fixture_used": False,
        }

    if raw.get("status") != "LIVE_PROBE_OK":
        raw["fixture_used"] = False
        raw["sha256"] = canonical_json_sha256({k: v for k, v in raw.items() if k != "sha256"})
        return raw

    sanitized = {
        "status": raw["status"],
        "probe_version": raw["probe_version"],
        "retrieved_at_utc": raw["retrieved_at_utc"],
        "evidence_type": raw["evidence_type"],
        "provenance": raw["provenance"],
        "mt5_version": raw["mt5_version"],
        "account_sanitized": sanitize_account(raw["account"]),
        "terminal": {k: v for k, v in raw["terminal"].items() if k != "path"}
        | {"path_present": bool(raw["terminal"].get("path"))},
        "symbol": raw["symbol"],
        "rates_proxy_ok": raw["rates_proxy_ok"],
        "fixture_used": False,
        "order_send_invoked": False,
        "credentials_persisted": False,
    }
    # Dual adapter path (64.6) for cross-check — same live backend instance would need re-init
    adapter_check = ReadOnlyMetadataAdapter(
        backend=LiveMt5Backend(),
        expected_symbol=ACTIVE_SYMBOL,
        expected_login=EXPECTED_DEMO_LOGIN,
        expected_server=EXPECTED_SERVER,
    ).fetch()
    out = {
        "status": "LIVE_PROBE_OK",
        "raw": raw,
        "sanitized": sanitized,
        "phase64_6_adapter_crosscheck": {
            "status": adapter_check.get("status"),
            "fail_closed": adapter_check.get("fail_closed"),
            "incomplete_fields": adapter_check.get("incomplete_fields"),
            "critical_metadata_complete": adapter_check.get("critical_metadata_complete"),
            "execution_authorized": adapter_check.get("execution_authorized"),
        },
        "prohibited_still_blocked": {
            k: k in PROHIBITED_MT5_API
            for k in ("order_send", "positions_get", "orders_get", "history_deals_get", "history_orders_get")
        },
    }
    out["sha256"] = canonical_json_sha256(
        {
            "status": out["status"],
            "sanitized": sanitized,
            "crosscheck_status": adapter_check.get("status"),
        }
    )
    return out
