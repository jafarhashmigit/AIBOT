"""Bounded deterministic historical replay — no auto-start, no live MT5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.archive_loader import list_archived_m5_days, load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase54.constants import DEFAULT_MAX_CANDLES, DEFAULT_REPLAY_ARCHIVE, EVENT_STRIDE, HORIZON_BARS
from phase54.lifecycle import LifecycleEngine
from phase54.research import dataset_provenance
from phase54.timeutil import now_utc_iso


def run_replay(
    *,
    archive_root: Path | None = None,
    days: list[str] | None = None,
    max_candles: int = DEFAULT_MAX_CANDLES,
    max_decisions: int | None = None,
    engine: LifecycleEngine | None = None,
    stride: int = EVENT_STRIDE,
) -> dict[str, Any]:
    root = Path(archive_root or DEFAULT_REPLAY_ARCHIVE)
    day_list = list(days) if days is not None else list_archived_m5_days(root)
    engine = engine or LifecycleEngine()
    provenance = dataset_provenance(str(root), day_list)

    candles = 0
    decisions = 0
    results = []
    stopped = None

    for day in day_list:
        m5 = load_m5(root, day)
        h1 = load_h1(root, day)
        by_bar = ticks_by_m5_bar(load_ticks(root, day))
        first = 48
        last = len(m5) - (1 + HORIZON_BARS)
        if last < first:
            continue
        idx = first
        while idx <= last:
            if candles >= max_candles:
                stopped = "max_candles"
                break
            if max_decisions is not None and decisions >= max_decisions:
                stopped = "max_decisions"
                break
            candles += 1
            if engine.state.already_processed(day, idx):
                idx += stride
                continue
            rec = engine.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by_bar, idx=idx)
            if not rec.get("skipped"):
                decisions += 1
                results.append(
                    {
                        "day": day,
                        "idx": idx,
                        "action": (rec.get("decision") or {}).get("action"),
                        "rejected": rec.get("rejected"),
                    }
                )
            idx += stride
        if stopped:
            break

    return {
        "archive_root": str(root),
        "days": day_list,
        "n_days": len(day_list),
        "candles_seen": candles,
        "decisions_attempted": decisions,
        "stop_reason": stopped,
        "sample_results": results[:20],
        "n_results": len(results),
        "provenance_sha256": provenance.get("provenance_sha256"),
        "completed_iso": now_utc_iso(),
        "deterministic": True,
        "live_mt5": False,
        "auto_started": False,
    }
