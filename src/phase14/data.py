"""Independent Phase 14 data load. Uses phase3.nplib only for CSV IO."""

from __future__ import annotations

from datetime import datetime, timedelta

from phase3.nplib import read_csv_dicts
from phase14.constants import (
    FEATURES_PATH,
    FOLDS,
    H1_PATH,
    MAX_DECISION_TIME,
    OOS_PATH,
    OUTCOMES_PATH,
    PURGE_MINUTES,
    RESEARCH_CUTOFF_UTC,
)

FEATURE_KEEP = (
    "time", "open", "high", "low", "close",
    "close_to_ema_20", "ema_9_20_spread", "atr_14_pct",
    "corrected_session_new_york",
)


def parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fold_of(decision_time: str) -> str | None:
    for fold_id, spec in FOLDS.items():
        if decision_time < spec["start"]:
            continue
        if spec["inclusive_stop"]:
            if decision_time <= spec["stop"]:
                return fold_id
        elif decision_time < spec["stop"]:
            return fold_id
    return None


def train_cutoff_for_fold(fold_id: str) -> str:
    start = FOLDS[fold_id]["start"]
    return fmt_ts(parse_ts(start) - timedelta(minutes=PURGE_MINUTES))


def load_bundle() -> dict:
    features = {}
    feature_times = []
    for row in read_csv_dicts(FEATURES_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        features[t] = {k: row[k] for k in FEATURE_KEEP}
        feature_times.append(t)
    feature_times.sort()
    index = {t: i for i, t in enumerate(feature_times)}

    outcomes = {}
    for row in read_csv_dicts(OUTCOMES_PATH):
        t = row["decision_time"]
        if t > MAX_DECISION_TIME:
            continue
        if str(row.get("eligible")).lower() != "true":
            continue
        if str(row.get("incomplete_window")).lower() == "true":
            continue
        if str(row.get("crosses_gap")).lower() == "true":
            continue
        outcomes[(t, row["side"])] = {
            "net_r": float(row["net_r"]),
            "net_pnl": float(row["net_pnl"]),
            "initial_risk": float(row["initial_risk"]),
            "costs": float(row["costs"]),
            "entry_fill": float(row["entry_fill"]),
            "exit_reason": row["exit_reason"],
            "entry_time": row["entry_time"],
            "exit_time": row["exit_time"],
        }

    timestamps = []
    seen = set()
    for row in read_csv_dicts(OOS_PATH):
        t = row["decision_time"]
        if t > MAX_DECISION_TIME or t in seen:
            continue
        seen.add(t)
        timestamps.append(t)
    timestamps.sort()

    h1_rows = []
    for row in read_csv_dicts(H1_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        h1_rows.append({
            "time": t,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })
    h1_rows.sort(key=lambda r: r["time"])

    return {
        "features": features,
        "feature_times": feature_times,
        "feature_index": index,
        "outcomes": outcomes,
        "timestamps": timestamps,
        "h1_rows": h1_rows,
        "bounds": {
            "n_oos": len(timestamps),
            "first": timestamps[0] if timestamps else None,
            "last": timestamps[-1] if timestamps else None,
            "max_decision_time": MAX_DECISION_TIME,
            "research_cutoff": RESEARCH_CUTOFF_UTC,
        },
    }
