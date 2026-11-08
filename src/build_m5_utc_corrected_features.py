"""Add timezone-correct UTC/session columns without changing existing features.

Investigation (see the verification report):
  * MT5 copy_rates time is a Unix seconds field. pd.to_datetime(unit='s') yields a
    naive datetime whose *clock face* matches the broker server wall clock, not
    UTC. Evidence: daily gold reopen at 18:00 America/New_York lands on 01:00
    (winter) / 00:00 (US-EU DST gap) / 01:00 (summer) in the CSV, which is
    Europe/Athens, not UTC (research_economic_calendar_m5.py, 98.4% of 127
    daily breaks; research_xauusd_ema_pullback.py, 99.7% of 1599 H1 breaks).
  * features_m5.server_time_to_utc() currently does tz_localize('UTC') without
    converting, so hour_utc and session_* are shifted 2–3 hours. Those columns
    are preserved byte-for-byte here.
  * Conversion used: naive stamp -> tz_localize(Europe/Athens) -> tz_convert(UTC),
    using IANA historical DST rules (tzdata). No fixed offset.

Output: src/data/xauusd_m5_features_utc_corrected.csv
  research-period rows only (through the cutoff). Holdout rows are not copied.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from evaluation.constants import DATA_DIR, DEFAULT_SEED, TIME_FORMAT
from evaluation.integrity import assert_holdout_untouched, prepare_research_reads, reports_dir
from evaluation.report import save, wrap
from features_m5 import SESSION_IDS, SESSIONS
from label_m5 import FEATURES_PATH
from research_kronos_m5 import GUARD, assert_no_test_rows

OUTPUT_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
SERVER_TZ = "Europe/Athens"
NEW_COLUMNS = [
    "corrected_time_utc",
    "corrected_hour_utc",
    "corrected_weekday_utc",
    "corrected_session_asia",
    "corrected_session_london",
    "corrected_session_new_york",
    "corrected_session_london_ny_overlap",
    "corrected_session_id",
]


def server_to_utc(times: pd.Series) -> pd.Series:
    naive = pd.to_datetime(times)
    localized = naive.dt.tz_localize(SERVER_TZ, ambiguous="NaT", nonexistent="NaT")
    if localized.isna().any():
        bad = naive[localized.isna()].head(5).tolist()
        raise RuntimeError(f"DST-ambiguous or nonexistent server timestamps, e.g. {bad}")
    return localized.dt.tz_convert("UTC")


def add_corrected_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    utc = server_to_utc(out["time"])
    out["corrected_time_utc"] = utc.dt.strftime(TIME_FORMAT)
    out["corrected_hour_utc"] = utc.dt.hour.astype(int)
    out["corrected_weekday_utc"] = utc.dt.day_of_week.astype(int)
    for name, (tz, start_hour, end_hour) in SESSIONS.items():
        local_hour = utc.dt.tz_convert(tz).dt.hour
        out[f"corrected_session_{name}"] = ((local_hour >= start_hour) & (local_hour < end_hour)).astype(int)
    out["corrected_session_london_ny_overlap"] = (
        out["corrected_session_london"] & out["corrected_session_new_york"]
    ).astype(int)
    session_id = pd.Series(SESSION_IDS["off_hours"], index=out.index)
    session_id[out["corrected_session_asia"] == 1] = SESSION_IDS["asia"]
    session_id[out["corrected_session_london"] == 1] = SESSION_IDS["london"]
    session_id[out["corrected_session_new_york"] == 1] = SESSION_IDS["new_york"]
    session_id[out["corrected_session_london_ny_overlap"] == 1] = SESSION_IDS["london_ny_overlap"]
    out["corrected_session_id"] = session_id.astype(int)
    return out


def daily_reopen_check(times: pd.Series) -> dict:
    """Share of daily gaps whose next bar is 18:00 America/New_York after conversion."""
    utc = server_to_utc(times)
    gap = times.diff() > pd.Timedelta(minutes=5)
    reopen = times[gap]
    ny = utc[gap].dt.tz_convert("America/New_York")
    hit = (ny.dt.hour == 18) & (ny.dt.minute == 0)
    return {"n_gaps": int(gap.sum()), "n_18_00_ny": int(hit.sum()),
            "share_18_00_ny": float(hit.mean()) if gap.any() else float("nan")}


def dst_anchor_check(df: pd.DataFrame) -> dict:
    """Weekday noon stamps around 2026 DST transitions (Sunday clocks are closed).

    US spring-forward: 2026-03-08 02:00 America/New_York. Athens still UTC+2.
    EU spring-forward: 2026-03-29 03:00 Europe/Athens, then UTC+3.
    """
    utc = server_to_utc(df["time"])
    rows = {}
    expected_offset = {
        "2026-03-06 12:00:00": 2,   # Friday before US DST
        "2026-03-09 12:00:00": 2,   # Monday after US DST; Athens still winter
        "2026-03-27 12:00:00": 2,   # Friday before EU DST
        "2026-03-30 12:00:00": 3,   # Monday after EU DST
    }
    for stamp, offset in expected_offset.items():
        hit = df["time"] == pd.Timestamp(stamp)
        if not hit.any():
            rows[stamp] = {"present": False, "expected_athens_offset_hours": offset}
            continue
        u = utc[hit].iloc[0]
        athens = pd.Timestamp(stamp).tz_localize("Europe/Athens")
        got = int(athens.utcoffset().total_seconds() // 3600)
        rows[stamp] = {
            "present": True,
            "utc": u.strftime(TIME_FORMAT),
            "athens_offset_hours": got,
            "expected_athens_offset_hours": offset,
            "offset_ok": got == offset,
            "matches_localize": bool(u == athens.tz_convert("UTC")),
            "corrected_hour_utc": int(u.hour),
        }
    return rows


def original_columns_unchanged(original: pd.DataFrame, corrected: pd.DataFrame) -> bool:
    shared = [c for c in original.columns]
    return original[shared].equals(corrected[shared])


def causality_prefix(df: pd.DataFrame, cut: pd.Timestamp) -> bool:
    """Corrected columns on rows <= cut equal those computed from the truncated frame."""
    full = df[df["time"] <= cut]
    rebuilt = add_corrected_columns(full.drop(columns=[c for c in NEW_COLUMNS if c in full.columns], errors="ignore"))
    return np.array_equal(full[NEW_COLUMNS].to_numpy(), rebuilt[NEW_COLUMNS].to_numpy())


def run(boundary: dict) -> dict:
    features = pd.read_csv(FEATURES_PATH)
    features["time"] = pd.to_datetime(features["time"], format=TIME_FORMAT)
    features = features[features["time"] <= boundary["cutoff"]].reset_index(drop=True)
    assert_no_test_rows(features)

    original_cols = list(features.columns)
    corrected = add_corrected_columns(features)
    if not original_columns_unchanged(features, corrected[original_cols]):
        raise RuntimeError("original feature columns changed")

    reopen = daily_reopen_check(features["time"])
    dst = dst_anchor_check(features)
    cuts = [
        pd.Timestamp("2026-03-29 00:00:00"),
        pd.Timestamp("2026-06-19 03:05:00"),
        pd.Timestamp("2026-08-26 13:55:00"),
        boundary["val_end"],
    ]
    prefix_ok = {str(c): causality_prefix(corrected, c) for c in cuts}

    out = corrected.copy()
    out["time"] = out["time"].dt.strftime(TIME_FORMAT)
    out.to_csv(OUTPUT_PATH, index=False)

    hour_shift = (corrected["corrected_hour_utc"] - features["hour_utc"]).mod(24)
    summary = {
        "rows": int(len(corrected)),
        "range": [str(features["time"].iloc[0]), str(features["time"].iloc[-1])],
        "server_timezone": SERVER_TZ,
        "new_columns": NEW_COLUMNS,
        "original_columns_unchanged": True,
        "daily_reopen": reopen,
        "dst_anchors": dst,
        "prefix_causality": prefix_ok,
        "hour_utc_shift_mode": int(hour_shift.mode().iloc[0]) if len(hour_shift) else None,
        "session_london_disagreement_share": float(
            (corrected["corrected_session_london"] != features["session_london"]).mean()
        ),
        "output": str(OUTPUT_PATH),
        "holdout": {"test_open_attempts": GUARD["test_open_attempts"]},
    }
    if reopen["share_18_00_ny"] < 0.95:
        raise RuntimeError(f"reopen-NY check too weak: {reopen}")
    if not all(prefix_ok.values()):
        raise RuntimeError(f"prefix causality failed: {prefix_ok}")
    if any(not v.get("present") for v in dst.values()):
        raise RuntimeError(f"DST weekday anchors missing: {dst}")
    if any(v.get("present") and not v.get("offset_ok") for v in dst.values()):
        raise RuntimeError(f"DST offset mismatch: {dst}")
    assert_holdout_untouched()
    save(reports_dir() / "utc_correction_verification.json",
         wrap("utc_corrected_features", "reproduction", {"server_tz": SERVER_TZ}, summary, DEFAULT_SEED))
    print("Saved", OUTPUT_PATH, "rows", summary["rows"])
    print("daily reopen 18:00 NY share", reopen["share_18_00_ny"])
    print("hour_utc shift mode", summary["hour_utc_shift_mode"])
    print("London session disagreement", summary["session_london_disagreement_share"])
    return summary


def main() -> None:
    run(prepare_research_reads())


if __name__ == "__main__":
    main()
