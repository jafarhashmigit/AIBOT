"""Bounded resumable acquisition of UNSEEN dates only."""

from __future__ import annotations

import json
import time
from typing import Any

from phase40.fetch import fetch_h1_warmup, fetch_m5_day, fetch_ticks_hour
from phase43.constants import (
    H1_WARMUP_BARS,
    MAX_RETRIES_PER_HOUR,
    MAX_TICKS_TOTAL,
    STATE_DIR,
    SYMBOL,
    TICK_HOURS,
)
from phase43.storage import h1_done, m5_done, save_h1, save_m5, save_tick_hour, tick_hour_done


def _state_path():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "acquisition_state.json"


def load_state(selected: list[str]) -> dict[str, Any]:
    completed = {}
    pending = []
    for day in selected:
        hours_ok = all(tick_hour_done(day, h) for h in TICK_HOURS)
        if m5_done(day) and h1_done(day) and hours_ok:
            completed[day] = True
        else:
            pending.append(day)
    prev = {}
    p = _state_path()
    if p.is_file():
        prev = json.loads(p.read_text(encoding="utf-8"))
    return {
        "completed": completed,
        "pending": pending,
        "ticks_total": int(prev.get("ticks_total") or 0),
        "last_stop_reason": prev.get("last_stop_reason"),
    }


def save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _count_existing_ticks(selected: list[str]) -> int:
    from phase43.constants import RAW_TICKS
    from phase43.storage import load_jsonl

    n = 0
    for day in selected:
        for h in TICK_HOURS:
            path = RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"
            if path.is_file():
                # cheap: count lines
                n += sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
    return n


def acquire_dates(
    handle: Any,
    selected: list[str],
    *,
    server: str | None,
    terminal_build: Any,
    wall_deadline: float,
) -> dict[str, Any]:
    state = load_state(selected)
    if state["ticks_total"] == 0:
        state["ticks_total"] = _count_existing_ticks(selected)
    results = []
    stop_reason = None

    for day in list(state["pending"]):
        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            break
        if state["ticks_total"] >= MAX_TICKS_TOTAL:
            stop_reason = "max_ticks_total"
            break

        day_rec: dict[str, Any] = {"day": day, "m5": None, "h1": None, "ticks": {}}

        if m5_done(day):
            day_rec["m5"] = {"status": "reused"}
        else:
            m5 = fetch_m5_day(handle, SYMBOL, day, wall_deadline=wall_deadline)
            if not m5.get("ok"):
                day_rec["m5"] = {"status": "failed", "error": m5.get("error")}
            else:
                saved = save_m5(
                    day,
                    m5["bars"],
                    {**m5, "server": server, "terminal_build": terminal_build, "validation_status": "saved"},
                )
                day_rec["m5"] = {"status": "saved", "n": saved["n"], "sha256": saved["sha256"]}

        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            results.append(day_rec)
            break

        if h1_done(day):
            day_rec["h1"] = {"status": "reused"}
        else:
            h1 = fetch_h1_warmup(handle, SYMBOL, day, warmup_bars=H1_WARMUP_BARS, wall_deadline=wall_deadline)
            if not h1.get("ok"):
                day_rec["h1"] = {"status": "failed", "error": h1.get("error")}
            else:
                # store full returned bars (includes warmup + day) like phase40
                bars = h1.get("bars") or []
                saved = save_h1(
                    day,
                    bars,
                    {
                        **h1,
                        "server": server,
                        "terminal_build": terminal_build,
                        "validation_status": "warmup_ok" if h1.get("warmup_sufficient") else "warmup_partial",
                    },
                )
                day_rec["h1"] = {
                    "status": "saved",
                    "n": saved["n"],
                    "warmup_sufficient": h1.get("warmup_sufficient"),
                    "n_warmup_available": h1.get("n_warmup_available"),
                    "sha256": saved["sha256"],
                }

        hour_stats = {"ok": 0, "empty": 0, "failed": 0, "reused": 0}
        for hour in TICK_HOURS:
            if time.monotonic() > wall_deadline:
                stop_reason = "max_wall_seconds"
                break
            if state["ticks_total"] >= MAX_TICKS_TOTAL:
                stop_reason = "max_ticks_total"
                break
            if tick_hour_done(day, hour):
                hour_stats["reused"] += 1
                day_rec["ticks"][f"{hour:02d}"] = {"status": "reused"}
                continue
            ok = False
            last_err = None
            for attempt in range(1, MAX_RETRIES_PER_HOUR + 1):
                tk = fetch_ticks_hour(handle, SYMBOL, day, hour, wall_deadline=wall_deadline)
                if not tk.get("ok"):
                    last_err = tk.get("error")
                    continue
                # reject crossed ticks only; keep empty hours
                accepted = []
                for t in tk["ticks"]:
                    if t.get("bid") is None or t.get("ask") is None:
                        continue
                    if float(t["ask"]) < float(t["bid"]):
                        continue
                    accepted.append(t)
                saved = save_tick_hour(
                    day,
                    hour,
                    accepted,
                    {
                        **tk,
                        "server": server,
                        "terminal_build": terminal_build,
                        "validation_status": "pass",
                        "bid_ask_ok": tk.get("bid_ask_ok"),
                    },
                )
                state["ticks_total"] += saved["n"]
                if saved["empty"]:
                    hour_stats["empty"] += 1
                else:
                    hour_stats["ok"] += 1
                day_rec["ticks"][f"{hour:02d}"] = {
                    "status": "saved",
                    "n": saved["n"],
                    "empty": saved["empty"],
                    "attempt": attempt,
                }
                ok = True
                break
            if not ok:
                hour_stats["failed"] += 1
                day_rec["ticks"][f"{hour:02d}"] = {"status": "failed", "error": last_err}

        day_rec["tick_hour_stats"] = hour_stats
        results.append(day_rec)
        state = load_state(selected)
        state["ticks_total"] = state.get("ticks_total") or 0
        # preserve tick counter from this run
        # reload loses ticks_total — restore
        ticks_total = sum(
            (day_rec["ticks"].get(f"{h:02d}", {}) or {}).get("n", 0)
            for h in TICK_HOURS
            if (day_rec["ticks"].get(f"{h:02d}", {}) or {}).get("status") == "saved"
        )
        # recompute from disk for accuracy
        state["ticks_total"] = _count_existing_ticks(selected)
        state["last_stop_reason"] = stop_reason
        save_state(state)
        if stop_reason:
            break

    state = load_state(selected)
    state["ticks_total"] = _count_existing_ticks(selected)
    state["last_stop_reason"] = stop_reason
    save_state(state)
    return {
        "results": results,
        "completed_dates": sorted(state["completed"].keys()),
        "pending_dates": state["pending"],
        "ticks_total": state["ticks_total"],
        "stop_reason": stop_reason,
        "limits": {"max_dates": len(selected), "max_ticks": MAX_TICKS_TOTAL},
    }
