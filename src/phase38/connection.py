"""Read-only MT5 connection for historical retrieval only."""

from __future__ import annotations

from typing import Any

import phase38.constants as C


def open_readonly() -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"import failed: {exc}", "handle": None}
    ver = getattr(mt5, "__version__", None)
    if not mt5.initialize(path=C.TERMINAL_PATH, timeout=C.INIT_TIMEOUT_MS):
        return {"status": "unavailable", "reason": f"initialize failed: {mt5.last_error()}", "handle": None}
    C.MT5_CONNECTIONS += 1
    info = mt5.terminal_info()
    account = mt5.account_info()
    sym = mt5.symbol_info(C.SYMBOL)
    return {
        "status": "connected_readonly",
        "handle": mt5,
        "package_version": ver,
        "terminal_build": getattr(info, "build", None) if info else None,
        "terminal_connected": bool(getattr(info, "connected", False)) if info else False,
        "server": getattr(account, "server", None) if account else None,
        "symbol_ok": sym is not None,
        "symbol_digits": getattr(sym, "digits", None) if sym else None,
        "symbol_point": getattr(sym, "point", None) if sym else None,
        "provenance": {
            "terminal_path": C.TERMINAL_PATH,
            "expected_server": C.SOURCE_SERVER_LABEL,
            "symbol": C.SYMBOL,
            "note": "MetaQuotes-Demo is not live broker execution truth",
        },
    }


def close_readonly(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.shutdown()
    except Exception:  # noqa: BLE001
        pass
