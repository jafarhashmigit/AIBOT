"""Load research tables without opening the holdout. Numpy/nplib only."""

from __future__ import annotations

from datetime import datetime, timedelta

from phase3.nplib import read_csv_dicts
from phase13.constants import (
    FEATURES_PATH,
    FOLDS,
    H1_PATH,
    MAX_DECISION_TIME,
    OOS_PATH,
    OUTCOMES_PATH,
    PURGE_MINUTES,
    RESEARCH_CUTOFF_UTC,
)

FEATURE_COLS = (
    "time", "open", "high", "low", "close",
    "atr_14_pct", "ema_9_20_spread", "ema_20_50_spread", "close_to_ema_20",
    "corrected_session_new_york",
)


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fold_of(decision_time: str) -> str | None:
    for fold_id, spec in FOLDS.items():
        if decision_time < spec["start"]:
            continue
        if spec["inclusive_stop"]:
            if decision_time <= spec["stop"]:
                return fold_id
        else:
            if decision_time < spec["stop"]:
                return fold_id
    return None


def load_research_bundle() -> dict:
    features = {}
    feature_times = []
    for row in read_csv_dicts(FEATURES_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        features[t] = {c: row[c] for c in FEATURE_COLS}
        feature_times.append(t)
    feature_times.sort()

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
        key = (t, row["side"])
        outcomes[key] = {
            "net_r": float(row["net_r"]),
            "net_pnl": float(row["net_pnl"]),
            "initial_risk": float(row["initial_risk"]),
            "costs": float(row["costs"]),
        }

    oos_by_time: dict[str, dict] = {}
    for row in read_csv_dicts(OOS_PATH):
        t = row["decision_time"]
        if t > MAX_DECISION_TIME:
            continue
        bucket = oos_by_time.setdefault(t, {"fold_id": row["fold_id"], "pred_r_rf": {}})
        bucket["pred_r_rf"][row["side"]] = float(row["pred_r_rf"])
        bucket["actual_net_r"] = bucket.get("actual_net_r", {})
        bucket["actual_net_r"][row["side"]] = float(row["actual_net_r"])
        bucket["actual_net_pnl"] = bucket.get("actual_net_pnl", {})
        bucket["actual_net_pnl"][row["side"]] = float(row["actual_net_pnl"])

    timestamps = sorted(oos_by_time)
    # Index positions in feature_times for rolling windows
    index = {t: i for i, t in enumerate(feature_times)}

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
        "oos": oos_by_time,
        "timestamps": timestamps,
        "h1_rows": h1_rows,
        "bounds": {
            "features_first": feature_times[0] if feature_times else None,
            "features_last": feature_times[-1] if feature_times else None,
            "oos_first": timestamps[0] if timestamps else None,
            "oos_last": timestamps[-1] if timestamps else None,
            "n_oos_timestamps": len(timestamps),
            "n_eligible_outcome_keys": len(outcomes),
            "max_decision_time": MAX_DECISION_TIME,
            "research_cutoff": RESEARCH_CUTOFF_UTC,
        },
    }


def train_times_for_fold(timestamps: list[str], fold_id: str) -> list[str]:
    start = FOLDS[fold_id]["start"]
    cutoff = _fmt(_parse(start) - timedelta(minutes=PURGE_MINUTES))
    return [t for t in timestamps if t <= cutoff]


def eval_times_for_fold(timestamps: list[str], fold_id: str) -> list[str]:
    return [t for t in timestamps if fold_of(t) == fold_id]
