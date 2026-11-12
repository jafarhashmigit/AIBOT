"""Load Phase 34 tick corpus (read-only). No new downloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase35.constants import (
    PHASE34_IMMUTABLE_REPORTS,
    PHASE34_RAW,
    PHASE34_REPORTS,
    PHASE34_TICKS,
    PROJECT_ROOT,
    file_sha256,
)


def phase34_immutability() -> dict[str, Any]:
    hashes = {}
    ok = True
    for rel in PHASE34_IMMUTABLE_REPORTS:
        path = PROJECT_ROOT / rel
        if not path.is_file():
            hashes[rel] = None
            ok = False
            continue
        hashes[rel] = file_sha256(path)
    return {"immutable_policy": True, "phase34_reports_hashed": hashes, "ok": ok}


def load_phase34_manifest() -> dict[str, Any]:
    path = PHASE34_REPORTS / "acquisition_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def complete_trading_days(manifest: dict[str, Any] | None = None) -> list[str]:
    m = manifest or load_phase34_manifest()
    return list(m.get("complete_trading_days") or [])


def load_ticks_for_days(days: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load decoded ticks for listed days from Phase 34 jsonl (preferred)."""
    ticks: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for day in days:
        path = PHASE34_TICKS / f"{day}.jsonl"
        if not path.is_file():
            sources.append({"day": day, "status": "MISSING_JSONL"})
            continue
        sha = file_sha256(path)
        n = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ticks.append(json.loads(line))
                n += 1
        sources.append(
            {
                "day": day,
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": sha,
                "n_ticks": n,
                "status": "LOADED",
            }
        )
    ticks.sort(key=lambda t: int(t["epoch_ms"]))
    return ticks, sources


def dataset_inventory() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_phase34_manifest()
    days = complete_trading_days(manifest)
    ticks, sources = load_ticks_for_days(days)
    spreads = [float(t["ask"]) - float(t["bid"]) for t in ticks]
    spreads_sorted = sorted(spreads)

    def pct(p: float) -> float:
        if not spreads_sorted:
            return float("nan")
        k = (len(spreads_sorted) - 1) * (p / 100.0)
        import math

        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return spreads_sorted[int(k)]
        return spreads_sorted[f] * (c - k) + spreads_sorted[c] * (k - f)

    return {
        "phase34_verdict_path": "reports/phase34/final_verdict.json",
        "complete_trading_days": days,
        "n_complete_days": len(days),
        "n_ticks_loaded": len(ticks),
        "sources": sources,
        "raw_dir_exists": PHASE34_RAW.is_dir(),
        "recomputed_spread_usd": {
            "n": len(spreads),
            "median": pct(50) if spreads else None,
            "mean": (sum(spreads) / len(spreads)) if spreads else None,
            "p95": pct(95) if spreads else None,
        },
        "immutability": phase34_immutability(),
        "mt5_used": False,
        "live_data_used": False,
        "new_download": False,
    }, ticks
