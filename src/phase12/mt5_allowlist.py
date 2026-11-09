"""Static MT5 API allowlist. Never imports MetaTrader5."""

from __future__ import annotations

import ast
from pathlib import Path

PERMITTED_MT5_API = frozenset({
    "initialize",
    "shutdown",
    "last_error",
    "terminal_info",
    "account_info",
    "symbol_info",
    "copy_rates_from",
    "copy_rates_from_pos",
    "copy_rates_range",
    "version",
})

PROHIBITED_MT5_API = frozenset({
    "order_send",
    "order_check",
    "order_calc_margin",
    "order_calc_profit",
    "positions_get",
    "positions_total",
    "orders_get",
    "orders_total",
    "history_orders_get",
    "history_deals_get",
    "buy",
    "sell",
    "Close",
    "symbol_select",
})


class Mt5AllowlistError(ValueError):
    pass


def _mt5_calls(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {"mt5", "MetaTrader5"}:
                names.append(node.attr)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in {"mt5", "MetaTrader5"}
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            names.append(node.args[1].value)
    return names


def _module_level_mt5_import(tree: ast.AST) -> tuple[bool, list[str]]:
    imported = False
    from_names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "MetaTrader5":
                    imported = True
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "MetaTrader5":
            imported = True
            from_names.extend(alias.name for alias in node.names)
    return imported, from_names


def audit_source(path: Path, *, raise_on_prohibited: bool = True) -> dict:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    calls = _mt5_calls(tree)
    module_import, from_names = _module_level_mt5_import(tree)
    api = set(calls) | set(from_names)
    prohibited_found = sorted({n for n in api if n in PROHIBITED_MT5_API})
    unknown = sorted({n for n in api if n not in PERMITTED_MT5_API and n not in PROHIBITED_MT5_API})
    permitted_used = sorted({n for n in api if n in PERMITTED_MT5_API})
    if prohibited_found and raise_on_prohibited:
        raise Mt5AllowlistError(f"prohibited MT5 API reachable in {path}: {prohibited_found}")
    if "def connect_readonly" in text:
        prefix = text.split("def connect_readonly", 1)[0]
        import_time_initialize = "initialize(" in prefix
    else:
        import_time_initialize = False
    has_reconnect = any(
        isinstance(node, ast.While)
        and isinstance(getattr(node, "test", None), ast.Constant)
        and node.test.value is True
        for node in ast.walk(tree)
    )
    has_thread = any(
        isinstance(node, ast.Name) and node.id in {"threading", "Thread"}
        for node in ast.walk(tree)
    )
    passed = (
        not prohibited_found
        and not unknown
        and not module_import
        and not import_time_initialize
        and not has_thread
        and not has_reconnect
    )
    return {
        "path": str(path),
        "permitted_used": permitted_used,
        "prohibited_found": prohibited_found,
        "unknown_attrs": unknown,
        "module_level_mt5_import": module_import,
        "import_time_initialize": import_time_initialize,
        "has_thread": has_thread,
        "has_reconnect_loop": has_reconnect,
        "passed": passed,
    }


def audit_phase12_tree(root: Path) -> dict:
    adapter = (root / "mt5_readonly.py").resolve()
    files = sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
    )
    per_file = []
    prohibited_any = []
    api_outside_adapter = []
    for path in files:
        row = audit_source(path, raise_on_prohibited=False)
        row["file"] = str(path.relative_to(root.parent.parent) if root.parent.parent in path.parents else path)
        per_file.append(row)
        prohibited_any.extend(row["prohibited_found"])
        if path.resolve() != adapter and row["permitted_used"]:
            api_outside_adapter.append({"file": row["file"], "api": row["permitted_used"]})
    adapter_row = next(r for r in per_file if Path(r["path"]).resolve() == adapter)
    passed = (
        adapter_row["passed"]
        and not prohibited_any
        and not api_outside_adapter
        and all(not r["module_level_mt5_import"] for r in per_file)
        and all(not r["prohibited_found"] for r in per_file)
    )
    return {
        "passed": passed,
        "adapter": adapter_row,
        "prohibited_any": sorted(set(prohibited_any)),
        "api_outside_adapter": api_outside_adapter,
        "per_file": per_file,
        "allowlist": sorted(PERMITTED_MT5_API),
        "denylist": sorted(PROHIBITED_MT5_API),
    }
