"""Resumable one-date-at-a-time acquisition within wall budget."""

from __future__ import annotations

import json
import time
from typing import Any

from phase40.constants import (
    H1_WARMUP_BARS,
    STATE_DIR,
    SYMBOL,
    TARGET_DATES,
    TICK_HOURS,
)
from phase40.fetch import fetch_h1_warmup, fetch_m5_day, fetch_ticks_hour
from phase40.storage import h1_done, m5_done, save_h1, save_m5, save_tick_hour, tick_hour_done
from phase40.validation import classify_session, validate_m5, validate_ticks


def _state_path():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "acquisition_state.json"


def load_state() -> dict[str, Any]:
    completed = {}
    pending = []
    for day in TARGET_DATES:
        hours_ok = all(tick_hour_done(day, h) for h in TICK_HOURS)
        if m5_done(day) and h1_done(day) and hours_ok:
            completed[day] = {"m5": True, "h1": True, "ticks_24h": True}
        else:
            pending.append(day)
    p = _state_path()
    prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    return {
        "completed": completed,
        "pending": pending,
        "last_stop_reason": prev.get("last_stop_reason"),
        "reconciled_from_disk": True,
    }


def save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def acquire_all(handle: Any, *, server: str | None, terminal_build: Any, wall_deadline: float) -> dict[str, Any]:
    state = load_state()
    results = []
    stop_reason = None
    consec_fail = 0

    for day in list(state["pending"]):
        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            break
        day_rec: dict[str, Any] = {"day": day, "m5": None, "h1": None, "ticks": {}}

        # M5
        if m5_done(day):
            day_rec["m5"] = {"status": "reused"}
        else:
            m5 = fetch_m5_day(handle, SYMBOL, day, wall_deadline=wall_deadline)
            if not m5.get("ok"):
                day_rec["m5"] = {"status": "failed", "error": m5.get("error")}
                consec_fail += 1
            else:
                v = validate_m5(m5["bars"])
                saved = save_m5(
                    day,
                    v["accepted"],
                    {
                        **m5,
                        "server": server,
                        "terminal_build": terminal_build,
                        "validation_status": "pass" if v["pass"] else "rejected_rows",
                    },
                )
                day_rec["m5"] = {"status": "saved", **{k: saved[k] for k in ("n", "sha256", "retrieval_id")}, "validation": {k: v[k] for k in v if k != "accepted"}}
                consec_fail = 0

        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            results.append(day_rec)
            break

        # H1 warm-up
        if h1_done(day):
            day_rec["h1"] = {"status": "reused"}
        else:
            h1 = fetch_h1_warmup(handle, SYMBOL, day, warmup_bars=H1_WARMUP_BARS, wall_deadline=wall_deadline)
            if not h1.get("ok"):
                day_rec["h1"] = {"status": "failed", "error": h1.get("error")}
                consec_fail += 1
            else:
                saved = save_h1(
                    day,
                    h1["bars"],
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
                    "n_warmup_available": h1.get("n_warmup_available"),
                    "warmup_sufficient": h1.get("warmup_sufficient"),
                    "sha256": saved["sha256"],
                }
                consec_fail = 0

        # Ticks hour-by-hour
        hour_stats = {"ok": 0, "empty": 0, "failed": 0, "reused": 0}
        for hour in TICK_HOURS:
            if time.monotonic() > wall_deadline:
                stop_reason = "max_wall_seconds"
                break
            if tick_hour_done(day, hour):
                hour_stats["reused"] += 1
                day_rec["ticks"][f"{hour:02d}"] = {"status": "reused"}
                continue
            tk = fetch_ticks_hour(handle, SYMBOL, day, hour, wall_deadline=wall_deadline)
            if not tk.get("ok"):
                hour_stats["failed"] += 1
                day_rec["ticks"][f"{hour:02d}"] = {"status": "failed", "error": tk.get("error")}
                consec_fail += 1
                if consec_fail >= 8:
                    stop_reason = "consecutive_network_failures>=8"
                    break
                continue
            v = validate_ticks(tk["ticks"])
            saved = save_tick_hour(
                day,
                hour,
                v["accepted"],
                {
                    **tk,
                    "server": server,
                    "terminal_build": terminal_build,
                    "validation_status": "pass" if v["pass"] else "rejected_rows",
                    "bid_ask_ok": tk.get("bid_ask_ok") and v.get("pass"),
                },
            )
            if saved["empty"]:
                hour_stats["empty"] += 1
            else:
                hour_stats["ok"] += 1
            day_rec["ticks"][f"{hour:02d}"] = {
                "status": "saved",
                "n": saved["n"],
                "empty": saved["empty"],
                "elapsed_s": tk.get("elapsed_s"),
            }
            consec_fail = 0

        day_rec["tick_hour_stats"] = hour_stats
        day_rec["session_status"] = classify_session(day)
        results.append(day_rec)

        # refresh completion
        state = load_state()
        save_state({**state, "last_stop_reason": stop_reason})
        if stop_reason:
            break

    state = load_state()
    state["last_stop_reason"] = stop_reason
    save_state(state)
    return {
        "results": results,
        "completed_dates": sorted(state["completed"].keys()),
        "pending_dates": state["pending"],
        "stop_reason": stop_reason,
        "resume_command": "PYTHONPATH=src python -m phase40.run_phase40",
    }
