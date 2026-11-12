"""Discover all archived XAUUSD M5/H1/tick days without mutating sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase54.archive_loader import sealed_forbidden
from phase54.constants import SYMBOL
from phase59.constants import ARCHIVE_ROOTS, PHASE58_SPLITS, canonical_json_sha256


def _days_in_m5(root: Path) -> list[str]:
    m5 = root / "m5"
    if not m5.is_dir():
        return []
    days = []
    for p in sorted(m5.glob(f"m5_{SYMBOL}_*.jsonl")):
        day = p.stem.replace(f"m5_{SYMBOL}_", "")
        days.append(day)
    return days


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    obj = json.loads(PHASE58_SPLITS.read_text(encoding="utf-8"))
    return list(obj.get("holdout_sealed") or [])


def build_inventory() -> dict[str, Any]:
    by_source: dict[str, list[str]] = {}
    union: set[str] = set()
    for name, root in ARCHIVE_ROOTS:
        days = _days_in_m5(root) if root.is_dir() else []
        by_source[name] = days
        union |= set(days)
    sealed = sorted(sealed_forbidden())
    holdout = phase58_holdout()
    all_days = sorted(union)
    inv = {
        "symbol": SYMBOL,
        "sources": {k: {"n_days": len(v), "days": v, "root": str(dict(ARCHIVE_ROOTS)[k])} for k, v in by_source.items()},
        "union_n_days": len(all_days),
        "union_days": all_days,
        "date_min": all_days[0] if all_days else None,
        "date_max": all_days[-1] if all_days else None,
        "sealed_forbidden_n": len(sealed),
        "sealed_forbidden": sealed,
        "phase58_holdout_sealed": holdout,
        "phase58_holdout_in_union": [d for d in holdout if d in union],
        "note": "list_archived_m5_days excludes sealed; Phase59 inventory includes all files for integrity/coverage.",
    }
    inv["inventory_sha256"] = canonical_json_sha256({k: v for k, v in inv.items() if k != "inventory_sha256"})
    return inv


def resolve_root_for_day(day: str) -> Path | None:
    # Prefer later-phase archives when duplicates exist
    for name, root in reversed(ARCHIVE_ROOTS):
        p = root / "m5" / f"m5_{SYMBOL}_{day}.jsonl"
        if p.is_file():
            return root
    return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
