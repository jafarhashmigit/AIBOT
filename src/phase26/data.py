"""Approved historical data loader for Phase 26 (no holdout)."""

from __future__ import annotations

from datetime import datetime, timedelta

from phase3.nplib import read_csv_dicts
from phase14.data import fold_of
from phase26.constants import (
    BASELINE_FEATURE_COLS,
    FEATURES_PATH,
    H1_PATH,
    HOLDOUT_NAME,
    MAX_DECISION_TIME_UTC,
    OOS_PATH,
    RESEARCH_CUTOFF_UTC,
)


def parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_m5_bars() -> dict:
    assert HOLDOUT_NAME not in str(FEATURES_PATH)
    times: list[str] = []
    rows: list[dict] = []
    keep = (
        "time",
        "open",
        "high",
        "low",
        "close",
        "spread",
        "atr_14",
        "atr_14_pct",
        "minutes_since_prev_bar",
        "is_after_gap",
        *BASELINE_FEATURE_COLS,
    )
    for row in read_csv_dicts(FEATURES_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        feat = {k: row[k] for k in keep if k in row}
        times.append(t)
        rows.append(feat)
    index = {t: i for i, t in enumerate(times)}
    return {
        "times": times,
        "rows": rows,
        "index": index,
        "holdout_opened": False,
        "research_cutoff": RESEARCH_CUTOFF_UTC,
        "max_decision_time": MAX_DECISION_TIME_UTC,
    }


def load_h1_bars() -> list[dict]:
    out = []
    for row in read_csv_dicts(H1_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        out.append(
            {
                "time": t,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )
    out.sort(key=lambda r: r["time"])
    return out


def load_decision_times() -> list[str]:
    times = []
    seen = set()
    for row in read_csv_dicts(OOS_PATH):
        t = row["decision_time"]
        if t > MAX_DECISION_TIME_UTC or t in seen:
            continue
        seen.add(t)
        if fold_of(t) is None:
            continue
        times.append(t)
    times.sort()
    return times


def train_cutoff_for_fold(fold_id: str) -> str:
    from phase14.constants import FOLDS

    start = FOLDS[fold_id]["start"]
    from phase26.constants import PURGE_MIN

    return fmt_ts(parse_ts(start) - timedelta(minutes=PURGE_MIN))
