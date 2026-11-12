"""Historical coverage mapping via bounded probes."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from phase38.constants import COVERAGE_PROBE_DAYS, SYMBOL, TICK_SAMPLE_START_HOUR_UTC
from phase38.fetch import fetch_m5_day, fetch_ticks_window
from phase38.validation import classify_interval

UTC = timezone.utc


def build_coverage_map(handle: Any, *, wall_deadline: float) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    for day in COVERAGE_PROBE_DAYS:
        if time.monotonic() > wall_deadline:
            probes.append({"day": day, "status": "NOT_PROBED", "reason": "wall_budget"})
            continue

        m5 = fetch_m5_day(handle, SYMBOL, day, wall_deadline=wall_deadline)
        m5_status = classify_interval(
            None, int(m5.get("n") or 0), m5.get("actual_start"), m5.get("actual_end"), m5.get("error")
        )
        if m5_status == "VERIFIED_COMPLETE_INTERVAL" and m5.get("bars"):
            if int(m5["n"]) < 50:
                m5_status = "VERIFIED_PARTIAL_INTERVAL"

        # Coverage tick probe: 30 minutes only (mapping ≠ acquisition)
        start = datetime.strptime(day, "%Y-%m-%d").replace(
            hour=TICK_SAMPLE_START_HOUR_UTC, minute=0, second=0, tzinfo=UTC
        )
        end = start + timedelta(minutes=30)
        if time.monotonic() > wall_deadline:
            tk = {"ok": False, "error": "wall_budget", "n": 0, "elapsed_s": 0}
            tk_status = "NOT_PROBED"
        else:
            tk = fetch_ticks_window(handle, SYMBOL, start, end, wall_deadline=wall_deadline)
            tk_status = classify_interval(
                None, int(tk.get("n") or 0), tk.get("actual_start"), tk.get("actual_end"), tk.get("error")
            )
            if tk_status.startswith("VERIFIED") and int(tk.get("n") or 0) < 100:
                tk_status = "VERIFIED_PARTIAL_INTERVAL"

        probes.append(
            {
                "day": day,
                "weekday": datetime.strptime(day, "%Y-%m-%d").strftime("%A"),
                "m5": {
                    "requested_start": m5.get("requested_start"),
                    "requested_end": m5.get("requested_end"),
                    "actual_start": m5.get("actual_start"),
                    "actual_end": m5.get("actual_end"),
                    "n": m5.get("n"),
                    "elapsed_s": m5.get("elapsed_s"),
                    "error": m5.get("error"),
                    "mt5_error": m5.get("mt5_error"),
                    "status": m5_status,
                },
                "ticks_liquid_window": {
                    "requested_start": tk.get("requested_start"),
                    "requested_end": tk.get("requested_end"),
                    "actual_start": tk.get("actual_start"),
                    "actual_end": tk.get("actual_end"),
                    "n": tk.get("n"),
                    "elapsed_s": tk.get("elapsed_s"),
                    "error": tk.get("error"),
                    "mt5_error": tk.get("mt5_error"),
                    "status": tk_status,
                    "note": "30m liquid probe only; does not prove full-day tick coverage",
                },
            }
        )

    summary = {
        "m5_complete": sum(1 for p in probes if (p.get("m5") or {}).get("status") == "VERIFIED_COMPLETE_INTERVAL"),
        "m5_partial": sum(1 for p in probes if (p.get("m5") or {}).get("status") == "VERIFIED_PARTIAL_INTERVAL"),
        "m5_empty": sum(1 for p in probes if (p.get("m5") or {}).get("status") == "EMPTY_INTERVAL"),
        "m5_failed": sum(1 for p in probes if (p.get("m5") or {}).get("status") == "UNAVAILABLE_OR_FAILED"),
        "m5_not_probed": sum(1 for p in probes if p.get("status") == "NOT_PROBED" or (p.get("m5") or {}).get("status") == "NOT_PROBED"),
        "tick_complete": sum(1 for p in probes if (p.get("ticks_liquid_window") or {}).get("status") == "VERIFIED_COMPLETE_INTERVAL"),
        "tick_partial": sum(1 for p in probes if (p.get("ticks_liquid_window") or {}).get("status") == "VERIFIED_PARTIAL_INTERVAL"),
        "tick_empty": sum(1 for p in probes if (p.get("ticks_liquid_window") or {}).get("status") == "EMPTY_INTERVAL"),
        "tick_failed": sum(1 for p in probes if (p.get("ticks_liquid_window") or {}).get("status") == "UNAVAILABLE_OR_FAILED"),
    }
    return {
        "coverage_start_utc": "2025-07-01 00:00:00",
        "coverage_end_utc": "2026-09-29 18:50:00",
        "probe_count": len(probes),
        "probes": probes,
        "summary": summary,
        "caveat": "Probe success ≠ full historical completeness. Empty ≠ assumed market closure.",
    }
