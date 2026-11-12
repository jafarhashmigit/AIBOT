"""Lean fill: only retry missing hours on selected Phase36 days (resume-safe)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from phase36.acquisition import acquire_hour, rebuild_corpus_from_disk
from phase36.constants import (
    EXCLUDED_EVAL_DAYS,
    MAX_CONSECUTIVE_NETWORK_FAILURES,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
)
from phase36.date_selection import select_independent_dates
from phase36.progress import write_json

UTC = timezone.utc
HOURS = list(range(24))


def missing_hours(day: str) -> list[int]:
    day_dir = RAW_DIR / day
    out: list[int] = []
    for hour in HOURS:
        if f"{day} {hour:02d}:00:00" > RESEARCH_CUTOFF_UTC:
            continue
        if (day_dir / f"{hour:02d}h_ticks.bi5").is_file() or (
            day_dir / f"{hour:02d}h_ticks.empty"
        ).is_file():
            continue
        out.append(hour)
    return out


def coverage(day: str) -> int:
    return 24 - len(missing_hours(day))


def main() -> None:
    dates = select_independent_dates()["selected_dates"]
    ranked = sorted(
        [d for d in dates if d not in EXCLUDED_EVAL_DAYS],
        key=lambda d: (-coverage(d), len(missing_hours(d)), d),
    )
    print("coverage_before:")
    for d in ranked:
        miss = missing_hours(d)
        print(f"  {d}: have={24 - len(miss)} missing={miss}")

    # Near-complete first; wall ~25 min for gap fill only.
    wall_s = 1500
    started = datetime.now(UTC)
    consec = 0
    filled = 0
    failed = 0
    stop_reason = None

    # Pass 1: days with <=4 missing hours
    # Pass 2: remaining gaps if budget left
    for pass_max_missing in (4, 24):
        for day in ranked:
            miss = missing_hours(day)
            if not miss or len(miss) > pass_max_missing:
                continue
            if (datetime.now(UTC) - started).total_seconds() > wall_s:
                stop_reason = "max_wall_seconds"
                break
            if consec >= MAX_CONSECUTIVE_NETWORK_FAILURES:
                stop_reason = "consecutive_network_failures"
                break

            day_dir = RAW_DIR / day
            day_dir.mkdir(parents=True, exist_ok=True)
            for hour in miss:
                if (datetime.now(UTC) - started).total_seconds() > wall_s:
                    stop_reason = "max_wall_seconds"
                    break
                if consec >= MAX_CONSECUTIVE_NETWORK_FAILURES:
                    stop_reason = "consecutive_network_failures"
                    break
                meta, _ = acquire_hour(day, hour, day_dir, allow_network=True)
                if meta.get("ok"):
                    consec = 0
                    filled += 1
                    print(f"OK {day} h{hour:02d} src={meta.get('source')} ticks={meta.get('tick_count')}")
                else:
                    consec += 1
                    failed += 1
                    print(f"FAIL {day} h{hour:02d} err={meta.get('error')} consec={consec}")
                    time.sleep(1.5)
            if stop_reason:
                break
        if stop_reason:
            break

    print(
        f"fill_done filled={filled} failed={failed} "
        f"elapsed={(datetime.now(UTC) - started).total_seconds():.1f}s stop={stop_reason}"
    )
    print("coverage_after:")
    for d in ranked:
        miss = missing_hours(d)
        print(f"  {d}: have={24 - len(miss)} missing={miss}")

    # Classify complete days from disk only (no more network burn).
    acq = rebuild_corpus_from_disk(dates, allow_network=False)
    m = acq["manifest"]
    summary = {
        "n_complete": m.get("n_complete_trading_days"),
        "complete": m.get("complete_trading_days"),
        "incomplete": m.get("incomplete_trading_days"),
        "stop_reason": stop_reason or m.get("stop_reason"),
        "totals": m.get("totals"),
        "fill_filled": filled,
        "fill_failed": failed,
    }
    write_json("fill_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
