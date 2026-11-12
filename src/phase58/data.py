"""Leakage-safe multi-archive loader and chronological splits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase54.archive_loader import list_archived_m5_days, sealed_forbidden
from phase54.archive_loader import ticks_by_m5_bar as ticks_by_m5_bar  # re-export
from phase54.constants import SYMBOL
from phase58.constants import ARCHIVE_ROOTS, N_DISCOVERY, N_HOLDOUT, N_VALIDATION, canonical_json_sha256


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def resolve_root(day: str) -> Path:
    for root in ARCHIVE_ROOTS:
        p = root / "m5"
        if p.is_dir() and any(p.glob(f"m5_*_{day}.jsonl")):
            return root
    raise FileNotFoundError(day)


def list_all_days() -> list[str]:
    days: set[str] = set()
    for root in ARCHIVE_ROOTS:
        if (root / "m5").is_dir():
            days |= set(list_archived_m5_days(root))
    return sorted(days)


def eligible_days() -> list[str]:
    forbid = sealed_forbidden()
    return [d for d in list_all_days() if d not in forbid]


def load_m5_raw(day: str, *, allow_sealed_context: bool = False) -> list[dict[str, Any]]:
    """Load M5. Scoring days must not be sealed; prior-session context may load sealed archives."""
    if not allow_sealed_context and day in sealed_forbidden():
        raise RuntimeError(f"sealed_date_forbidden_for_scoring:{day}")
    root = resolve_root(day)
    rows = _load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_h1(day: str) -> list[dict[str, Any]]:
    if day in sealed_forbidden():
        raise RuntimeError(f"sealed_date_forbidden_for_scoring:{day}")
    root = resolve_root(day)
    rows = _load_jsonl(root / "h1" / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_ticks(day: str) -> list[dict[str, Any]]:
    if day in sealed_forbidden():
        raise RuntimeError(f"sealed_date_forbidden_for_scoring:{day}")
    root = resolve_root(day)
    ticks: list[dict[str, Any]] = []
    for h in range(24):
        ticks.extend(_load_jsonl(root / "ticks" / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"))
    ticks.sort(key=lambda t: int(t["timestamp_msc"]))
    return ticks


def chronological_splits(days: list[str] | None = None) -> dict[str, Any]:
    days = sorted(days or eligible_days())
    n = len(days)
    if n < N_DISCOVERY + 2:
        n_disc = max(2, int(0.5 * n))
        n_val = max(1, int(0.25 * n))
        n_hold = max(0, n - n_disc - n_val)
    else:
        n_disc, n_val = N_DISCOVERY, N_VALIDATION
        n_hold = min(N_HOLDOUT, n - n_disc - n_val)
        if n_hold < 0:
            n_hold = 0
    discovery = days[:n_disc]
    validation = days[n_disc : n_disc + n_val]
    holdout = days[n_disc + n_val : n_disc + n_val + n_hold]
    split = {
        "algorithm": "chronological eligible archive union; Phase44/49 sealed dates excluded from scoring",
        "n_total_eligible": n,
        "discovery": discovery,
        "validation": validation,
        "holdout_sealed": holdout,
        "forbidden_sealed_not_used": sorted(sealed_forbidden()),
    }
    split["split_sha256"] = canonical_json_sha256({k: v for k, v in split.items() if k != "split_sha256"})
    return split


def previous_archived_day(day: str, all_days: list[str] | None = None) -> str | None:
    days = sorted(all_days or list_all_days())
    if day not in days:
        # still find latest day strictly before
        before = [d for d in days if d < day]
        return before[-1] if before else None
    i = days.index(day)
    return days[i - 1] if i > 0 else None


__all__ = [
    "chronological_splits",
    "eligible_days",
    "list_all_days",
    "load_h1",
    "load_m5_raw",
    "load_ticks",
    "previous_archived_day",
    "resolve_root",
    "ticks_by_m5_bar",
]
