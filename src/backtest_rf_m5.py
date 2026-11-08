"""Historical backtest of the RF M5 baseline on the validation period only.

Signals: the model predicts on every validation-period feature row t, whose
features are complete at the close of bar t. This includes rows that labeling
excluded because their future window crossed a gap; signals are never filtered
with future information. A BUY/SELL prediction becomes a market order filled at
the open of bar t+1. Only one position may be open at a time; signals that
arrive while a trade is open are ignored.

Execution rules are imported from label_m5.py so trades are priced exactly as
the labels were built:
  * spread floored at MIN_SPREAD_POINTS (15 points = $0.15), POINT_SIZE = $0.01;
  * EXTRA_COST_PER_SIDE ($0.05) at entry and at exit ($0.10 round trip);
  * long:  entry = open[t+1] + spread[t+1] + 0.05, exits valued at bid - 0.05;
  * short: entry = open[t+1] - 0.05, exits valued at ask + 0.05 using the
    floored spread of the exit bar;
  * TP = 1.5 x atr_14[t], SL = 1.0 x atr_14[t], measured from the entry fill;
  * holding window is bars t+1 .. t+12 (entry bar included); within a bar the
    SL is checked before the TP, so a bar touching both counts as a stop-loss.

Rules the labels did not need, added here:
  * TP and SL fill exactly at their levels, except that a bar opening beyond the
    SL (e.g. after a market gap) fills the SL at that worse open price.
  * A trade still open after 12 bars exits at the close of bar t+12.
  * If bar t+1 is not the next 5-minute slot (market closed), the order is
    rejected and the signal is dropped.
  * A gap that occurs mid-trade is not known in advance, so the position is held
    through it; no swap/overnight financing is charged.
  * Signals whose 12 future bars lie beyond the backtest data boundary (raw bars
    are loaded up to 12 bars past the last validation feature timestamp) cannot
    be simulated and are counted separately. This is a data-availability limit,
    not a trading filter.

P&L is reported in USD per ounce, per 1 lot (100 oz) and in R (1R = SL distance).
Drawdown is measured on closed-trade equity only; floating intratrade drawdown
is not included. Results are diagnostic and not proof of profitability.
"""

from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from features_m5 import BAR_MINUTES, load_and_validate
from label_m5 import (
    ATR_COLUMN,
    BUY,
    EXTRA_COST_PER_SIDE,
    FEATURES_PATH,
    HORIZON_BARS,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    RAW_PATH,
    SELL,
    SL_ATR_MULTIPLE,
    TARGET_NAMES,
    TP_ATR_MULTIPLE,
    align_features_to_raw,
    check_point_size,
    load_features,
)

SRC_DIR = Path(__file__).resolve().parent
MODEL_PATH = SRC_DIR / "models" / "rf_m5_baseline.pkl"
VALIDATION_PATH = SRC_DIR / "data" / "xauusd_m5_validation.csv"
TRADES_PATH = SRC_DIR / "data" / "rf_m5_validation_trades.csv"

OUNCES_PER_LOT = 100
BAR = np.timedelta64(BAR_MINUTES, "m")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FORBIDDEN_INPUTS = {"time", "time_utc", "open", "high", "low", "close", "target"}

SKIP_POSITION_OPEN = "position_already_open"
SKIP_BACKTEST_BOUNDARY = "12_future_bars_unavailable_at_backtest_data_boundary"
SKIP_MARKET_CLOSED = "market_closed_at_entry"

WARNINGS = [
    "Historical MT5 bar spread is the minimum spread seen during each bar and may "
    "underestimate the actual executable spread, even with the 15-point floor.",
    "Slippage is approximated by a fixed $0.05 per side; gapped stop-loss opens are the only "
    "price-dependent slippage modeled. Overnight swap/financing is not modeled.",
    "Results are diagnostic, from one validation period, and are not proof of profitability.",
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_model(path: Path):
    bundle = joblib.load(path)
    model, features = bundle["model"], list(bundle["features"])
    assert len(features) == 30 and len(set(features)) == 30, "expected 30 unique model features"
    assert not FORBIDDEN_INPUTS & set(features), "model features include time/price/target columns"
    assert list(model.feature_names_in_) == features, "saved feature order differs from the fitted model"
    return model, features


def load_validation_period(path: Path) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    val = pd.read_csv(path)
    val["time"] = pd.to_datetime(val["time"], format=TIME_FORMAT)
    assert val["time"].is_monotonic_increasing and val["time"].is_unique, "validation not chronological"
    return val, val["time"].iloc[0], val["time"].iloc[-1]


def load_market(start: pd.Timestamp, end: pd.Timestamp):
    """Raw bars and feature rows restricted to the validation period.

    Raw bars stop at end + 12 bars: the last validation signal's window ends
    there, inside the purged gap that split_m5.py leaves before the test split.
    """
    raw = load_and_validate(RAW_PATH)
    check_point_size(raw)
    bar_limit = end + HORIZON_BARS * pd.Timedelta(minutes=BAR_MINUTES)
    raw = raw[(raw["time"] >= start) & (raw["time"] <= bar_limit)].reset_index(drop=True)

    features = load_features(FEATURES_PATH)
    features = features[(features["time"] >= start) & (features["time"] <= end)].reset_index(drop=True)
    positions = align_features_to_raw(features, raw)
    return raw, features, positions, bar_limit


def check_against_validation(features: pd.DataFrame, val: pd.DataFrame, model_features: list[str]) -> None:
    matched = features.set_index("time").reindex(val["time"])
    assert matched[model_features].notna().all().all(), "validation rows missing from features file"
    assert np.allclose(matched[model_features].to_numpy(float), val[model_features].to_numpy(float)), \
        "feature values differ from the validation split"


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def generate_signals(model, features: pd.DataFrame, model_features: list[str]) -> np.ndarray:
    X = features[model_features]
    assert list(X.columns) == model_features, "feature order mismatch"
    assert np.isfinite(X.to_numpy(float)).all(), "missing or infinite feature values"
    signals = model.predict(X)

    # Each prediction may depend only on its own (closed-bar) row: dropping all
    # later rows must leave earlier signals unchanged.
    half = len(X) // 2
    assert (model.predict(X.iloc[:half]) == signals[:half]).all(), "signals depend on later rows"
    return signals


def count_boundary_signals(signals: np.ndarray, positions: np.ndarray, n_raw: int) -> int:
    """BUY/SELL signals whose 12 future bars lie beyond the backtest data boundary."""
    actionable = np.isin(signals, (BUY, SELL))
    beyond = positions + HORIZON_BARS > n_raw - 1
    return int((actionable & beyond).sum())


# --------------------------------------------------------------------------
# Trade simulation
# --------------------------------------------------------------------------

def simulate_trade(m: dict, side: int, signal_pos: int, atr: float) -> dict:
    signal_time = m["time"][signal_pos]
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError(f"Invalid {ATR_COLUMN} at signal {signal_time}: {atr!r} (must be finite and > 0).")

    entry_pos = signal_pos + 1
    last_pos = entry_pos + HORIZON_BARS - 1
    tp_dist, sl_dist = TP_ATR_MULTIPLE * atr, SL_ATR_MULTIPLE * atr
    for name, dist in (("TP", tp_dist), ("SL", sl_dist)):
        if not np.isfinite(dist) or dist <= 0:
            raise ValueError(f"Invalid {name} distance at signal {signal_time}: {dist!r} (must be finite and > 0).")

    if side == BUY:
        entry_fill = m["open"][entry_pos] + m["spread"][entry_pos] + EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill + tp_dist, entry_fill - sl_dist
    else:
        entry_fill = m["open"][entry_pos] - EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill - tp_dist, entry_fill + sl_dist

    exit_fill, reason, gap_fill = None, "TIME", False
    for k in range(entry_pos, last_pos + 1):
        if side == BUY:  # long exits sell at bid, minus exit cost
            open_px = m["open"][k] - EXTRA_COST_PER_SIDE
            low_px = m["low"][k] - EXTRA_COST_PER_SIDE
            high_px = m["high"][k] - EXTRA_COST_PER_SIDE
            if k > entry_pos and open_px <= sl_level:
                exit_fill, reason, gap_fill = open_px, "SL", True
            elif low_px <= sl_level:
                exit_fill, reason = sl_level, "SL"
            elif high_px >= tp_level:
                exit_fill, reason = tp_level, "TP"
        else:  # short exits buy at ask, plus exit cost
            ask_cost = m["spread"][k] + EXTRA_COST_PER_SIDE
            open_px = m["open"][k] + ask_cost
            high_px = m["high"][k] + ask_cost
            low_px = m["low"][k] + ask_cost
            if k > entry_pos and open_px >= sl_level:
                exit_fill, reason, gap_fill = open_px, "SL", True
            elif high_px >= sl_level:
                exit_fill, reason = sl_level, "SL"
            elif low_px <= tp_level:
                exit_fill, reason = tp_level, "TP"
        if exit_fill is not None:
            exit_pos = k
            break
    else:
        exit_pos = last_pos
        if side == BUY:
            exit_fill = m["close"][last_pos] - EXTRA_COST_PER_SIDE
        else:
            exit_fill = m["close"][last_pos] + m["spread"][last_pos] + EXTRA_COST_PER_SIDE

    net = exit_fill - entry_fill if side == BUY else entry_fill - exit_fill
    spread_paid = m["spread"][entry_pos] if side == BUY else m["spread"][exit_pos]
    costs = spread_paid + 2 * EXTRA_COST_PER_SIDE
    steps = np.diff(m["time"][entry_pos : exit_pos + 1])

    return {
        "side": TARGET_NAMES[side],
        "signal_pos": signal_pos,
        "entry_pos": entry_pos,
        "exit_pos": exit_pos,
        "signal_time": m["time"][signal_pos],
        "entry_time": m["time"][entry_pos],
        "exit_time": m["time"][exit_pos],
        "bars_held": exit_pos - entry_pos + 1,
        "exit_reason": reason,
        "sl_gap_fill": gap_fill,
        "crossed_gap": bool((steps != BAR).any()),
        "atr": atr,
        "tp_distance": tp_dist,
        "sl_distance": sl_dist,
        "entry_open": m["open"][entry_pos],
        "entry_fill": entry_fill,
        "tp_level": tp_level,
        "sl_level": sl_level,
        "exit_fill": exit_fill,
        "gross_pnl": net + costs,
        "costs": costs,
        "net_pnl": net,
        "net_pnl_r": net / sl_dist,
    }


def run_backtest(raw: pd.DataFrame, features: pd.DataFrame, positions: np.ndarray, signals: np.ndarray):
    m = {
        "time": raw["time"].to_numpy(),
        "open": raw["open"].to_numpy(),
        "high": raw["high"].to_numpy(),
        "low": raw["low"].to_numpy(),
        "close": raw["close"].to_numpy(),
        "spread": np.maximum(raw["spread"].to_numpy(), MIN_SPREAD_POINTS) * POINT_SIZE,
    }
    feature_times = features["time"].to_numpy()
    atr = features[ATR_COLUMN].to_numpy()
    n_raw = len(raw)

    trades, skipped = [], Counter()
    last_exit_pos = -1
    for i, side in enumerate(signals):
        if side not in (BUY, SELL):
            continue
        signal_pos = int(positions[i])
        assert m["time"][signal_pos] == feature_times[i], "signal not tied to its own closed bar"

        if signal_pos < last_exit_pos:
            skipped[SKIP_POSITION_OPEN] += 1
            continue
        entry_pos = signal_pos + 1
        if entry_pos + HORIZON_BARS - 1 > n_raw - 1:
            skipped[SKIP_BACKTEST_BOUNDARY] += 1
            continue
        if m["time"][entry_pos] - m["time"][signal_pos] != BAR:
            skipped[SKIP_MARKET_CLOSED] += 1
            continue

        trade = simulate_trade(m, int(side), signal_pos, float(atr[i]))
        assert trade["entry_time"] > trade["signal_time"], "entry must be after the signal bar closes"
        assert trade["entry_pos"] == signal_pos + 1, "entry must be the next bar's open"
        assert trade["entry_pos"] > last_exit_pos, "overlapping positions"
        assert trade["bars_held"] <= HORIZON_BARS, "holding period exceeded"
        trades.append(trade)
        last_exit_pos = trade["exit_pos"]

    trades = pd.DataFrame(trades)
    if not trades.empty:
        assert (trades["entry_pos"].iloc[1:].to_numpy() > trades["exit_pos"].iloc[:-1].to_numpy()).all(), \
            "a trade opened before the previous one closed"
        assert trades["exit_pos"].max() <= n_raw - 1
    return trades, skipped


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def closed_trade_max_drawdown(pnl: pd.Series) -> float:
    """Peak-to-trough decline of cumulative closed-trade P&L (no floating P&L)."""
    equity = pnl.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return float((peak - equity).max()) if len(equity) else 0.0


def print_warnings() -> None:
    print("\nWARNINGS")
    for warning in WARNINGS:
        print(f"  - {warning}")


def report(trades: pd.DataFrame, signals: np.ndarray, skipped: Counter, boundary_signals: int,
           start, end, bar_limit) -> None:
    print(f"\nValidation period: {start} -> {end} (bars used up to {bar_limit})")
    counts = pd.Series(signals).map(TARGET_NAMES).value_counts()
    print("Model signals: " + ", ".join(f"{k} {int(counts.get(k, 0))}" for k in ("BUY", "SELL", "WAIT")))
    print(f"  skipped, position already open: {skipped[SKIP_POSITION_OPEN]}")
    print(f"  skipped, market closed at next bar (order rejected): {skipped[SKIP_MARKET_CLOSED]}")
    print("12 future observed bars unavailable at the backtest data boundary:")
    print(f"  BUY/SELL signals affected: {boundary_signals}")
    print(f"  trades not opened for this reason (no position open at the time): {skipped[SKIP_BACKTEST_BOUNDARY]}")

    if trades.empty:
        print("No trades.")
        print_warnings()
        return

    net, gross, costs = trades["net_pnl"], trades["gross_pnl"], trades["costs"]
    assert np.isclose(gross.sum() - costs.sum(), net.sum()), "gross - costs != net"
    profits, losses = net[net > 0].sum(), -net[net < 0].sum()
    profit_factor = profits / losses if losses > 0 else float("inf")
    time_exits = trades["exit_reason"] == "TIME"
    tp_sl_reference = SL_ATR_MULTIPLE / (TP_ATR_MULTIPLE + SL_ATR_MULTIPLE)

    print(f"\nTotal trades: {len(trades)}  (BUY {int((trades.side == 'BUY').sum())}, "
          f"SELL {int((trades.side == 'SELL').sum())})")
    print(f"Wins (TP): {int((trades.exit_reason == 'TP').sum())}")
    print(f"Losses (SL): {int((trades.exit_reason == 'SL').sum())}  "
          f"(of which SL filled at a gapped open: {int(trades.sl_gap_fill.sum())})")
    print(f"Time exits: {int(time_exits.sum())}  "
          f"(net positive {int((time_exits & (net > 0)).sum())}, net negative {int((time_exits & (net <= 0)).sum())})")
    print(f"Win rate (net P&L > 0): {(net > 0).mean():.2%}")
    print(f"TP hit rate: {(trades.exit_reason == 'TP').mean():.2%}")
    print(f"Theoretical TP/SL reference (excluding time exits and gap effects): {tp_sl_reference:.2%}")
    print("  This is the TP rate at which TP-only and SL-only trades would net zero; it is not the")
    print("  strategy's actual break-even rate, which depends on time exits, costs and gap fills.")
    print(f"Trades held through a market gap: {int(trades.crossed_gap.sum())}")

    dd = closed_trade_max_drawdown(net)
    print("\nP&L                                    $/oz     $/1 lot")
    for name, value in (("Gross P&L", gross.sum()), ("Total costs", costs.sum()), ("Net P&L", net.sum()),
                        ("Closed-trade equity max drawdown", dd)):
        print(f"  {name:<34} {value:9.2f}  {value * OUNCES_PER_LOT:10.2f}")
    print(f"  {'Average trade P&L':<34} {net.mean():9.4f}  {net.mean() * OUNCES_PER_LOT:10.2f}")
    print("  Note: drawdown is measured on closed-trade equity only and does not include")
    print("  intratrade floating drawdown.")
    print(f"Profit factor: {profit_factor:.3f}")
    print(f"Net P&L in R: total {trades.net_pnl_r.sum():.2f}R, average {trades.net_pnl_r.mean():.4f}R, "
          f"closed-trade equity max drawdown {closed_trade_max_drawdown(trades.net_pnl_r):.2f}R")

    print("\nBy side:")
    by_side = trades.groupby("side").agg(
        trades=("net_pnl", "size"),
        tp=("exit_reason", lambda s: int((s == "TP").sum())),
        sl=("exit_reason", lambda s: int((s == "SL").sum())),
        time=("exit_reason", lambda s: int((s == "TIME").sum())),
        win_rate=("net_pnl", lambda s: round((s > 0).mean(), 4)),
        net_pnl=("net_pnl", "sum"),
        avg_r=("net_pnl_r", "mean"),
    )
    print(by_side.round(4).to_string())
    print_warnings()


def save_trades(trades: pd.DataFrame, path: Path) -> None:
    out = trades.drop(columns=["signal_pos", "entry_pos", "exit_pos"]).copy()
    out.insert(0, "trade_id", np.arange(1, len(out) + 1))
    out["net_pnl_per_lot"] = out["net_pnl"] * OUNCES_PER_LOT
    out["cum_net_pnl"] = out["net_pnl"].cumsum()
    for col in ("signal_time", "entry_time", "exit_time"):
        out[col] = pd.to_datetime(out[col]).dt.strftime(TIME_FORMAT)
    out.to_csv(path, index=False)
    print(f"\nSaved trades: {path}")


def main() -> None:
    model, model_features = load_model(MODEL_PATH)
    val, start, end = load_validation_period(VALIDATION_PATH)
    raw, features, positions, bar_limit = load_market(start, end)
    check_against_validation(features, val, model_features)

    signals = generate_signals(model, features, model_features)
    boundary_signals = count_boundary_signals(signals, positions, len(raw))
    trades, skipped = run_backtest(raw, features, positions, signals)
    report(trades, signals, skipped, boundary_signals, start, end, bar_limit)
    if not trades.empty:
        save_trades(trades, TRADES_PATH)


if __name__ == "__main__":
    main()
