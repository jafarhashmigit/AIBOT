"""Bounded read-only acquisition into Phase51 storage."""

from __future__ import annotations

import json
import time
from typing import Any

from phase40.fetch import fetch_h1_warmup, fetch_m5_day, fetch_ticks_hour
from phase51.constants import H1_WARMUP_BARS, MAX_RETRIES_PER_HOUR, MAX_TICKS_TOTAL, STATE_DIR, SYMBOL, TICK_HOURS
from phase51.storage import h1_done, m5_done, save_h1, save_m5, save_tick_hour, tick_hour_done


def _state_path():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "acquisition_state.json"


def _count_ticks(selected: list[str]) -> int:
    from phase51.constants import RAW_TICKS

    n = 0
    for day in selected:
        for h in TICK_HOURS:
            p = RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"
            if p.is_file():
                n += sum(1 for line in p.open("r", encoding="utf-8") if line.strip())
    return n


def load_state(selected: list[str]) -> dict[str, Any]:
    completed, pending = {}, []
    for day in selected:
        if m5_done(day) and h1_done(day) and all(tick_hour_done(day, h) for h in TICK_HOURS):
            completed[day] = True
        else:
            pending.append(day)
    prev = json.loads(_state_path().read_text(encoding="utf-8")) if _state_path().is_file() else {}
    return {"completed": completed, "pending": pending, "ticks_total": int(prev.get("ticks_total") or 0)}


def save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def acquire_dates(handle: Any, selected: list[str], *, server, terminal_build, wall_deadline: float) -> dict[str, Any]:
    state = load_state(selected)
    if state["ticks_total"] == 0:
        state["ticks_total"] = _count_ticks(selected)
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
            if m5.get("ok"):
                saved = save_m5(day, m5["bars"], {**m5, "server": server})
                day_rec["m5"] = {"status": "saved", "n": saved["n"]}
            else:
                day_rec["m5"] = {"status": "failed", "error": m5.get("error")}
        if h1_done(day):
            day_rec["h1"] = {"status": "reused"}
        else:
            h1 = fetch_h1_warmup(handle, SYMBOL, day, warmup_bars=H1_WARMUP_BARS, wall_deadline=wall_deadline)
            if h1.get("ok"):
                saved = save_h1(day, h1.get("bars") or [], {**h1, "server": server})
                day_rec["h1"] = {"status": "saved", "n": saved["n"]}
            else:
                day_rec["h1"] = {"status": "failed", "error": h1.get("error")}
        for hour in TICK_HOURS:
            if time.monotonic() > wall_deadline:
                stop_reason = "max_wall_seconds"
                break
            if state["ticks_total"] >= MAX_TICKS_TOTAL:
                stop_reason = "max_ticks_total"
                break
            if tick_hour_done(day, hour):
                day_rec["ticks"][f"{hour:02d}"] = {"status": "reused"}
                continue
            ok = False
            last_err = None
            for _attempt in range(1, MAX_RETRIES_PER_HOUR + 1):
                tk = fetch_ticks_hour(handle, SYMBOL, day, hour, wall_deadline=wall_deadline)
                if not tk.get("ok"):
                    last_err = tk.get("error")
                    continue
                accepted = [t for t in tk["ticks"] if t.get("bid") is not None and t.get("ask") is not None and float(t["ask"]) >= float(t["bid"])]
                saved = save_tick_hour(day, hour, accepted, {**tk, "server": server})
                state["ticks_total"] += saved["n"]
                day_rec["ticks"][f"{hour:02d}"] = {"status": "saved", "n": saved["n"], "empty": saved["empty_hour"]}
                ok = True
                break
            if not ok:
                day_rec["ticks"][f"{hour:02d}"] = {"status": "failed", "error": last_err}
        results.append(day_rec)
        state = load_state(selected)
        state["ticks_total"] = _count_ticks(selected)
        save_state(state)
        if stop_reason:
            break
    state = load_state(selected)
    state["ticks_total"] = _count_ticks(selected)
    save_state(state)
    return {
        "results": results,
        "completed_dates": sorted(state["completed"].keys()),
        "pending_dates": state["pending"],
        "ticks_total": state["ticks_total"],
        "stop_reason": stop_reason,
    }
