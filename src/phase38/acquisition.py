"""Bounded resumable acquisition of representative dates."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from phase38.constants import (
    MAX_ACQUIRE_DATES,
    RAW_M5_DIR,
    RAW_TICKS_DIR,
    REPRESENTATIVE_DATES,
    STATE_DIR,
    SYMBOL,
    TICK_SAMPLE_HOURS,
    TICK_SAMPLE_START_HOUR_UTC,
)
from phase38.fetch import fetch_m5_day, fetch_ticks_window
from phase38.storage import save_m5_chunk, save_ticks_chunk
from phase38.validation import validate_m5_bars, validate_ticks

UTC = timezone.utc


def _state_path() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "acquisition_state.json"


def load_state() -> dict[str, Any]:
    """Reconcile state with on-disk chunks so tests/stale state cannot skip real work."""
    completed: dict[str, Any] = {}
    pending: list[str] = []
    for d in REPRESENTATIVE_DATES[:MAX_ACQUIRE_DATES]:
        if _m5_done(d) and _ticks_done(d):
            completed[d] = {"m5": True, "ticks": True}
        else:
            pending.append(d)
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


def _m5_done(day: str) -> bool:
    return (RAW_M5_DIR / f"m5_{SYMBOL}_{day}.jsonl").is_file()


def _ticks_done(day: str) -> bool:
    tag = f"{TICK_SAMPLE_START_HOUR_UTC:02d}h"
    return (RAW_TICKS_DIR / f"ticks_{SYMBOL}_{day}_{tag}.jsonl").is_file()


def acquire_representative_dates(
    handle: Any,
    *,
    server: str | None,
    terminal_build: Any,
    wall_deadline: float,
) -> dict[str, Any]:
    state = load_state()
    dates = list(state.get("pending") or REPRESENTATIVE_DATES[:MAX_ACQUIRE_DATES])
    # ensure max 10
    dates = dates[:MAX_ACQUIRE_DATES]
    results: list[dict[str, Any]] = []
    stop_reason = None

    for day in dates:
        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            break
        day_rec: dict[str, Any] = {"day": day, "m5": None, "ticks": None}

        # M5
        if _m5_done(day):
            day_rec["m5"] = {"status": "reused_existing_chunk", "path": str(RAW_M5_DIR / f"m5_{SYMBOL}_{day}.jsonl")}
        else:
            m5 = fetch_m5_day(handle, SYMBOL, day, wall_deadline=wall_deadline)
            if not m5.get("ok"):
                day_rec["m5"] = {"status": "failed", "error": m5.get("error"), "mt5_error": m5.get("mt5_error")}
            else:
                v = validate_m5_bars(m5.get("bars") or [])
                accepted = v.pop("accepted")
                try:
                    saved = save_m5_chunk(
                        accepted,
                        day=day,
                        requested_start=m5["requested_start"],
                        requested_end=m5["requested_end"],
                        actual_start=m5.get("actual_start"),
                        actual_end=m5.get("actual_end"),
                        validation=v,
                        terminal_build=terminal_build,
                        server=server,
                        mt5_error=m5.get("mt5_error"),
                        elapsed_s=float(m5.get("elapsed_s") or 0),
                    )
                    day_rec["m5"] = {
                        "status": "saved",
                        "n_accepted": v.get("n_accepted"),
                        "n_rejected": v.get("n_rejected"),
                        "validation_pass": v.get("pass"),
                        "sha256": saved["sha256"],
                        "retrieval_id": saved["retrieval_id"],
                        "elapsed_s": m5.get("elapsed_s"),
                    }
                except FileExistsError as exc:
                    day_rec["m5"] = {"status": "exists_conflict", "error": str(exc)}

        if time.monotonic() > wall_deadline:
            stop_reason = "max_wall_seconds"
            results.append(day_rec)
            break

        # Ticks liquid window
        hour_tag = f"{TICK_SAMPLE_START_HOUR_UTC:02d}h"
        if _ticks_done(day):
            day_rec["ticks"] = {
                "status": "reused_existing_chunk",
                "path": str(RAW_TICKS_DIR / f"ticks_{SYMBOL}_{day}_{hour_tag}.jsonl"),
            }
        else:
            start = datetime.strptime(day, "%Y-%m-%d").replace(
                hour=TICK_SAMPLE_START_HOUR_UTC, minute=0, second=0, tzinfo=UTC
            )
            end = start + timedelta(hours=TICK_SAMPLE_HOURS)
            tk = fetch_ticks_window(handle, SYMBOL, start, end, wall_deadline=wall_deadline)
            if not tk.get("ok"):
                day_rec["ticks"] = {"status": "failed", "error": tk.get("error"), "mt5_error": tk.get("mt5_error")}
            else:
                v = validate_ticks(tk.get("ticks") or [])
                accepted = v.pop("accepted")
                try:
                    saved = save_ticks_chunk(
                        accepted,
                        day=day,
                        hour_tag=hour_tag,
                        requested_start=tk["requested_start"],
                        requested_end=tk["requested_end"],
                        actual_start=tk.get("actual_start"),
                        actual_end=tk.get("actual_end"),
                        validation=v,
                        terminal_build=terminal_build,
                        server=server,
                        mt5_error=tk.get("mt5_error"),
                        elapsed_s=float(tk.get("elapsed_s") or 0),
                    )
                    day_rec["ticks"] = {
                        "status": "saved",
                        "n_accepted": v.get("n_accepted"),
                        "n_rejected": v.get("n_rejected"),
                        "validation_pass": v.get("pass"),
                        "sha256": saved["sha256"],
                        "retrieval_id": saved["retrieval_id"],
                        "elapsed_s": tk.get("elapsed_s"),
                        "window_note": "liquid hours only; not full-day ticks",
                    }
                except FileExistsError as exc:
                    day_rec["ticks"] = {"status": "exists_conflict", "error": str(exc)}

        # mark complete if both present
        if _m5_done(day) and _ticks_done(day):
            state.setdefault("completed", {})[day] = {"m5": True, "ticks": True}
            if day in state.get("pending", []):
                state["pending"].remove(day)
        results.append(day_rec)
        save_state(state)

    pending = [d for d in dates if d not in state.get("completed", {})]
    state["pending"] = pending
    state["last_stop_reason"] = stop_reason
    save_state(state)

    return {
        "dates_targeted": dates,
        "results": results,
        "completed_days": sorted(state.get("completed", {}).keys()),
        "pending_days": pending,
        "stop_reason": stop_reason,
        "resume_command": "PYTHONPATH=src python -m phase38.run_phase38",
    }
