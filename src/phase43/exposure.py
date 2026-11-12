"""Prior-exposure audit across Phases 0–42. No outcome inspection for selection."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from phase43.constants import (
    COVERAGE_PROBE_DATES,
    KNOWN_EVAL_OR_TARGET_DATES,
    PHASE37_M5_RANGES,
    PHASE40_PLAN_ONLY,
    PROJECT_ROOT,
    SRC_DIR,
    WINDOW_END,
    WINDOW_START,
)
from phase43.progress import write_json


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _daterange(a: date, b: date):
    cur = a
    while cur <= b:
        yield cur
        cur += timedelta(days=1)


def _in_ranges(day: str) -> list[str]:
    hits = []
    d = _d(day)
    for a, b in PHASE37_M5_RANGES:
        if _d(a) <= d <= _d(b):
            hits.append(f"phase37_m5_range:{a}:{b}")
    return hits


def _data_file_dates() -> dict[str, list[str]]:
    """Dates present as M5/H1/tick data filenames under src/data."""
    out: dict[str, list[str]] = {}
    root = SRC_DIR / "data"
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if not any(k in name for k in ("m5_", "h1_", "ticks_")):
            continue
        # extract YYYY-MM-DD
        for i in range(len(name) - 9):
            frag = name[i : i + 10]
            if frag[4] == "-" and frag[7] == "-" and frag[:4].isdigit() and frag[5:7].isdigit() and frag[8:10].isdigit():
                day = frag
                kind = "m5" if "m5_" in name else ("h1" if "h1_" in name else "ticks")
                # phase folder
                parts = p.as_posix()
                phase = "unknown"
                for ph in range(34, 43):
                    if f"phase{ph}" in parts:
                        phase = f"phase{ph}"
                        break
                out.setdefault(day, []).append(f"{phase}:{kind}:{p.name}")
                break
    return out


def _h1_warmup_neighbors() -> set[str]:
    """Calendar days likely used as H1 warm-up context for known eval dates (~4 days prior)."""
    neigh: set[str] = set()
    for day in KNOWN_EVAL_OR_TARGET_DATES:
        d0 = _d(day)
        for i in range(1, 6):
            neigh.add((d0 - timedelta(days=i)).isoformat())
    return neigh


def classify_day(day: str, data_hits: dict[str, list[str]], h1_neighbors: set[str]) -> dict[str, Any]:
    m5 = h1 = ticks = labels = strategy = False
    sources: list[str] = []
    exposure = "UNSEEN"

    if day in KNOWN_EVAL_OR_TARGET_DATES:
        m5 = h1 = ticks = labels = strategy = True
        sources.append("known_eval_or_target")
        exposure = "PREVIOUSLY_EXPOSED"
    if day in COVERAGE_PROBE_DATES:
        m5 = True
        sources.append("phase38_coverage_probe")
        if exposure == "UNSEEN":
            exposure = "PREVIOUSLY_EXPOSED"
    ranges = _in_ranges(day)
    if ranges:
        m5 = True
        sources.extend(ranges)
        exposure = "PREVIOUSLY_EXPOSED"
    if day in data_hits:
        for hit in data_hits[day]:
            sources.append(hit)
            if ":m5:" in hit:
                m5 = True
            if ":h1:" in hit:
                h1 = True
            if ":ticks:" in hit:
                ticks = True
        exposure = "PREVIOUSLY_EXPOSED"
    if day in PHASE40_PLAN_ONLY and exposure == "UNSEEN":
        sources.append("phase40_plan_only_not_downloaded")
        # Named in a plan without archived data → still not independent-claim-only;
        # classify PARTIALLY_EXPOSED for caution (selection bias risk if later used as "held out")
        exposure = "PARTIALLY_EXPOSED"
    if day in h1_neighbors and exposure == "UNSEEN":
        h1 = True
        sources.append("h1_warmup_neighbor_of_eval_date")
        exposure = "PARTIALLY_EXPOSED"

    # Labels/strategy: if previously exposed eval date
    if exposure == "PREVIOUSLY_EXPOSED" and day in KNOWN_EVAL_OR_TARGET_DATES:
        labels = True
        strategy = True

    independent_eligible = exposure == "UNSEEN"
    return {
        "date": day,
        "m5_exposure": m5,
        "h1_m15_exposure": h1,
        "tick_exposure": ticks,
        "label_outcome_exposure": labels,
        "strategy_evaluation_exposure": strategy,
        "source_phases": sorted(set(sources)),
        "exposure_class": exposure,
        "independent_validation_eligibility": independent_eligible,
    }


def build_exposure_registry() -> dict[str, Any]:
    data_hits = _data_file_dates()
    h1_neighbors = _h1_warmup_neighbors()
    rows = []
    # Full calendar for window + known outside dates that matter
    for d in _daterange(WINDOW_START - timedelta(days=7), WINDOW_END + timedelta(days=7)):
        if d.weekday() >= 5:
            continue
        rows.append(classify_day(d.isoformat(), data_hits, h1_neighbors))

    # Also ensure all known eval dates appear even if weekend (shouldn't)
    for day in sorted(KNOWN_EVAL_OR_TARGET_DATES | COVERAGE_PROBE_DATES):
        if not any(r["date"] == day for r in rows):
            rows.append(classify_day(day, data_hits, h1_neighbors))

    rows.sort(key=lambda r: r["date"])
    in_window = [r for r in rows if WINDOW_START.isoformat() <= r["date"] <= WINDOW_END.isoformat()]
    summary = {
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "n_weekdays_in_window": len(in_window),
        "n_unseen": sum(1 for r in in_window if r["exposure_class"] == "UNSEEN"),
        "n_partially_exposed": sum(1 for r in in_window if r["exposure_class"] == "PARTIALLY_EXPOSED"),
        "n_previously_exposed": sum(1 for r in in_window if r["exposure_class"] == "PREVIOUSLY_EXPOSED"),
        "n_unknown": sum(1 for r in in_window if r["exposure_class"] == "UNKNOWN_EXPOSURE"),
        "policy": (
            "UNSEEN only for independent validation. "
            "PARTIALLY_EXPOSED exploratory only. "
            "PREVIOUSLY_EXPOSED prohibited as independent validation. "
            "Tick-new alone does not create independence."
        ),
    }
    payload = {"summary": summary, "rows": rows, "in_window_rows": in_window}
    write_json("prior_exposure_registry.json", payload)
    return payload


def select_unseen_dates(exposure: dict[str, Any], k: int = 30) -> dict[str, Any]:
    """Deterministic evenly spaced selection among UNSEEN weekdays — no outcome peeking."""
    pool = [
        r["date"]
        for r in exposure.get("in_window_rows") or []
        if r["exposure_class"] == "UNSEEN" and r["independent_validation_eligibility"]
    ]
    pool = sorted(set(pool))
    if k >= len(pool):
        selected = pool
    elif k <= 1:
        selected = pool[:1]
    else:
        selected = []
        for i in range(k):
            idx = int(round(i * (len(pool) - 1) / (k - 1)))
            day = pool[idx]
            if day not in selected:
                selected.append(day)
        for day in pool:
            if len(selected) >= k:
                break
            if day not in selected:
                selected.append(day)
        selected = sorted(selected)[:k]

    report = {
        "algorithm": (
            "Evenly spaced Mon–Fri UNSEEN dates in [2025-07-02, 2026-02-15] via "
            "round(i*(n-1)/(k-1)); no performance/volatility/outcome-based selection."
        ),
        "pool_n": len(pool),
        "requested_k": k,
        "selected_n": len(selected),
        "selected_dates": selected,
        "selection_locked_before_acquisition": True,
        "months_represented": sorted({d[:7] for d in selected}),
    }
    write_json("date_selection.json", report)
    return report
