"""Cost-aware triple-barrier labels for the XAUUSD 5-minute dataset.

Target mapping: BUY = 1, SELL = -1, WAIT = 0 (column `target`).

For feature row t (known at the close of bar t):
  * entry is at the open of bar t+1;
  * the forward window is bars t+1 .. t+12 (12 bars, entry bar included);
  * take-profit = 1.5 x ATR14[t], stop-loss = 1.0 x ATR14[t], measured from the
    cost-adjusted entry price;
  * BUY if the long trade reaches TP strictly before SL, SELL if the short trade
    does; a bar touching both TP and SL counts as SL; everything else is WAIT.
Rows whose window is incomplete or crosses a market gap/closure get no label.

Execution-cost model (MT5 bar prices are bid prices):
  * spread: the bar's recorded spread, floored at 15 points (1 point = $0.01).
    MT5 stores the minimum spread seen during each bar, so the raw value
    understates what a market order actually pays.
  * extra costs: $0.10 per ounce round trip for commission and slippage
    (= $10 per 100-oz lot), charged $0.05 at entry and $0.05 at exit.
  * long:  buy at ask  = open[t+1] + spread[t+1] + 0.05, sell at bid  - 0.05.
  * short: sell at bid = open[t+1] - 0.05,            buy at ask + 0.05,
    where the exit ask uses the floored spread of the bar being tested.

Future OHLC values are used only inside this module to build `target`; the
saved feature columns are exactly the past/current features from
features_m5.py. `time` is kept as a row identifier for chronological splits and
must not be used as a model input.

Chronological splits: label t uses bars t+1 .. t+12, so the last PURGE_BARS = 12
training rows before each boundary must be removed (see purge_before_boundary).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from features_m5 import BAR_MINUTES, load_and_validate

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_PATH = DATA_DIR / "xauusd_m5.csv"
FEATURES_PATH = DATA_DIR / "xauusd_m5_features.csv"
OUTPUT_PATH = DATA_DIR / "xauusd_m5_labeled.csv"

HORIZON_BARS = 12
TP_ATR_MULTIPLE = 1.5
SL_ATR_MULTIPLE = 1.0
ATR_COLUMN = "atr_14"

POINT_SIZE = 0.01
MIN_SPREAD_POINTS = 15
EXTRA_COST_ROUND_TRIP = 0.10
EXTRA_COST_PER_SIDE = EXTRA_COST_ROUND_TRIP / 2

TARGET_COLUMN = "target"
BUY, SELL, WAIT = 1, -1, 0
TARGET_NAMES = {BUY: "BUY", SELL: "SELL", WAIT: "WAIT"}

PURGE_BARS = HORIZON_BARS

# Columns in the features file that are identifiers or raw prices, not model inputs.
NON_FEATURE_COLUMNS = ["time", "time_utc", "open", "high", "low", "close"]


# --------------------------------------------------------------------------
# Loading and alignment
# --------------------------------------------------------------------------

def load_features(path: Path) -> pd.DataFrame:
    features = pd.read_csv(path)
    features["time"] = pd.to_datetime(features["time"], format="%Y-%m-%d %H:%M:%S")
    if not features["time"].is_unique:
        raise ValueError("Feature file contains duplicate timestamps.")
    if not features["time"].is_monotonic_increasing:
        raise ValueError("Feature file is not in chronological order.")
    if features[ATR_COLUMN].isna().any() or (features[ATR_COLUMN] <= 0).any():
        raise ValueError(f"{ATR_COLUMN} must be present and positive on every feature row.")
    return features


def check_point_size(raw: pd.DataFrame) -> None:
    prices = raw[["open", "high", "low", "close"]].to_numpy()
    in_points = prices / POINT_SIZE
    if not np.allclose(in_points, np.round(in_points), atol=1e-6):
        raise ValueError(f"Prices are not quoted in multiples of POINT_SIZE={POINT_SIZE}.")


def align_features_to_raw(features: pd.DataFrame, raw: pd.DataFrame) -> np.ndarray:
    """Return the raw row position of every feature row, matched by timestamp."""
    raw_pos = pd.Series(np.arange(len(raw)), index=raw["time"])
    positions = raw_pos.reindex(features["time"])
    if positions.isna().any():
        missing = features.loc[positions.isna().to_numpy(), "time"].head(5).tolist()
        raise ValueError(f"Feature timestamps not found in raw data, e.g. {missing}")
    positions = positions.to_numpy(dtype=np.int64)

    for col in ("open", "high", "low", "close"):
        if not np.allclose(features[col].to_numpy(), raw[col].to_numpy()[positions]):
            raise ValueError(f"Feature and raw '{col}' disagree at matching timestamps.")
    return positions


# --------------------------------------------------------------------------
# Labeling
# --------------------------------------------------------------------------

def window_status(raw: pd.DataFrame, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flags for rows lacking a full window and rows whose window crosses a gap."""
    n_raw = len(raw)
    step = pd.Timedelta(minutes=BAR_MINUTES)
    contiguous = (raw["time"].diff() == step).to_numpy()  # bar i directly follows bar i-1

    incomplete = positions + HORIZON_BARS > n_raw - 1
    crosses_gap = np.zeros(len(positions), dtype=bool)
    for offset in range(1, HORIZON_BARS + 1):
        k = np.minimum(positions + offset, n_raw - 1)
        crosses_gap |= ~contiguous[k]
    crosses_gap &= ~incomplete
    return incomplete, crosses_gap


def first_touch(hit_by_offset: list[np.ndarray]) -> np.ndarray:
    """1-based offset of the first True per row, or HORIZON_BARS + 1 if never hit."""
    hits = np.column_stack(hit_by_offset)
    return np.where(hits.any(axis=1), hits.argmax(axis=1) + 1, HORIZON_BARS + 1)


def triple_barrier_labels(raw: pd.DataFrame, features: pd.DataFrame, positions: np.ndarray) -> pd.DataFrame:
    n_raw = len(raw)
    open_ = raw["open"].to_numpy()
    high = raw["high"].to_numpy()
    low = raw["low"].to_numpy()
    spread = np.maximum(raw["spread"].to_numpy(), MIN_SPREAD_POINTS) * POINT_SIZE

    atr = features[ATR_COLUMN].to_numpy()
    tp = TP_ATR_MULTIPLE * atr
    sl = SL_ATR_MULTIPLE * atr

    entry = np.minimum(positions + 1, n_raw - 1)
    long_entry = open_[entry] + spread[entry] + EXTRA_COST_PER_SIDE
    short_entry = open_[entry] - EXTRA_COST_PER_SIDE

    long_tp, long_sl, short_tp, short_sl = [], [], [], []
    for offset in range(1, HORIZON_BARS + 1):
        k = np.minimum(positions + offset, n_raw - 1)
        long_exit_high = high[k] - EXTRA_COST_PER_SIDE
        long_exit_low = low[k] - EXTRA_COST_PER_SIDE
        short_exit_low = low[k] + spread[k] + EXTRA_COST_PER_SIDE
        short_exit_high = high[k] + spread[k] + EXTRA_COST_PER_SIDE
        long_tp.append(long_exit_high >= long_entry + tp)
        long_sl.append(long_exit_low <= long_entry - sl)
        short_tp.append(short_exit_low <= short_entry - tp)
        short_sl.append(short_exit_high >= short_entry + sl)

    long_tp_bar, long_sl_bar = first_touch(long_tp), first_touch(long_sl)
    short_tp_bar, short_sl_bar = first_touch(short_tp), first_touch(short_sl)

    # Strict "<" makes a same-bar TP/SL touch count as a stop-loss.
    long_win = long_tp_bar < long_sl_bar
    short_win = short_tp_bar < short_sl_bar

    incomplete, crosses_gap = window_status(raw, positions)
    excluded = incomplete | crosses_gap

    both = long_win & short_win & ~excluded
    if both.any():
        raise AssertionError(f"BUY and SELL are both true on {int(both.sum())} rows.")

    target = np.full(len(positions), WAIT, dtype=np.int64)
    target[long_win] = BUY
    target[short_win] = SELL

    return pd.DataFrame(
        {
            TARGET_COLUMN: target,
            "incomplete_window": incomplete,
            "crosses_gap": crosses_gap,
            "excluded": excluded,
            "same_bar_long": (long_tp_bar == long_sl_bar) & (long_tp_bar <= HORIZON_BARS),
            "same_bar_short": (short_tp_bar == short_sl_bar) & (short_tp_bar <= HORIZON_BARS),
        },
        index=features.index,
    )


# --------------------------------------------------------------------------
# Chronological split helper (not used here; no splitting or training yet)
# --------------------------------------------------------------------------

def purge_before_boundary(train: pd.DataFrame, boundary_time: pd.Timestamp) -> pd.DataFrame:
    """Drop training rows whose label window (t+1 .. t+12) reaches the boundary bar.

    With contiguous windows the last bar used by row t is t + 12 * 5 minutes, so
    exactly the final PURGE_BARS rows before the boundary are removed.
    """
    label_end = train["time"] + pd.Timedelta(minutes=BAR_MINUTES * PURGE_BARS)
    return train[label_end < boundary_time]


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def main() -> None:
    raw = load_and_validate(RAW_PATH)
    check_point_size(raw)
    features = load_features(FEATURES_PATH)
    positions = align_features_to_raw(features, raw)

    labels = triple_barrier_labels(raw, features, positions)

    feature_columns = [c for c in features.columns if c not in NON_FEATURE_COLUMNS]
    labeled = pd.concat([features[["time"] + feature_columns], labels], axis=1)
    labeled = labeled[~labeled["excluded"]]

    same_bar_long = int(labeled["same_bar_long"].sum())
    same_bar_short = int(labeled["same_bar_short"].sum())
    output = labeled[["time"] + feature_columns + [TARGET_COLUMN]].reset_index(drop=True)

    if not output["time"].is_monotonic_increasing or not output["time"].is_unique:
        raise AssertionError("Labeled output is not strictly chronological.")
    if not output[TARGET_COLUMN].isin(TARGET_NAMES).all():
        raise AssertionError("Unexpected target values.")

    to_save = output.copy()
    to_save["time"] = to_save["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    to_save.to_csv(OUTPUT_PATH, index=False)

    print("Labeling configuration")
    print(f"  horizon: {HORIZON_BARS} bars (t+1 .. t+{HORIZON_BARS}), entry at open of t+1")
    print(f"  TP = {TP_ATR_MULTIPLE} x {ATR_COLUMN}, SL = {SL_ATR_MULTIPLE} x {ATR_COLUMN}")
    print(f"  spread floor: {MIN_SPREAD_POINTS} points (${MIN_SPREAD_POINTS * POINT_SIZE:.2f})")
    print(f"  extra cost: ${EXTRA_COST_ROUND_TRIP:.2f} round trip (${EXTRA_COST_PER_SIDE:.2f} per side)")
    print(f"  target mapping: BUY={BUY}, SELL={SELL}, WAIT={WAIT}")
    print(f"  purge for chronological splits: {PURGE_BARS} training rows per boundary")

    print(f"\nFeature rows: {len(features)}")
    print(f"Excluded rows: {int(labels['excluded'].sum())}")
    print(f"  incomplete {HORIZON_BARS}-bar window (end of data): {int(labels['incomplete_window'].sum())}")
    print(f"  window crosses market gap/closure: {int(labels['crosses_gap'].sum())}")
    print(f"Total labels: {len(output)}")
    print(f"Same-bar TP+SL counted as stop-loss: long {same_bar_long}, short {same_bar_short}")
    print(f"BUY/SELL mutually exclusive: True")

    names = output[TARGET_COLUMN].map(TARGET_NAMES)
    counts = names.value_counts().reindex(["BUY", "SELL", "WAIT"], fill_value=0)
    print("\nClass distribution")
    for name, count in counts.items():
        print(f"  {name:<4} {count:>6}  {count / len(output):6.2%}")

    month = output["time"].dt.strftime("%Y-%m")
    monthly = pd.crosstab(month, names).reindex(columns=["BUY", "SELL", "WAIT"], fill_value=0)
    monthly_pct = monthly.div(monthly.sum(axis=1), axis=0).mul(100).round(1)
    monthly_pct.columns = [f"{c}_%" for c in monthly_pct.columns]
    print("\nMonthly class distribution")
    print(pd.concat([monthly, monthly_pct], axis=1).assign(total=monthly.sum(axis=1)).to_string())

    remaining = to_save.isna().sum()
    remaining = remaining[remaining > 0]
    print(f"\nRemaining missing values: {int(remaining.sum())}")
    if not remaining.empty:
        print(remaining.to_string())

    print(f"\nSaved: {OUTPUT_PATH}")
    print(f"Model input columns ({len(feature_columns)}): all columns except 'time' and '{TARGET_COLUMN}'")


if __name__ == "__main__":
    main()
