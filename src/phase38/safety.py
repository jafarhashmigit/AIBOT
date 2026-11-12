"""AST safety audit — no order APIs in Phase38."""

from __future__ import annotations

import ast
from typing import Any

from phase38.constants import PHASE38_PROHIBITED_MT5_API, SRC_DIR


def audit_phase38() -> dict[str, Any]:
    root = SRC_DIR / "phase38"
    hits = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in {"mt5", "MetaTrader5", "handle"} and node.attr in PHASE38_PROHIBITED_MT5_API:
                    hits.append({"file": str(path), "api": node.attr})
    return {
        "pass": len(hits) == 0,
        "prohibited_hits": hits,
        "orders_sent": 0,
        "note": "historical read-only; no live trading",
    }
