"""Read-only MT5 connection (lazy MetaTrader5 import)."""

from __future__ import annotations

from typing import Any

import phase37.constants as C


def package_available() -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5  # noqa: F401

        return {
            "available": True,
            "version": getattr(mt5, "__version__", None),
            "package": "MetaTrader5",
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "version": None, "error": f"{type(exc).__name__}: {exc}"}


def terminal_exists() -> bool:
    from pathlib import Path

    return Path(C.TERMINAL_PATH).is_file()


def open_readonly(terminal_path: str | None = None) -> dict[str, Any]:
    path = terminal_path or C.TERMINAL_PATH
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"MetaTrader5 import failed: {exc}", "handle": None}
    if not mt5.initialize(path=path, timeout=C.INIT_TIMEOUT_MS):
        return {
            "status": "unavailable",
            "reason": f"initialize failed: {mt5.last_error()}",
            "handle": None,
            "terminal_path": path,
        }
    C.MT5_CONNECTIONS += 1
    info = mt5.terminal_info()
    account = mt5.account_info()
    # Never persist login / account number
    return {
        "status": "connected_readonly",
        "handle": mt5,
        "terminal_path": path,
        "terminal_connected": bool(getattr(info, "connected", False)) if info else False,
        "terminal_company": getattr(info, "company", None) if info else None,
        "terminal_name": getattr(info, "name", None) if info else None,
        "terminal_build": getattr(info, "build", None) if info else None,
        "server": getattr(account, "server", None) if account else None,
        "trade_mode": getattr(account, "trade_mode", None) if account else None,
        "trade_allowed_flag_present": bool(getattr(account, "trade_allowed", False)) if account else None,
        "note": "read-only qualification; no orders will be sent even if trade_allowed is True",
    }


def close_readonly(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.shutdown()
    except Exception:  # noqa: BLE001
        pass
