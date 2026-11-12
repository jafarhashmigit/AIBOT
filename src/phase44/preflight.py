"""Phase43 integrity preflight before any hypothesis research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase44.constants import (
    DISCOVERY_DATES,
    PHASE43_MANIFESTS,
    PHASE43_RAW_H1,
    PHASE43_RAW_M5,
    PHASE43_RAW_TICKS,
    PHASE43_REPORTS,
    SYMBOL,
    VALIDATION_DATES,
    file_sha256,
)
from phase44.progress import write_json


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def run_preflight() -> dict[str, Any]:
    fails: list[str] = []
    # Phase43 independent verification artifact
    indep_path = PHASE43_REPORTS / "independent_verification.json"
    p43_indep_ok = None
    if indep_path.is_file():
        p43_indep_ok = bool(json.loads(indep_path.read_text(encoding="utf-8")).get("ok"))
        if not p43_indep_ok:
            fails.append("phase43_independent_verification_not_ok")
    else:
        fails.append("phase43_independent_verification_missing")

    # Re-hash selected date files
    dates = DISCOVERY_DATES + VALIDATION_DATES
    file_checks = []
    tick_density = []
    for day in dates:
        m5p = PHASE43_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl"
        h1p = PHASE43_RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl"
        if not m5p.is_file():
            fails.append(f"missing_m5:{day}")
        if not h1p.is_file():
            fails.append(f"missing_h1:{day}")
        m5 = _load_jsonl(m5p)
        h1 = _load_jsonl(h1p)
        warmup = [b for b in h1 if (b.get("close_time_utc") or "") < f"{day} 00:00:00"]
        hour_n = {}
        empty_hours = []
        missing_hours = []
        n_ticks = 0
        bid_ask_bad = 0
        for h in range(24):
            tp = PHASE43_RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"
            if not tp.is_file():
                missing_hours.append(h)
                hour_n[h] = None
                continue
            rows = _load_jsonl(tp)
            hour_n[h] = len(rows)
            n_ticks += len(rows)
            if not rows:
                empty_hours.append(h)
            for t in rows:
                if t.get("bid") is None or t.get("ask") is None or float(t["ask"]) < float(t["bid"]):
                    bid_ask_bad += 1
        # M5 chronology
        epochs = [int(b["time_epoch"]) for b in m5]
        gaps = sum(1 for i in range(1, len(epochs)) if epochs[i] - epochs[i - 1] != 300 and 0 < epochs[i] - epochs[i - 1] < 1800)
        shortened = len(m5) < 200  # holiday / short session heuristic
        row = {
            "day": day,
            "m5_n": len(m5),
            "m5_first": m5[0]["timestamp_utc"] if m5 else None,
            "m5_last": m5[-1]["timestamp_utc"] if m5 else None,
            "m5_unexpected_gaps": gaps,
            "h1_warmup_n": len(warmup),
            "h1_warmup_ok": len(warmup) >= 30,
            "ema20_ready": len(warmup) >= 20,
            "tick_n": n_ticks,
            "empty_hours": empty_hours,
            "missing_hours": missing_hours,
            "bid_ask_bad": bid_ask_bad,
            "shortened_session_flag": shortened,
            "m5_sha256": file_sha256(m5p) if m5p.is_file() else None,
            "h1_sha256": file_sha256(h1p) if h1p.is_file() else None,
        }
        file_checks.append(row)
        tick_density.append({"day": day, "tick_n": n_ticks, "by_hour": hour_n})
        if missing_hours:
            fails.append(f"missing_tick_hours:{day}:{missing_hours}")
        if not row["h1_warmup_ok"]:
            fails.append(f"h1_warmup_insufficient:{day}")
        if len(m5) == 0:
            fails.append(f"empty_m5:{day}")

    # Unusual tick counts
    counts = [r["tick_n"] for r in file_checks if r["tick_n"]]
    med = sorted(counts)[len(counts) // 2] if counts else 0
    unusual = [
        {"day": r["day"], "tick_n": r["tick_n"], "note": "high" if r["tick_n"] > 3 * med else "low"}
        for r in file_checks
        if counts and (r["tick_n"] > 3 * med or r["tick_n"] < max(1, med // 5))
    ]

    # Spot-check manifests exist for selected days
    man_n = 0
    man_fail = 0
    if PHASE43_MANIFESTS.is_dir():
        for day in dates:
            for man in PHASE43_MANIFESTS.glob(f"*_{day}*.manifest.json"):
                man_n += 1
                meta = json.loads(man.read_text(encoding="utf-8"))
                p = Path(meta["file_path"])
                if not p.is_file() or file_sha256(p) != meta.get("sha256"):
                    man_fail += 1
                    fails.append(f"manifest_hash_fail:{man.name}")

    payload = {
        "ok": len(fails) == 0,
        "fails": fails[:50],
        "n_fails": len(fails),
        "phase43_independent_ok": p43_indep_ok,
        "n_dates_checked": len(dates),
        "discovery_dates_locked": DISCOVERY_DATES,
        "validation_dates_locked": VALIDATION_DATES,
        "file_checks": file_checks,
        "tick_density": tick_density,
        "unusual_tick_counts": unusual,
        "median_tick_n": med,
        "manifests_checked": man_n,
        "manifest_fails": man_fail,
        "demo_spread_note": "MetaQuotes-Demo spreads are not live broker execution truth",
        "allocation_note": "Dates frozen from Phase43; never reallocated by returns",
    }
    write_json("preflight.json", payload)
    return payload
