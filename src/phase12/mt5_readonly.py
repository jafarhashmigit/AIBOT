"""Optional Stage B read-only MT5 adapter. Not imported during Stage A or 12B.

MetaTrader5 is imported only inside connect_readonly(), never at module import time.
No automatic terminal launch, reconnect loop, thread, or order wrapper.

Phase 12B correction: symbol_select(enable=True) removed — it mutates Market Watch.
Read-only probe uses symbol_info only.

Permitted API: see mt5_allowlist.PERMITTED_MT5_API.
"""

from __future__ import annotations

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API


class Mt5ReadOnlyError(RuntimeError):
    pass


def connect_readonly(terminal_path: str) -> dict:
    """Read-only connect probe. Not called by Stage A or Phase 12B."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return {"status": "unavailable", "reason": f"MetaTrader5 import failed: {exc}"}
    if not mt5.initialize(path=terminal_path, timeout=60000):
        err = mt5.last_error()
        return {"status": "unavailable", "reason": f"initialize failed: {err}"}
    try:
        info = mt5.terminal_info()
        account = mt5.account_info()
        symbol = mt5.symbol_info("XAUUSD")
        payload = {
            "status": "connected_readonly" if symbol is not None else "symbol_unavailable",
            "server": getattr(account, "server", None) if account else None,
            "terminal_connected": bool(getattr(info, "connected", False)) if info else None,
            "note": "observation probe only; no orders; Market Watch not mutated",
            "allowlist": sorted(PERMITTED_MT5_API),
            "denylist": sorted(PROHIBITED_MT5_API),
        }
    finally:
        mt5.shutdown()
    return payload
