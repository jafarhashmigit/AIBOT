"""Approved M5 dataset integrity audit (no holdout)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from phase31.constants import FEATURES_UTC_PATH, HOLDOUT_NAME, RAW_M5_PATH, RESEARCH_CUTOFF_UTC


def _assert_no_holdout(path) -> None:
    if HOLDOUT_NAME in str(path):
        raise RuntimeError("HARD FAILURE: holdout path referenced")


def run_data_integrity_audit() -> dict[str, Any]:
    _assert_no_holdout(RAW_M5_PATH)
    _assert_no_holdout(FEATURES_UTC_PATH)
    raw = pd.read_csv(RAW_M5_PATH)
    feat = pd.read_csv(FEATURES_UTC_PATH)

    raw["time"] = pd.to_datetime(raw["time"], format="%Y-%m-%d %H:%M:%S")
    feat["time"] = pd.to_datetime(feat["time"], format="%Y-%m-%d %H:%M:%S")
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)

    # Cap analysis at research cutoff for feature store (approved research surface).
    feat_cut = feat[feat["time"] <= cutoff].copy()
    raw_cut = raw[raw["time"] <= cutoff].copy()

    diffs = raw_cut["time"].diff().dt.total_seconds() / 60.0
    gaps = diffs[diffs > 5]
    known_gap_count = int((diffs > 5).sum())

    ohlc_bad = int(
        (
            (raw_cut[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (raw_cut["high"] < raw_cut[["open", "close", "low"]].max(axis=1))
            | (raw_cut["low"] > raw_cut[["open", "close", "high"]].min(axis=1))
        ).sum()
    )
    atr_bad = 0
    if "atr_14" in feat_cut.columns:
        atr_bad = int(((feat_cut["atr_14"].isna()) | (feat_cut["atr_14"] <= 0)).sum())

    # Timezone: naive stamps as Europe/Athens → UTC; compare corrected columns if present.
    tz_report: dict[str, Any] = {"server_tz": "Europe/Athens", "method": "astimezone(UTC)"}
    try:
        athens = ZoneInfo("Europe/Athens")
        # Sample around typical DST transitions (EU last Sunday March / October)
        samples = []
        for ts in (
            "2026-03-29 02:00:00",
            "2026-03-29 04:00:00",
            "2026-10-25 02:00:00",
            "2026-10-25 04:00:00",
            "2026-06-15 12:00:00",
            "2026-01-15 12:00:00",
        ):
            naive = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            local = naive.replace(tzinfo=athens)
            utc = local.astimezone(ZoneInfo("UTC"))
            samples.append(
                {
                    "athens_wall": ts,
                    "utc": utc.strftime("%Y-%m-%d %H:%M:%S"),
                    "utc_offset_hours": utc.utcoffset().total_seconds() / 3600.0 if utc.utcoffset() else None,
                }
            )
        tz_report["dst_samples"] = samples
        tz_report["tzdata_available"] = True
        # If corrected_hour_utc exists, spot-check a mid-summer row
        if "corrected_hour_utc" in feat_cut.columns and len(feat_cut):
            row = feat_cut.iloc[len(feat_cut) // 2]
            wall = row["time"].to_pydatetime().replace(tzinfo=athens)
            expect_hour = wall.astimezone(ZoneInfo("UTC")).hour
            tz_report["mid_sample_check"] = {
                "feature_time_naive": str(row["time"]),
                "corrected_hour_utc": int(row["corrected_hour_utc"]),
                "expected_utc_hour_if_athens": expect_hour,
                "match": int(row["corrected_hour_utc"]) == expect_hour,
            }
    except Exception as exc:  # noqa: BLE001
        tz_report["tzdata_available"] = False
        tz_report["error"] = f"{type(exc).__name__}:{exc}"

    post_cutoff_feat = int((feat["time"] > cutoff).sum())
    post_cutoff_raw = int((raw["time"] > cutoff).sum())

    return {
        "holdout_opened": False,
        "raw_path": str(RAW_M5_PATH),
        "features_utc_path": str(FEATURES_UTC_PATH),
        "raw_rows_le_cutoff": int(len(raw_cut)),
        "feature_rows_le_cutoff": int(len(feat_cut)),
        "timestamp_ordered_raw": bool(raw_cut["time"].is_monotonic_increasing),
        "timestamp_ordered_feat": bool(feat_cut["time"].is_monotonic_increasing),
        "duplicate_timestamps_raw": int(raw_cut["time"].duplicated().sum()),
        "duplicate_timestamps_feat": int(feat_cut["time"].duplicated().sum()),
        "gaps_gt_5min_count": known_gap_count,
        "gaps_gt_5min_note": "Expected weekends/closures; previously cited ~188 gaps — count is for <=cutoff.",
        "median_gap_minutes_when_gt_5": float(np.median(gaps)) if len(gaps) else None,
        "ohlc_invalid_count": ohlc_bad,
        "atr_invalid_count": atr_bad,
        "post_cutoff_feature_rows": post_cutoff_feat,
        "post_cutoff_raw_rows": post_cutoff_raw,
        "cutoff_enforced_on_research_slice": True,
        "timezone": tz_report,
        "internally_valid": ohlc_bad == 0
        and atr_bad == 0
        and raw_cut["time"].is_monotonic_increasing
        and feat_cut["time"].is_monotonic_increasing
        and raw_cut["time"].duplicated().sum() == 0,
    }
