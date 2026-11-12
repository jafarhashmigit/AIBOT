"""Independent feature recomputation from raw OHLCV (no features_m5 function calls)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase32.constants import (
    BAR_MINUTES,
    FEATURES_PATH,
    FEATURES_UTC_PATH,
    HOLDOUT_NAME,
    RAW_M5_PATH,
    RESEARCH_CUTOFF_UTC,
    SERVER_TZ,
    SESSION_IDS,
    SESSIONS,
)


def _assert_no_holdout(path) -> None:
    if HOLDOUT_NAME in str(path):
        raise RuntimeError("HARD FAILURE: holdout path referenced")


def load_raw_independent() -> pd.DataFrame:
    """Load and validate raw M5 without calling features_m5.load_and_validate."""
    _assert_no_holdout(RAW_M5_PATH)
    df = pd.read_csv(RAW_M5_PATH)
    need = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    for c in need[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=need)
    off = (df["time"].dt.second != 0) | (df["time"].dt.minute % BAR_MINUTES != 0)
    df = df[~off]
    bad = (
        (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df["tick_volume"] < 0)
        | (df["spread"] < 0)
    )
    df = df[~bad].sort_values("time", kind="stable")
    df = df[~df.duplicated()].drop_duplicates(subset=["time"], keep="first").reset_index(drop=True)
    return df


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, min_periods=span, adjust=False).mean()


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def recompute_features_independent(raw: pd.DataFrame | None = None) -> pd.DataFrame:
    """Recompute Phase1-style features independently from raw OHLC."""
    df = (raw if raw is not None else load_raw_independent()).copy()
    close = df["close"]

    for span in (9, 20, 50):
        ema = _ema(close, span)
        df[f"ema_{span}"] = ema
        df[f"close_to_ema_{span}"] = close / ema - 1
    df["ema_9_20_spread"] = df["ema_9"] / df["ema_20"] - 1
    df["ema_20_50_spread"] = df["ema_20"] / df["ema_50"] - 1

    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    df["macd"] = ema12 - ema26
    df["macd_signal"] = _ema(df["macd"], 9)
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    delta = close.diff()
    avg_gain = _wilder(delta.clip(lower=0), 14)
    avg_loss = _wilder((-delta).clip(lower=0), 14)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    df["rsi_14"] = rsi

    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    upper = mid + 2.0 * std
    lower = mid - 2.0 * std
    band = (upper - lower).replace(0, np.nan)
    df["bb_middle"] = mid
    df["bb_upper"] = upper
    df["bb_lower"] = lower
    df["bb_width"] = band / mid
    df["bb_percent_b"] = ((close - lower) / band).where(band.notna(), 0.5)
    df.loc[mid.isna(), ["bb_width", "bb_percent_b"]] = np.nan

    prev = close.shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1, skipna=False)
    df["atr_14"] = _wilder(tr, 14)
    df["atr_14_pct"] = df["atr_14"] / close

    top = df[["open", "close"]].max(axis=1)
    bot = df[["open", "close"]].min(axis=1)
    rng = df["high"] - df["low"]
    df["candle_body"] = close - df["open"]
    df["candle_body_abs"] = df["candle_body"].abs()
    df["upper_wick"] = df["high"] - top
    df["lower_wick"] = bot - df["low"]
    df["candle_range"] = rng
    safe = rng.replace(0, np.nan)
    for col in ("candle_body_abs", "upper_wick", "lower_wick"):
        df[f"{col}_to_range"] = (df[col] / safe).fillna(0.0)
    df["candle_range_to_atr"] = rng / df["atr_14"]

    df["log_return_1"] = np.log(close / close.shift(1))
    for bars in (1, 3, 6, 12):
        df[f"return_{bars}"] = close.pct_change(bars)
    for bars in (10, 20):
        df[f"momentum_{bars}"] = close - close.shift(bars)
        df[f"roc_{bars}"] = close.pct_change(bars)
    for w in (12, 48):
        df[f"volatility_{w}"] = df["log_return_1"].rolling(w).std()
    df["volatility_ratio_12_48"] = df["volatility_12"] / df["volatility_48"].replace(0, np.nan)

    vol = df["tick_volume"].astype(float)
    rm = vol.rolling(20).mean()
    rs = vol.rolling(20).std()
    df["log_tick_volume"] = np.log1p(vol)
    df["tick_volume_change"] = df["log_tick_volume"].diff()
    df["tick_volume_ratio_20"] = vol / rm.replace(0, np.nan)
    df["tick_volume_zscore_20"] = ((vol - rm) / rs.replace(0, np.nan)).where(rs != 0, 0.0)
    df.loc[rm.isna(), "tick_volume_zscore_20"] = np.nan

    # Original Phase1 clock path treated naive stamps as UTC (documented incorrect vs Athens).
    time_as_utc = df["time"].dt.tz_localize("UTC")
    df["time_utc"] = time_as_utc.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["hour"] = df["time"].dt.hour
    df["minute"] = df["time"].dt.minute
    df["weekday"] = df["time"].dt.day_of_week
    df["hour_utc"] = time_as_utc.dt.hour
    minute_of_day = time_as_utc.dt.hour * 60 + time_as_utc.dt.minute
    df["time_of_day_sin"] = np.sin(2 * np.pi * minute_of_day / 1440)
    df["time_of_day_cos"] = np.cos(2 * np.pi * minute_of_day / 1440)
    df["weekday_sin"] = np.sin(2 * np.pi * df["weekday"] / 7)
    df["weekday_cos"] = np.cos(2 * np.pi * df["weekday"] / 7)
    for name, (tz, start_hour, end_hour) in SESSIONS.items():
        local_hour = time_as_utc.dt.tz_convert(tz).dt.hour
        df[f"session_{name}"] = ((local_hour >= start_hour) & (local_hour < end_hour)).astype(int)
    df["session_london_ny_overlap"] = (df["session_london"] & df["session_new_york"]).astype(int)
    sid = pd.Series(SESSION_IDS["off_hours"], index=df.index)
    sid[df["session_asia"] == 1] = SESSION_IDS["asia"]
    sid[df["session_london"] == 1] = SESSION_IDS["london"]
    sid[df["session_new_york"] == 1] = SESSION_IDS["new_york"]
    sid[df["session_london_ny_overlap"] == 1] = SESSION_IDS["london_ny_overlap"]
    df["session_id"] = sid
    gap_m = df["time"].diff().dt.total_seconds() / 60
    df["minutes_since_prev_bar"] = gap_m
    df["is_after_gap"] = (gap_m > BAR_MINUTES).astype(int)

    # Drop warmup: first row where all indicator features are finite
    non_feat = {"time", "time_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"}
    feat_cols = [c for c in df.columns if c not in non_feat]
    tmp = df[feat_cols].replace([np.inf, -np.inf], np.nan)
    complete = tmp.notna().all(axis=1)
    first = complete.idxmax()
    out = df.loc[first:].reset_index(drop=True)
    out.attrs["warmup_dropped"] = int(first)
    out.attrs["gaps_gt_5min"] = int((df["time"].diff() > pd.Timedelta(minutes=BAR_MINUTES)).sum())
    return out


def add_corrected_utc_independent(df: pd.DataFrame) -> pd.DataFrame:
    """Athens wall-clock → UTC corrected session columns (independent of build_m5_utc...)."""
    out = df.copy()
    naive = pd.to_datetime(out["time"])
    localized = naive.dt.tz_localize(SERVER_TZ, ambiguous="NaT", nonexistent="NaT")
    if localized.isna().any():
        raise RuntimeError("DST-ambiguous timestamps in independent UTC conversion")
    utc = localized.dt.tz_convert("UTC")
    out["corrected_time_utc"] = utc.dt.strftime("%Y-%m-%d %H:%M:%S")
    out["corrected_hour_utc"] = utc.dt.hour.astype(int)
    out["corrected_weekday_utc"] = utc.dt.day_of_week.astype(int)
    for name, (tz, start_hour, end_hour) in SESSIONS.items():
        local_hour = utc.dt.tz_convert(tz).dt.hour
        out[f"corrected_session_{name}"] = ((local_hour >= start_hour) & (local_hour < end_hour)).astype(int)
    out["corrected_session_london_ny_overlap"] = (
        out["corrected_session_london"] & out["corrected_session_new_york"]
    ).astype(int)
    sid = pd.Series(SESSION_IDS["off_hours"], index=out.index)
    sid[out["corrected_session_asia"] == 1] = SESSION_IDS["asia"]
    sid[out["corrected_session_london"] == 1] = SESSION_IDS["london"]
    sid[out["corrected_session_new_york"] == 1] = SESSION_IDS["new_york"]
    sid[out["corrected_session_london_ny_overlap"] == 1] = SESSION_IDS["london_ny_overlap"]
    out["corrected_session_id"] = sid.astype(int)
    return out


def run_feature_recomputation() -> dict[str, Any]:
    raw = load_raw_independent()
    feats = recompute_features_independent(raw)
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    feats_cut = feats[feats["time"] <= cutoff].copy()
    corrected = add_corrected_utc_independent(feats_cut)
    return {
        "holdout_opened": False,
        "raw_rows": int(len(raw)),
        "independent_feature_rows": int(len(feats)),
        "warmup_dropped": int(feats.attrs.get("warmup_dropped", -1)),
        "gaps_gt_5min_full_raw_slice": int(feats.attrs.get("gaps_gt_5min", -1)),
        "independent_rows_le_cutoff": int(len(feats_cut)),
        "existing_feature_rows": int(len(pd.read_csv(FEATURES_PATH, usecols=["time"]))),
        "existing_utc_feature_rows": int(len(pd.read_csv(FEATURES_UTC_PATH, usecols=["time"]))),
        "recomputed_frame": feats,
        "corrected_frame": corrected,
    }
