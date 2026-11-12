"""Lean fill: download only missing hours for priority days; no full-corpus rebuild mid-pass."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from phase34.acquisition import DST_PRIORITY_DAYS, acquire_hour, rebuild_corpus_from_disk
from phase34.constants import (
    DOWNLOAD_HOURS_UTC,
    MAX_NETWORK_HOURS,
    MAX_WALL_SECONDS,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
    REPORTS_DIR,
    select_trading_days,
)
from phase34.progress import save_progress

UTC = timezone.utc

PRIORITY = list(DST_PRIORITY_DAYS) + ["2026-02-16", "2026-02-26", "2026-09-28"]


def missing_hours(day: str) -> list[int]:
    day_dir = RAW_DIR / day
    day_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for hour in DOWNLOAD_HOURS_UTC:
        if f"{day} {hour:02d}:00:00" > RESEARCH_CUTOFF_UTC:
            continue
        if (day_dir / f"{hour:02d}h_ticks.bi5").is_file():
            continue
        if (day_dir / f"{hour:02d}h_ticks.empty").is_file():
            continue
        out.append(hour)
    return out


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    save_progress(
        {
            "phase": 34,
            "current_stage": "lean_fill",
            "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed_stages": [],
        }
    )
    network_used = 0
    log = {"days": {}, "network_ok": 0, "network_fail": 0, "stopped": False, "reason": None}

    for day in PRIORITY:
        elapsed = (datetime.now(UTC) - start).total_seconds()
        if elapsed > MAX_WALL_SECONDS:
            log["stopped"] = True
            log["reason"] = "max_wall_seconds"
            break
        need = missing_hours(day)
        print(f"DAY {day} missing={need}", flush=True)
        day_dir = RAW_DIR / day
        day_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for hour in need:
            if network_used >= MAX_NETWORK_HOURS:
                log["stopped"] = True
                log["reason"] = "max_network_hours"
                break
            if (datetime.now(UTC) - start).total_seconds() > MAX_WALL_SECONDS:
                log["stopped"] = True
                log["reason"] = "max_wall_seconds"
                break
            meta, _ticks = acquire_hour(day, hour, day_dir, allow_network=True)
            network_used += 1 if meta.get("network_used") else 0
            ok = bool(meta.get("ok"))
            if ok:
                log["network_ok"] += 1
            else:
                log["network_fail"] += 1
            results.append(
                {
                    "hour": hour,
                    "ok": ok,
                    "empty": meta.get("empty"),
                    "error": meta.get("error"),
                    "source": meta.get("source"),
                    "bytes": meta.get("bytes"),
                }
            )
            print(
                f"  hour={hour:02d} ok={ok} empty={meta.get('empty')} src={meta.get('source')} err={meta.get('error')}",
                flush=True,
            )
            time.sleep(0.1)
        log["days"][day] = {
            "missing_before": need,
            "still_missing": missing_hours(day),
            "results": results,
        }
        if log["stopped"]:
            break

    log["ended_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    log["duration_seconds"] = (datetime.now(UTC) - start).total_seconds()
    (REPORTS_DIR / "lean_fill_log.json").write_text(
        json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("LEAN_FILL_DONE", json.dumps({k: log[k] for k in ("network_ok", "network_fail", "stopped", "reason", "duration_seconds")}), flush=True)

    rebuilt = rebuild_corpus_from_disk(days=select_trading_days())
    m = rebuilt["manifest"]
    print(
        "REBUILD",
        {
            "complete": m.get("n_complete_trading_days"),
            "complete_days": m.get("complete_trading_days"),
            "ticks": m["totals"]["ticks"],
            "incomplete": m.get("incomplete_trading_days"),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
