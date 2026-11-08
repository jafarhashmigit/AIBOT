"""Feature engineering for the XAUUSD 5-minute dataset.

Every feature on row t is computed only from bars <= t (current bar close and
earlier). Nothing is shifted backwards, no centred windows are used, and no
statistics are fitted on the full dataset, so the output is free of look-ahead
bias. Targets/labels are intentionally not created here.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_PATH = DATA_DIR / "xauusd_m5.csv"
OUTPUT_PATH = DATA_DIR / "xauusd_m5_features.csv"

BAR_MINUTES = 5

# Local trading hours of each financial centre, DST-aware: (timezone, start, end).
SESSIONS = {
    "asia": ("Asia/Tokyo", 9, 18),
    "london": ("Europe/London", 8, 17),
    "new_york": ("America/New_York", 8, 17),
}
SESSION_IDS = {"off_hours": 0, "asia": 1, "london": 2, "london_ny_overlap": 3, "new_york": 4}

RAW_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
PRICE_COLUMNS = ["open", "high", "low", "close"]


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def load_and_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    report = {"rows_read": len(df)}

    missing_cols = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    if "real_volume" in df.columns and (df["real_volume"].fillna(0) == 0).all():
        df = df.drop(columns="real_volume")
        report["dropped_real_volume_all_zero"] = True

    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    for col in RAW_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df[RAW_COLUMNS[1:]] = df[RAW_COLUMNS[1:]].replace([np.inf, -np.inf], np.nan)

    # Rows with unparsable timestamps or missing raw values are removed, never imputed.
    missing_mask = df[RAW_COLUMNS].isna().any(axis=1)
    report["rows_with_missing_or_unparsable_values"] = int(missing_mask.sum())
    df = df[~missing_mask]

    off_grid = (df["time"].dt.second != 0) | (df["time"].dt.minute % BAR_MINUTES != 0)
    report["rows_off_5min_grid"] = int(off_grid.sum())
    df = df[~off_grid]

    invalid_ohlc = (
        (df[PRICE_COLUMNS] <= 0).any(axis=1)
        | (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df["tick_volume"] < 0)
        | (df["spread"] < 0)
    )
    report["rows_with_invalid_ohlc_or_volume"] = int(invalid_ohlc.sum())
    df = df[~invalid_ohlc]

    report["was_chronological"] = bool(df["time"].is_monotonic_increasing)
    df = df.sort_values("time", kind="stable")

    exact_dupes = df.duplicated()
    report["exact_duplicate_rows"] = int(exact_dupes.sum())
    df = df[~exact_dupes]

    conflicting_dupes = df["time"].duplicated(keep="first")
    report["conflicting_duplicate_timestamps"] = int(conflicting_dupes.sum())
    df = df[~conflicting_dupes]

    df = df.reset_index(drop=True)

    # Gaps (nights, weekends, holidays) are reported but deliberately left unfilled.
    gaps = df["time"].diff() > pd.Timedelta(minutes=BAR_MINUTES)
    report["gaps_left_unfilled"] = int(gaps.sum())
    report["rows_after_validation"] = len(df)

    print("Validation report")
    for key, value in report.items():
        print(f"  {key}: {value}")
    print()
    return df


# --------------------------------------------------------------------------
# Indicators (all causal: rolling/ewm windows only look backwards)
# --------------------------------------------------------------------------

def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def add_trend_indicators(df: pd.DataFrame) -> None:
    close = df["close"]
    for span in (9, 20, 50):
        ema = close.ewm(span=span, min_periods=span, adjust=False).mean()
        df[f"ema_{span}"] = ema
        df[f"close_to_ema_{span}"] = close / ema - 1
    df["ema_9_20_spread"] = df["ema_9"] / df["ema_20"] - 1
    df["ema_20_50_spread"] = df["ema_20"] / df["ema_50"] - 1

    ema_12 = close.ewm(span=12, min_periods=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, min_periods=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, min_periods=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]


def add_rsi(df: pd.DataFrame, period: int = 14) -> None:
    delta = df["close"].diff()
    avg_gain = wilder_smooth(delta.clip(lower=0), period)
    avg_loss = wilder_smooth(-delta.clip(upper=0), period)
    rsi = 100 - 100 / (1 + avg_gain / avg_loss)
    # avg_loss == 0 means only gains in the window (RSI 100); both zero means flat (RSI 50).
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    df[f"rsi_{period}"] = rsi


def add_bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> None:
    middle = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    band = (upper - lower).replace(0, np.nan)
    df["bb_middle"] = middle
    df["bb_upper"] = upper
    df["bb_lower"] = lower
    df["bb_width"] = band / middle
    df["bb_percent_b"] = ((df["close"] - lower) / band).where(band.notna(), 0.5)
    df.loc[middle.isna(), ["bb_width", "bb_percent_b"]] = np.nan


def add_atr(df: pd.DataFrame, period: int = 14) -> None:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=False)
    df[f"atr_{period}"] = wilder_smooth(true_range, period)
    df[f"atr_{period}_pct"] = df[f"atr_{period}"] / df["close"]


# --------------------------------------------------------------------------
# Price action, returns, volatility and volume features
# --------------------------------------------------------------------------

def add_candle_features(df: pd.DataFrame) -> None:
    candle_top = df[["open", "close"]].max(axis=1)
    candle_bottom = df[["open", "close"]].min(axis=1)
    candle_range = df["high"] - df["low"]

    df["candle_body"] = df["close"] - df["open"]
    df["candle_body_abs"] = df["candle_body"].abs()
    df["upper_wick"] = df["high"] - candle_top
    df["lower_wick"] = candle_bottom - df["low"]
    df["candle_range"] = candle_range

    safe_range = candle_range.replace(0, np.nan)
    for col in ("candle_body_abs", "upper_wick", "lower_wick"):
        df[f"{col}_to_range"] = (df[col] / safe_range).fillna(0.0)
    df["candle_range_to_atr"] = candle_range / df["atr_14"]


def add_return_features(df: pd.DataFrame) -> None:
    close = df["close"]
    df["log_return_1"] = np.log(close / close.shift(1))
    for bars in (1, 3, 6, 12):
        df[f"return_{bars}"] = close.pct_change(bars)

    for bars in (10, 20):
        df[f"momentum_{bars}"] = close - close.shift(bars)
        df[f"roc_{bars}"] = close.pct_change(bars)

    for window in (12, 48):
        df[f"volatility_{window}"] = df["log_return_1"].rolling(window).std()
    df["volatility_ratio_12_48"] = df["volatility_12"] / df["volatility_48"].replace(0, np.nan)


def add_volume_features(df: pd.DataFrame, window: int = 20) -> None:
    volume = df["tick_volume"].astype(float)
    rolling_mean = volume.rolling(window).mean()
    rolling_std = volume.rolling(window).std()

    df["log_tick_volume"] = np.log1p(volume)
    df["tick_volume_change"] = df["log_tick_volume"].diff()
    df[f"tick_volume_ratio_{window}"] = volume / rolling_mean.replace(0, np.nan)
    df[f"tick_volume_zscore_{window}"] = ((volume - rolling_mean) / rolling_std.replace(0, np.nan)).where(
        rolling_std != 0, 0.0
    )
    df.loc[rolling_mean.isna(), f"tick_volume_zscore_{window}"] = np.nan


# --------------------------------------------------------------------------
# Time and session features
# --------------------------------------------------------------------------

def server_time_to_utc(times: pd.Series) -> pd.Series:
    # The CSV stores MT5 Unix timestamps converted with pd.to_datetime(unit="s"),
    # i.e. naive UTC. Attach the UTC zone without shifting the wall-clock time.
    return times.dt.tz_localize("UTC")


def add_time_features(df: pd.DataFrame) -> None:
    time_utc = server_time_to_utc(df["time"])
    df["time_utc"] = time_utc.dt.strftime("%Y-%m-%d %H:%M:%S")

    df["hour"] = df["time"].dt.hour
    df["minute"] = df["time"].dt.minute
    df["weekday"] = df["time"].dt.day_of_week
    df["hour_utc"] = time_utc.dt.hour

    minute_of_day = time_utc.dt.hour * 60 + time_utc.dt.minute
    df["time_of_day_sin"] = np.sin(2 * np.pi * minute_of_day / 1440)
    df["time_of_day_cos"] = np.cos(2 * np.pi * minute_of_day / 1440)
    df["weekday_sin"] = np.sin(2 * np.pi * df["weekday"] / 7)
    df["weekday_cos"] = np.cos(2 * np.pi * df["weekday"] / 7)

    for name, (tz, start_hour, end_hour) in SESSIONS.items():
        local_hour = time_utc.dt.tz_convert(tz).dt.hour
        df[f"session_{name}"] = ((local_hour >= start_hour) & (local_hour < end_hour)).astype(int)
    df["session_london_ny_overlap"] = df["session_london"] & df["session_new_york"]

    session_id = pd.Series(SESSION_IDS["off_hours"], index=df.index)
    session_id[df["session_asia"] == 1] = SESSION_IDS["asia"]
    session_id[df["session_london"] == 1] = SESSION_IDS["london"]
    session_id[df["session_new_york"] == 1] = SESSION_IDS["new_york"]
    session_id[df["session_london_ny_overlap"] == 1] = SESSION_IDS["london_ny_overlap"]
    df["session_id"] = session_id

    # Market closures stay as real gaps; these columns let a model see them.
    gap_minutes = df["time"].diff().dt.total_seconds() / 60
    df["minutes_since_prev_bar"] = gap_minutes
    df["is_after_gap"] = (gap_minutes > BAR_MINUTES).astype(int)


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    add_trend_indicators(df)
    add_rsi(df)
    add_bollinger_bands(df)
    add_atr(df)
    add_candle_features(df)
    add_return_features(df)
    add_volume_features(df)
    add_time_features(df)
    return df


def drop_warmup_rows(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    df[feature_columns] = df[feature_columns].replace([np.inf, -np.inf], np.nan)
    complete = df[feature_columns].notna().all(axis=1)
    if not complete.any():
        raise ValueError("Not enough history to compute every indicator.")

    # Lookback NaNs only exist at the start; drop that warm-up block, never backfill it.
    first_complete = complete.idxmax()
    df = df.loc[first_complete:]

    interior_nan = df[feature_columns].isna().any(axis=1)
    if interior_nan.any():
        print(f"Warning: dropping {int(interior_nan.sum())} rows with NaN after warm-up.")
        df = df[~interior_nan]

    print(f"Dropped {first_complete} warm-up rows needed by indicator lookbacks.")
    return df.reset_index(drop=True)


def main() -> None:
    raw = load_and_validate(INPUT_PATH)
    features = build_features(raw)

    non_feature_columns = {"time", "time_utc"} | set(PRICE_COLUMNS)
    feature_columns = [c for c in features.columns if c not in non_feature_columns]
    features = drop_warmup_rows(features, feature_columns)

    if not features["time"].is_monotonic_increasing:
        raise AssertionError("Output is not in chronological order.")

    output = features.copy()
    output["time"] = output["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(OUTPUT_PATH, index=False)

    print(f"\nSaved: {OUTPUT_PATH}")
    print(f"Records: {len(features)}")
    print(f"Date range (UTC): {features['time_utc'].iloc[0]} -> {features['time_utc'].iloc[-1]}")
    print(f"\nFeature columns ({len(feature_columns)}):")
    for col in feature_columns:
        print(f"  {col}")

    remaining = output.isna().sum()
    remaining = remaining[remaining > 0]
    print(f"\nRemaining missing values: {int(remaining.sum())}")
    if not remaining.empty:
        print(remaining.to_string())


if __name__ == "__main__":
    main()
