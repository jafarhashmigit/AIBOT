"""Symbol discovery for gold / XAUUSD (no symbol_select)."""

from __future__ import annotations

from typing import Any

from phase37.constants import PREFERRED_SYMBOL


def _safe_attrs(si: Any) -> dict[str, Any]:
    keys = [
        "name",
        "path",
        "description",
        "digits",
        "point",
        "trade_tick_size",
        "trade_tick_value",
        "trade_contract_size",
        "volume_min",
        "volume_max",
        "volume_step",
        "spread",
        "spread_float",
        "trade_mode",
        "currency_base",
        "currency_profit",
        "currency_margin",
        "time",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        if hasattr(si, k):
            out[k] = getattr(si, k)
    return out


def discover_symbol(handle: Any, preferred: str = PREFERRED_SYMBOL) -> dict[str, Any]:
    preferred_info = handle.symbol_info(preferred)
    xau_like = []
    try:
        for pattern in ("*XAU*", "*GOLD*"):
            got = handle.symbols_get(pattern) or ()
            for s in got:
                xau_like.append({"name": s.name, "path": getattr(s, "path", None)})
    except Exception as exc:  # noqa: BLE001
        xau_like = [{"error": f"{type(exc).__name__}: {exc}"}]

    # Deduplicate by name
    seen = set()
    uniq = []
    for row in xau_like:
        n = row.get("name")
        if n and n not in seen:
            seen.add(n)
            uniq.append(row)

    if preferred_info is not None:
        return {
            "status": "ok",
            "selected_symbol": preferred,
            "selection_note": "preferred literal XAUUSD is available; no alternate auto-selected",
            "symbol_info": _safe_attrs(preferred_info),
            "xau_like_symbols": uniq[:40],
        }

    # Do not auto-select alternate — report only
    return {
        "status": "preferred_unavailable",
        "selected_symbol": None,
        "selection_note": "preferred XAUUSD missing; alternate gold symbols listed but NOT auto-selected",
        "symbol_info": None,
        "xau_like_symbols": uniq[:40],
    }
