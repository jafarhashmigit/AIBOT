"""
Read-only MT5 evidence backends.

Live path uses only Phase12 PERMITTED APIs.
Never calls order_send / buy / sell / Close / symbol_select.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from phase64_8.constants import (
    ACTIVE_SYMBOL,
    API_TIMEOUT_SEC,
    COLLECTOR_VERSION,
    DEFAULT_HISTORY_LOOKBACK_DAYS,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    UNKNOWN,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _g(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())
    # namedtuple / MT5 Trade* objects
    keys = [k for k in dir(obj) if not k.startswith("_") and not callable(getattr(obj, k, None))]
    out = {}
    for k in keys:
        try:
            out[k] = getattr(obj, k)
        except Exception:
            continue
    return out


class EvidenceBackend(Protocol):
    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def positions_get(self, symbol: str | None = None) -> Any: ...
    def orders_get(self, symbol: str | None = None) -> Any: ...
    def history_deals_get(self, date_from: datetime, date_to: datetime) -> Any: ...
    def history_orders_get(self, date_from: datetime, date_to: datetime) -> Any: ...


@dataclass
class FakeEvidenceBackend:
    """Deterministic fixture backend — SIMULATED only."""

    connected: bool = True
    fail_initialize: bool = False
    timeout: bool = False
    malformed: bool = False
    account: dict[str, Any] = field(
        default_factory=lambda: {
            "login": EXPECTED_DEMO_LOGIN,
            "server": EXPECTED_SERVER,
            "company": "Exness Technologies Ltd",
            "currency": "USD",
            "leverage": 2000,
            "balance": 500.0,
            "equity": 500.0,
            "margin": 0.0,
            "trade_mode": 0,
            "name": "AIBOT",
        }
    )
    positions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    deals: list[dict[str, Any]] = field(default_factory=list)
    hist_orders: list[dict[str, Any]] = field(default_factory=list)
    call_log: list[str] = field(default_factory=list)

    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool:
        self.call_log.append("initialize")
        if self.fail_initialize or not self.connected:
            return False
        return True

    def shutdown(self) -> None:
        self.call_log.append("shutdown")

    def last_error(self) -> Any:
        if self.timeout:
            return (-1, "timeout")
        if not self.connected:
            return (-10001, "disconnected")
        return (1, "Success")

    def terminal_info(self) -> Any:
        self.call_log.append("terminal_info")
        if self.malformed:
            return {"connected": "yes"}  # malformed type
        return {"connected": self.connected, "trade_allowed": True}

    def account_info(self) -> Any:
        self.call_log.append("account_info")
        if not self.connected:
            return None
        return dict(self.account)

    def positions_get(self, symbol: str | None = None) -> Any:
        self.call_log.append(f"positions_get:{symbol}")
        if self.timeout:
            return None
        if not self.connected:
            return None
        rows = self.positions
        if symbol:
            rows = [p for p in rows if p.get("symbol") == symbol]
        return tuple(rows)

    def orders_get(self, symbol: str | None = None) -> Any:
        self.call_log.append(f"orders_get:{symbol}")
        if self.timeout:
            return None
        if not self.connected:
            return None
        rows = self.orders
        if symbol:
            rows = [o for o in rows if o.get("symbol") == symbol]
        return tuple(rows)

    def history_deals_get(self, date_from: datetime, date_to: datetime) -> Any:
        self.call_log.append("history_deals_get")
        if self.timeout:
            return None
        if not self.connected:
            return None
        return tuple(self.deals)

    def history_orders_get(self, date_from: datetime, date_to: datetime) -> Any:
        self.call_log.append("history_orders_get")
        if self.timeout:
            return None
        if not self.connected:
            return None
        return tuple(self.hist_orders)


class LiveEvidenceBackend:
    """Live MetaTrader5 backend — import only inside methods; RO APIs only."""

    def __init__(self) -> None:
        self._mt5 = None
        self.timeout_sec = API_TIMEOUT_SEC

    def _mod(self):
        if self._mt5 is None:
            import MetaTrader5 as mt5  # noqa: WPS433 — intentional lazy import

            self._mt5 = mt5
        return self._mt5

    def initialize(self, *, path: str | None = None, timeout: int = 60000) -> bool:
        mt5 = self._mod()
        if path:
            return bool(mt5.initialize(path=path, timeout=timeout))
        return bool(mt5.initialize(timeout=timeout))

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def last_error(self) -> Any:
        return self._mod().last_error()

    def terminal_info(self) -> Any:
        return self._mod().terminal_info()

    def account_info(self) -> Any:
        return self._mod().account_info()

    def positions_get(self, symbol: str | None = None) -> Any:
        mt5 = self._mod()
        if symbol:
            return mt5.positions_get(symbol=symbol)
        return mt5.positions_get()

    def orders_get(self, symbol: str | None = None) -> Any:
        mt5 = self._mod()
        if symbol:
            return mt5.orders_get(symbol=symbol)
        return mt5.orders_get()

    def history_deals_get(self, date_from: datetime, date_to: datetime) -> Any:
        return self._mod().history_deals_get(date_from, date_to)

    def history_orders_get(self, date_from: datetime, date_to: datetime) -> Any:
        return self._mod().history_orders_get(date_from, date_to)


def default_history_window(
    *, lookback_days: int = DEFAULT_HISTORY_LOOKBACK_DAYS
) -> tuple[datetime, datetime]:
    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=lookback_days)
    return date_from, date_to


__all__ = [
    "ACTIVE_SYMBOL",
    "COLLECTOR_VERSION",
    "EvidenceBackend",
    "FakeEvidenceBackend",
    "LiveEvidenceBackend",
    "UNKNOWN",
    "_as_dict",
    "_g",
    "_utc",
    "default_history_window",
]
