"""Load approved Phase 2 OOS rows and join decision-time UTC features through val_end."""

from __future__ import annotations

import csv
from datetime import datetime

from phase3.dataset import load_oos, to_wide
from phase3.nplib import parse_time
from phase4.constants import (
    PHASE2_OOS_SHA256,
    RESEARCH_CUTOFF,
    TIME_FORMAT,
    UTC_FEATURES_PATH,
    UTC_KEEP,
    VALIDATION_END,
)


def load_utc_features() -> dict:
    """Read only listed columns. Stop at validation end. Never open the holdout."""
    by_time = {}
    n_read = 0
    n_kept = 0
    n_after_val = 0
    with open(UTC_FEATURES_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in UTC_KEEP if c not in reader.fieldnames]
        if missing:
            raise RuntimeError(f"UTC feature file missing columns: {missing}")
        for rec in reader:
            n_read += 1
            stamp = rec["time"]
            if stamp > RESEARCH_CUTOFF:
                raise RuntimeError(f"UTC feature timestamp exceeds cutoff: {stamp}")
            if stamp > VALIDATION_END:
                n_after_val += 1
                continue
            t = datetime.strptime(stamp, TIME_FORMAT)
            by_time[t] = {
                "atr_14_pct": float(rec["atr_14_pct"]),
                "ema_9_20_spread": float(rec["ema_9_20_spread"]),
                "volatility_ratio_12_48": float(rec["volatility_ratio_12_48"]),
                "minutes_since_prev_bar": float(rec["minutes_since_prev_bar"]) if rec["minutes_since_prev_bar"] else float("nan"),
                "corrected_hour_utc": int(float(rec["corrected_hour_utc"])),
                "corrected_weekday_utc": int(float(rec["corrected_weekday_utc"])),
                "corrected_session_asia": int(float(rec["corrected_session_asia"])),
                "corrected_session_london": int(float(rec["corrected_session_london"])),
                "corrected_session_new_york": int(float(rec["corrected_session_new_york"])),
                "corrected_session_london_ny_overlap": int(float(rec["corrected_session_london_ny_overlap"])),
                "corrected_session_id": int(float(rec["corrected_session_id"])),
            }
            n_kept += 1
    return {
        "by_time": by_time,
        "n_read": n_read,
        "n_kept_through_val_end": n_kept,
        "n_skipped_after_val_end": n_after_val,
        "path": str(UTC_FEATURES_PATH),
    }


def join_wide(wide: list[dict], utc: dict) -> tuple[list[dict], dict]:
    by_time = utc["by_time"]
    out = []
    missing = 0
    for row in wide:
        feat = by_time.get(row["decision_time"])
        if feat is None:
            missing += 1
            continue
        item = dict(row)
        item.update(feat)
        out.append(item)
    info = {
        "n_wide": len(wide),
        "n_joined": len(out),
        "n_missing_features": missing,
        "oos_sha256_expected": PHASE2_OOS_SHA256,
    }
    if missing:
        raise RuntimeError(f"{missing} OOS timestamps missing UTC features; stopping")
    return out, info


def load_phase4_frame() -> tuple[list[dict], list[dict], dict]:
    long_rows = load_oos()
    wide = to_wide(long_rows)
    utc = load_utc_features()
    joined, join_info = join_wide(wide, utc)
    return long_rows, joined, {"utc": {k: v for k, v in utc.items() if k != "by_time"}, "join": join_info}
