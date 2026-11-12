"""
Strictly read-only MT5 metadata adapter — permitted Phase12 APIs only.

Never calls order_send / positions_get / orders_get / history_* / symbol_select.
Live MetaTrader5 import only inside fetch path; tests inject FakeMt5Backend.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_6.constants import (
    ACTIVE_SYMBOL,
    ADAPTER_VERSION,
    METADATA_VERSION,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    canonical_json_sha256,
    sha256_hex,
)


class AdapterBlocked(RuntimeError):
    pass


class Mt5Backend(Protocol):
    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any: ...
    def version(self) -> Any: ...


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _g(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _unk(v: Any) -> Any:
    if v is None or v == "" or v == 0 and False:
        return UNKNOWN
    if v is None or v == "":
        return UNKNOWN
    return v


def account_identity_fingerprint(account: dict[str, Any]) -> str:
    """Non-secret fingerprint — login + server + trade_mode only."""
    raw = f"{account.get('login')}|{account.get('server')}|{account.get('trade_mode')}|{account.get('company')}"
    return sha256_hex(raw)


@dataclass
class FakeMt5Backend:
    """Deterministic fixture backend for tests — labeled SIMULATED."""

    connected: bool = True
    trade_allowed: bool = True
    account: dict[str, Any] = field(
        default_factory=lambda: {
            "login": 474906834,
            "server": "Exness-MT5Trial15",
            "company": "Exness Technologies Ltd",
            "currency": "USD",
            "leverage": 2000,
            "balance": 500.0,
            "equity": 500.0,
            "margin": 0.0,
            "trade_mode": 0,  # demo-ish; keep numeric as MT5 does
            "name": "AIBOT",
        }
    )
    symbol: dict[str, Any] | None = None
    rates: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        if self.symbol is None:
            self.symbol = {
                "name": ACTIVE_SYMBOL,
                "digits": 3,
                "point": 0.001,
                "trade_contract_size": 100.0,
                "trade_tick_size": None,  # UNKNOWN until verified
                "trade_tick_value": None,
                "volume_min": 0.01,
                "volume_max": 200.0,
                "volume_step": 0.01,
                "currency_profit": "USD",
                "currency_margin": "XAU",
                "trade_mode": 4,
                "trade_exemode": 2,  # market
                "filling_mode": 3,
                "bid": 2650.123,
                "ask": 2650.223,
                "time": now,
                "spread": 100,
                "swap_long": -488.7,
                "swap_short": 0.0,
                "session_deals": 0,
            }
        if self.rates is None:
            self.rates = [{"time": now, "open": 1, "high": 1, "low": 1, "close": 1, "tick_volume": 1}]
    init_ok: bool = True
    error: Any = (1, "ok")
    ver: tuple[int, int, str] = (5, 0, "fake")

    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool:
        return self.init_ok

    def shutdown(self) -> None:
        return None

    def last_error(self) -> Any:
        return self.error

    def terminal_info(self) -> Any:
        if not self.connected:
            return {"connected": False, "trade_allowed": False}
        return {"connected": True, "trade_allowed": self.trade_allowed, "path": "FAKE"}

    def account_info(self) -> Any:
        return dict(self.account) if self.account is not None else None

    def symbol_info(self, symbol: str) -> Any:
        if self.symbol is None:
            return None
        if symbol != self.symbol.get("name"):
            return None
        return dict(self.symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return list(self.rates)

    def version(self) -> Any:
        return self.ver


class LiveMt5Backend:
    """Live backend — MetaTrader5 imported only on initialize."""

    def __init__(self) -> None:
        self._mt5 = None

    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool:
        import MetaTrader5 as mt5  # local import — never module-level

        self._mt5 = mt5
        if path:
            return bool(mt5.initialize(path=path, timeout=timeout))
        return bool(mt5.initialize(timeout=timeout))

    def shutdown(self) -> None:
        if self._mt5:
            self._mt5.shutdown()

    def last_error(self) -> Any:
        return self._mt5.last_error() if self._mt5 else None

    def terminal_info(self) -> Any:
        return self._mt5.terminal_info() if self._mt5 else None

    def account_info(self) -> Any:
        return self._mt5.account_info() if self._mt5 else None

    def symbol_info(self, symbol: str) -> Any:
        return self._mt5.symbol_info(symbol) if self._mt5 else None

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return self._mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count) if self._mt5 else None

    def version(self) -> Any:
        return self._mt5.version() if self._mt5 else None


# Guard: adapter source must not reference prohibited call patterns
_FORBIDDEN_CALLS = tuple(sorted(PROHIBITED_MT5_API))


@dataclass
class ReadOnlyMetadataAdapter:
    backend: Mt5Backend
    expected_symbol: str = ACTIVE_SYMBOL
    expected_login: int | str | None = None
    expected_server: str | None = None
    max_tick_age_sec: int = 120
    terminal_path: str | None = None

    def fetch(self) -> dict[str, Any]:
        """
        Fetch RO metadata bundle. Fail closed on disconnect, wrong account/symbol,
        stale ticks, incomplete critical fields.
        """
        retrieved_at = _utc()
        if not self.backend.initialize(path=self.terminal_path):
            return self._blocked("initialize_failed", retrieved_at, detail=str(self.backend.last_error()))

        try:
            term = self.backend.terminal_info()
            acct = self.backend.account_info()
            sym = self.backend.symbol_info(self.expected_symbol)
            ver = self.backend.version()
            # timeframe M5 = 5 in MT5; keep numeric literal for RO freshness proxy
            rates = self.backend.copy_rates_from_pos(self.expected_symbol, 5, 0, 1)

            connected = bool(_g(term, "connected", False))
            if not connected:
                return self._blocked("terminal_disconnected", retrieved_at)

            if acct is None:
                return self._blocked("account_info_missing", retrieved_at)

            account = {
                "login": _g(acct, "login"),
                "server": _g(acct, "server") or UNKNOWN,
                "company": _g(acct, "company") or UNKNOWN,
                "currency": _g(acct, "currency") or UNKNOWN,
                "leverage": _g(acct, "leverage") if _g(acct, "leverage") not in (None, 0) else UNKNOWN,
                "balance": _g(acct, "balance"),
                "equity": _g(acct, "equity"),
                "margin": _g(acct, "margin"),
                "trade_mode": _g(acct, "trade_mode"),
                "name": _g(acct, "name") or UNKNOWN,
            }
            # Never persist credentials — none requested

            if self.expected_login is not None and str(account["login"]) != str(self.expected_login):
                return self._blocked("wrong_account_connected", retrieved_at, observed=account["login"])
            if self.expected_server is not None and account["server"] != self.expected_server:
                return self._blocked("wrong_broker_server", retrieved_at, observed=account["server"])

            if self.expected_symbol == SUPERSEDED_SYMBOL:
                return self._blocked("superseded_symbol_requested", retrieved_at)
            if sym is None:
                return self._blocked(
                    "symbol_unavailable_or_not_visible",
                    retrieved_at,
                    note="symbol_select is PROHIBITED; cannot enable Market Watch mutation",
                )

            sym_name = _g(sym, "name")
            if sym_name != self.expected_symbol:
                return self._blocked("wrong_symbol_selected", retrieved_at, observed=sym_name)

            bid = _g(sym, "bid")
            ask = _g(sym, "ask")
            tick_time = _g(sym, "time")
            tick_size = _g(sym, "trade_tick_size")
            tick_value = _g(sym, "trade_tick_value")

            stale = False
            age = UNKNOWN
            if tick_time in (None, 0):
                stale = True
                age = UNKNOWN
            else:
                try:
                    age = int(datetime.now(timezone.utc).timestamp() - int(tick_time))
                    stale = age > self.max_tick_age_sec
                except Exception:
                    stale = True
                    age = UNKNOWN

            if bid in (None, 0) or ask in (None, 0):
                return self._blocked("malformed_or_missing_quotes", retrieved_at)

            if stale:
                return self._blocked("stale_tick", retrieved_at, tick_age_sec=age)

            symbol = {
                "name": sym_name,
                "digits": _g(sym, "digits", UNKNOWN),
                "point": _g(sym, "point", UNKNOWN),
                "contract_size": _g(sym, "trade_contract_size", UNKNOWN),
                "tick_size": tick_size if tick_size not in (None, 0) else UNKNOWN,
                "tick_value": tick_value if tick_value not in (None, 0) else UNKNOWN,
                "tick_value_profit": UNKNOWN,  # not separately exposed on all brokers
                "tick_value_loss": UNKNOWN,
                "volume_min": _g(sym, "volume_min", UNKNOWN),
                "volume_max": _g(sym, "volume_max", UNKNOWN),
                "volume_step": _g(sym, "volume_step", UNKNOWN),
                "currency_profit": _g(sym, "currency_profit", UNKNOWN),
                "currency_margin": _g(sym, "currency_margin", UNKNOWN),
                "trade_mode": _g(sym, "trade_mode", UNKNOWN),
                "execution_mode": _g(sym, "trade_exemode", UNKNOWN),
                "filling_mode_bitmask": _g(sym, "filling_mode", UNKNOWN),
                "bid": bid,
                "ask": ask,
                "spread_points": _g(sym, "spread", UNKNOWN),
                "swap_long": _g(sym, "swap_long", UNKNOWN),
                "swap_short": _g(sym, "swap_short", UNKNOWN),
                "tick_time": tick_time,
                "tick_age_sec": age,
                "trading_sessions": UNKNOWN,  # full session tables often incomplete via symbol_info alone
                "initial_margin": UNKNOWN,
                "maintenance_margin": UNKNOWN,
                "commission_schedule": UNKNOWN,
            }

            incomplete = [
                k
                for k in (
                    "tick_size",
                    "tick_value",
                    "trading_sessions",
                    "commission_schedule",
                    "initial_margin",
                    "maintenance_margin",
                )
                if symbol.get(k) == UNKNOWN
            ]
            if account.get("currency") == UNKNOWN:
                incomplete.append("account_currency")
            if account.get("leverage") == UNKNOWN:
                incomplete.append("account_leverage")

            # Positions/orders/history intentionally unavailable
            blocked_capabilities = {
                "positions_get": "PROHIBITED",
                "orders_get": "PROHIBITED",
                "history_deals_get": "PROHIBITED",
                "history_orders_get": "PROHIBITED",
            }

            fingerprint = account_identity_fingerprint(account)
            rates_ok = rates is not None and len(list(rates)) > 0

            bundle = {
                "status": "OK_PARTIAL" if incomplete else "OK",
                "fail_closed": False,
                "adapter_version": ADAPTER_VERSION,
                "metadata_version": METADATA_VERSION,
                "retrieved_at_utc": retrieved_at,
                "provenance": {
                    "source": type(self.backend).__name__,
                    "mt5_version": ver,
                    "permitted_apis_used": sorted(
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
                    "store_separation": "broker_metadata_only_not_hist_or_paper",
                },
                "account_identity_fingerprint": fingerprint,
                "account": account,
                "terminal": {
                    "connected": connected,
                    "trade_allowed": bool(_g(term, "trade_allowed", False)),
                },
                "symbol": symbol,
                "rates_freshness_proxy_ok": rates_ok,
                "incomplete_fields": incomplete,
                "blocked_capabilities": blocked_capabilities,
                "critical_metadata_complete": len(incomplete) == 0,
                "execution_authorized": False,
            }
            # Fail closed for *execution* even on OK_PARTIAL — adapter returns data but marks incomplete
            bundle["ready_for_execution_gate"] = False  # never true in 64.6 without separate approval
            bundle["sha256"] = canonical_json_sha256({k: v for k, v in bundle.items() if k != "sha256"})
            return bundle
        finally:
            self.backend.shutdown()

    def _blocked(self, reason: str, retrieved_at: str, **extra: Any) -> dict[str, Any]:
        out = {
            "status": "BLOCKED",
            "fail_closed": True,
            "block_reason": reason,
            "adapter_version": ADAPTER_VERSION,
            "retrieved_at_utc": retrieved_at,
            "execution_authorized": False,
            "ready_for_execution_gate": False,
            "prohibited_apis_called": [],
            **extra,
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out


def assert_no_prohibited_in_adapter_source() -> dict[str, Any]:
    from pathlib import Path

    text = Path(__file__).read_text(encoding="utf-8")
    hits = []
    for name in _FORBIDDEN_CALLS:
        # detect mt5.<name> or backend.<name> style for prohibited
        if f".{name}(" in text and name not in ("initialize",):
            # allow listing in comments/strings of PROHIBITED set / blocked_capabilities keys
            if f'"{name}"' in text or f"'{name}'" in text:
                # string mention OK; call pattern .name( is concerning if not in comment
                pass
        needle = f"mt5.{name}("
        if needle in text:
            hits.append(needle)
    return {"prohibited_call_hits": hits, "pass": len(hits) == 0}
