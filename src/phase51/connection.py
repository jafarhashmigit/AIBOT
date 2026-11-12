"""Read-only MT5 historical connection."""

from __future__ import annotations

from typing import Any

import phase51.constants as C


def open_readonly() -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"import: {exc}", "handle": None}
    if not mt5.initialize(path=C.TERMINAL_PATH, timeout=C.INIT_TIMEOUT_MS):
        return {"status": "unavailable", "reason": f"init: {mt5.last_error()}", "handle": None}
    C.MT5_CONNECTIONS += 1
    info = mt5.terminal_info()
    account = mt5.account_info()
    return {
        "status": "connected_readonly",
        "handle": mt5,
        "terminal_build": getattr(info, "build", None) if info else None,
        "server": getattr(account, "server", None) if account else None,
    }


def close_readonly(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.shutdown()
    except Exception:  # noqa: BLE001
        pass
