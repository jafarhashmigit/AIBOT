"""Read-only safety: AST denylist + no Market Watch mutation."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from phase37.constants import PHASE37_PERMITTED_MT5_API, PHASE37_PROHIBITED_MT5_API, SRC_DIR


def _mt5_calls(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {"mt5", "MetaTrader5", "handle"}:
                names.append(node.attr)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in {"mt5", "MetaTrader5", "handle"}
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            names.append(node.args[1].value)
    return names


def audit_phase37_sources() -> dict[str, Any]:
    root = SRC_DIR / "phase37"
    files = sorted(p for p in root.rglob("*.py") if p.is_file())
    prohibited_hits: list[dict[str, str]] = []
    calls_seen: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = _mt5_calls(tree)
        calls_seen.update(calls)
        for c in calls:
            if c in PHASE37_PROHIBITED_MT5_API:
                prohibited_hits.append({"file": str(path.relative_to(SRC_DIR.parent)), "api": c})
    unknown = sorted(
        c
        for c in calls_seen
        if c not in PHASE37_PERMITTED_MT5_API
        and c not in PHASE37_PROHIBITED_MT5_API
        and not c.startswith("_")
        and c
        not in {
            # non-API attributes commonly accessed on rates/ticks/info objects
            "dtype",
            "names",
            "time",
            "bid",
            "ask",
            "last",
            "volume",
            "flags",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
            "connected",
            "company",
            "name",
            "path",
            "build",
            "server",
            "trade_mode",
            "trade_allowed",
            "digits",
            "point",
            "trade_tick_size",
            "trade_tick_value",
            "volume_min",
            "volume_max",
            "currency_base",
            "currency_profit",
            "description",
            "path",
            "session_deals",
            "session_buy_orders",
            "session_sell_orders",
        }
    )
    return {
        "files_audited": len(files),
        "prohibited_hits": prohibited_hits,
        "pass": len(prohibited_hits) == 0,
        "calls_seen": sorted(calls_seen),
        "unknown_or_extra_attrs": unknown,
        "permitted": sorted(PHASE37_PERMITTED_MT5_API),
        "prohibited": sorted(PHASE37_PROHIBITED_MT5_API),
        "orders_sent": 0,
        "symbol_select_used": False,
        "note": "Phase37 is observation-only; Market Watch not mutated; no order APIs.",
    }
