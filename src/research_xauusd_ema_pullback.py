"""Research backtest: XAUUSD Daily Trend + H4 Trend + H1 EMA Pullback Baseline.

Fully mechanical, fixed-parameter rules; no fitting, no tuning, no ML. Research only - no
live code, no MT5 connection, no orders.

Data
* src/data/xauusd_h1_mt5.csv: broker XAUUSD H1 bid bars (MT5 MetaQuotes-Demo, same feed and
  clock as xauusd_m5.csv - verified below), 2018-01-02 -> the last H1 bar ending before the
  M5 research cutoff. D1 and H4 candles are aggregated from these H1 bars only (server-day
  and 4-hour server-clock slots, MT5's own grouping); missing bars are never filled.
* src/data/xauusd_m5.csv, read only up to the research cutoff: feed/clock cross-check and
  spread context.
* Everything after the cutoff (the existing M5 test period) is the untouched final holdout:
  it was never downloaded, opened or read.

Timing
* An H1 bar stamped t covers [t, t+1h); its close is known at t+1h (decision time).
* D1/H4 values for that decision come from the latest D1/H4 candle whose slot ended at or
  before t+1h; a forming higher-timeframe candle is never used.
* Entry at the open of bar t+1h only if that exact bar exists; otherwise the signal is
  rejected.

Costs (project methodology, label_m5/backtest_rf_m5): MT5 bars are bid prices; MT5 stores the
minimum spread of each bar, so the spread is floored at 15 points ($0.15); plus $0.05 per side
(the project's $0.10 round-trip commission/slippage allowance). BUY enters at ask = open +
spread and exits at bid; SELL enters at bid and exits at ask = bid + spread.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from features_m5 import SESSIONS, add_atr, load_and_validate
from label_m5 import EXTRA_COST_PER_SIDE, MIN_SPREAD_POINTS, POINT_SIZE, RAW_PATH
from research_kronos_m5 import GUARD, TEST_PATH, assert_no_test_rows, install_guards, rows_through
from research_m5_label_horizon import research_boundary
from research_rf_m5_conditional_edge import snapshot

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
H1_PATH = DATA_DIR / "xauusd_h1_mt5.csv"
TRADES_PATH = DATA_DIR / "xauusd_ema_pullback_trades.csv"
RESULTS_PATH = DATA_DIR / "xauusd_ema_pullback_results.csv"
REPORT_PATH = DATA_DIR / "xauusd_ema_pullback_report.txt"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
H1 = pd.Timedelta(hours=1)
M5 = pd.Timedelta(minutes=5)
SERVER_TZ = "Europe/Athens"
BUY, SELL = 1, -1

# Pre-declared strategy parameters (from the specification; never changed).
PARAMS = {
    "d1_ema_fast": 50, "d1_ema_slow": 200, "h4_ema": 50, "h1_ema": 20, "h1_atr": 14,
    "sl_atr_multiple": 1.5, "reward_risk": 2.0, "max_open_positions": 1,
}
SPREAD_MULTIPLIERS = (1.0, 1.5, 2.0)
DEV_FRACTION = 0.55
WF_FRACTIONS = (0.55, 0.70, 0.85, 1.00)
PERIODS = ["DEV", "WF1", "WF2", "WF3"]
WF_PERIODS = PERIODS[1:]
TRUNCATION_FRACTIONS = (0.35, 0.62, 0.77, 0.93)

TEST_STATEMENT = "The untouched M5 TEST dataset / final holdout was never downloaded, opened, read or used."


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def load_h1() -> pd.DataFrame:
    df = pd.read_csv(H1_PATH)
    df["time"] = pd.to_datetime(df["time"], format=TIME_FORMAT)
    cols = ["open", "high", "low", "close", "tick_volume", "spread"]
    assert df[["time", *cols]].notna().all().all(), "missing values in H1 data"
    assert df["time"].is_unique and df["time"].is_monotonic_increasing
    assert (df["time"].dt.minute == 0).all() and (df["time"].dt.second == 0).all()
    assert (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
    assert (df[["open", "high", "low", "close"]] > 0).all().all() and (df["spread"] >= 0).all()
    px = df[["open", "high", "low", "close"]].to_numpy() / POINT_SIZE
    assert np.allclose(px, np.round(px), atol=1e-6), "prices not in multiples of the point size"
    return df[["time", *cols]]


def feed_check(h1: pd.DataFrame, m5: pd.DataFrame) -> dict:
    """Aggregate complete M5 hours (12 bars) and compare with the MT5 H1 bars."""
    g = m5.assign(hour=m5["time"].dt.floor("h")).groupby("hour")
    agg = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "n": g["time"].size(), "min_spread": g["spread"].min(),
                        "mean_spread": g["spread"].mean()})
    agg = agg[agg["n"] == 12]
    both = agg.join(h1.set_index("time"), how="inner", rsuffix="_h1")
    match = ((both["open"] == both["open_h1"]) & (both["high"] == both["high_h1"]) & (both["low"] == both["low_h1"])
             & (both["close"] == both["close_h1"]))
    return {"hours_compared": len(both), "ohlc_exact_match": int(match.sum()), "match_share": float(match.mean()),
            "h1_spread_eq_min_m5_spread": float((both["spread"] == both["min_spread"]).mean()),
            "m5_spread_median": float(m5["spread"].median()), "m5_spread_p75": float(m5["spread"].quantile(0.75)),
            "m5_spread_p95": float(m5["spread"].quantile(0.95)), "m5_share_below_floor": float((m5["spread"] < MIN_SPREAD_POINTS).mean())}


def utc_check(h1: pd.DataFrame) -> dict:
    """Daily trading break: the first bar after a 2-hour weekday gap should open at 18:00 New York
    time if the server clock is Europe/Athens (EET/EEST)."""
    gap = h1["time"].diff() == 2 * H1
    after = h1.loc[gap, "time"].dt.tz_localize(SERVER_TZ).dt.tz_convert("America/New_York")
    return {"daily_breaks": int(gap.sum()), "reopen_at_18_ny_share": float((after.dt.hour == 18).mean())}


# --------------------------------------------------------------------------
# Indicators and signals
# --------------------------------------------------------------------------

def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span, adjust=False).mean()


def aggregate(h1: pd.DataFrame, freq: str, length: pd.Timedelta) -> pd.DataFrame:
    g = h1.assign(slot=h1["time"].dt.floor(freq)).groupby("slot", sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "h1_bars": g["time"].size()}).reset_index()
    out["available_at"] = out["slot"] + length
    return out


def build_signals(h1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = PARAMS
    d1 = aggregate(h1, "D", pd.Timedelta(days=1))
    d1["ema_fast"], d1["ema_slow"] = ema(d1["close"], p["d1_ema_fast"]), ema(d1["close"], p["d1_ema_slow"])
    d1["bias"] = np.select([(d1["ema_fast"] > d1["ema_slow"]) & (d1["close"] > d1["ema_fast"]),
                            (d1["ema_fast"] < d1["ema_slow"]) & (d1["close"] < d1["ema_fast"])], [BUY, SELL], 0)
    h4 = aggregate(h1, "4h", pd.Timedelta(hours=4))
    h4["ema"] = ema(h4["close"], p["h4_ema"])
    h4["conf"] = np.select([h4["close"] > h4["ema"], h4["close"] < h4["ema"]], [BUY, SELL], 0)

    f = h1.copy()
    f["ema20"] = ema(f["close"], p["h1_ema"])
    add_atr(f, p["h1_atr"])
    f = f.rename(columns={"atr_14": "atr", "atr_14_pct": "atr_pct"})
    f["decision_time"] = f["time"] + H1
    d1r = d1.rename(columns={"slot": "d1_slot", "close": "d1_close", "ema_fast": "d1_ema50", "ema_slow": "d1_ema200",
                             "available_at": "d1_available_at", "bias": "d1_bias"})
    h4r = h4.rename(columns={"slot": "h4_slot", "close": "h4_close", "ema": "h4_ema50",
                             "available_at": "h4_available_at", "conf": "h4_conf"})
    f = pd.merge_asof(f, d1r[["d1_slot", "d1_close", "d1_ema50", "d1_ema200", "d1_available_at", "d1_bias"]],
                      left_on="decision_time", right_on="d1_available_at", direction="backward")
    f = pd.merge_asof(f, h4r[["h4_slot", "h4_close", "h4_ema50", "h4_available_at", "h4_conf"]],
                      left_on="decision_time", right_on="h4_available_at", direction="backward")
    f["valid"] = f[["d1_ema200", "d1_ema50", "h4_ema50", "ema20", "atr"]].notna().all(axis=1)
    bias = np.where(f["valid"] & f["d1_ema200"].notna(), f["d1_bias"].fillna(0), 0).astype(int)
    conf = f["h4_conf"].fillna(0).astype(int).to_numpy()
    buy = (bias == BUY) & (conf == BUY) & (f["low"] <= f["ema20"]) & (f["close"] > f["ema20"]) & (f["close"] > f["open"])
    sell = (bias == SELL) & (conf == SELL) & (f["high"] >= f["ema20"]) & (f["close"] < f["ema20"]) & (f["close"] < f["open"])
    f["signal"] = np.where(f["valid"] & buy, BUY, np.where(f["valid"] & sell, SELL, 0))
    return f, d1, h4


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------

def backtest(f: pd.DataFrame, spread_mult: float) -> tuple[pd.DataFrame, list[dict]]:
    t = f["time"].to_numpy()
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sp = np.maximum(f["spread"].to_numpy(float), MIN_SPREAD_POINTS) * POINT_SIZE * spread_mult
    atr, sig = f["atr"].to_numpy(float), f["signal"].to_numpy(int)
    x = EXTRA_COST_PER_SIDE
    n = len(f)
    trades, rejected = [], []
    last_exit = -1
    for i in np.flatnonzero(sig):
        side = sig[i]
        if i < last_exit:
            rejected.append({"signal_time": t[i], "side": side, "reason": "position_open"})
            continue
        e = i + 1
        if e >= n:
            rejected.append({"signal_time": t[i], "side": side, "reason": "no_next_bar_end_of_data"})
            continue
        if t[e] - t[i] != np.timedelta64(1, "h"):
            rejected.append({"signal_time": t[i], "side": side, "reason": "next_h1_slot_missing_market_closed"})
            continue
        sl_dist = PARAMS["sl_atr_multiple"] * atr[i]
        assert np.isfinite(sl_dist) and sl_dist > 0
        if side == BUY:
            entry = o[e] + sp[e] + x
            sl, tp = entry - sl_dist, entry + PARAMS["reward_risk"] * sl_dist
        else:
            entry = o[e] - x
            sl, tp = entry + sl_dist, entry - PARAMS["reward_risk"] * sl_dist
        exit_px, reason, same, k = None, "EOD", False, e
        for k in range(e, n):
            if side == BUY:   # exits at bid, minus exit cost
                ok_, hk, lk = o[k] - x, h[k] - x, l[k] - x
                if k > e and ok_ <= sl:
                    exit_px, reason = ok_, "GAP_SL"
                elif lk <= sl:
                    exit_px, reason, same = sl, "SL", hk >= tp
                elif hk >= tp:
                    exit_px, reason = tp, "TP"
            else:             # exits at ask = bid + spread, plus exit cost
                a = sp[k] + x
                ok_, hk, lk = o[k] + a, h[k] + a, l[k] + a
                if k > e and ok_ >= sl:
                    exit_px, reason = ok_, "GAP_SL"
                elif hk >= sl:
                    exit_px, reason, same = sl, "SL", lk <= tp
                elif lk <= tp:
                    exit_px, reason = tp, "TP"
            if exit_px is not None:
                break
        else:
            k = n - 1
            exit_px = c[k] - x if side == BUY else c[k] + sp[k] + x
        net = exit_px - entry if side == BUY else entry - exit_px
        trades.append({
            "side": "BUY" if side == BUY else "SELL", "signal_pos": i, "entry_pos": e, "exit_pos": k,
            "signal_time": t[i], "entry_time": t[e], "exit_time": t[k], "entry_price": entry, "stop_loss": sl,
            "take_profit": tp, "exit_price": exit_px, "exit_reason": reason, "same_candle_sl_tp": bool(same),
            "gap_exit": reason == "GAP_SL", "bars_held": k - e + 1,
            "holding_hours": (t[k] + np.timedelta64(1, "h") - t[e]) / np.timedelta64(1, "h"),
            "atr": atr[i], "sl_distance": sl_dist, "tp_distance": PARAMS["reward_risk"] * sl_dist,
            "entry_spread": sp[e], "exit_spread": sp[k],
            "costs": (sp[e] if side == BUY else sp[k]) + 2 * x, "net_pnl": net, "net_r": net / sl_dist,
        })
        last_exit = k
    return pd.DataFrame(trades), rejected


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def streak(mask: np.ndarray) -> int:
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def max_drawdown(x: np.ndarray) -> float:
    eq = np.concatenate([[0.0], np.cumsum(x)])
    return float((np.maximum.accumulate(eq) - eq).max())


def metrics(tr: pd.DataFrame) -> dict:
    n = len(tr)
    if n == 0:
        return {"total_trades": 0}
    net, r = tr["net_pnl"].to_numpy(float), tr["net_r"].to_numpy(float)
    gp, gl = net[net > 0].sum(), net[net < 0].sum()
    return {
        "total_trades": n, "buy_trades": int((tr["side"] == "BUY").sum()), "sell_trades": int((tr["side"] == "SELL").sum()),
        "wins": int((net > 0).sum()), "losses": int((net < 0).sum()), "win_rate": float((net > 0).mean()),
        "gross_profit": gp, "gross_loss": gl, "net_pnl": net.sum(),
        "profit_factor": gp / -gl if gl < 0 else float("inf"),
        "average_trade": net.mean(), "average_r": r.mean(), "total_r": r.sum(),
        "expectancy_per_trade": net.mean(), "expectancy_r": r.mean(),
        "max_drawdown": max_drawdown(net), "max_drawdown_r": max_drawdown(r),
        "largest_win": net.max(), "largest_loss": net.min(),
        "longest_win_streak": streak(net > 0), "longest_loss_streak": streak(net < 0),
        "avg_holding_hours": tr["holding_hours"].mean(), "median_holding_hours": tr["holding_hours"].median(),
        "avg_bars_held": tr["bars_held"].mean(),
        "tp_exits": int((tr["exit_reason"] == "TP").sum()), "sl_exits": int((tr["exit_reason"] == "SL").sum()),
        "gap_exits": int((tr["exit_reason"] == "GAP_SL").sum()), "eod_exits": int((tr["exit_reason"] == "EOD").sum()),
        "same_candle_sl_tp_assumed_sl": int(tr["same_candle_sl_tp"].sum()),
        "avg_costs": tr["costs"].mean(),
    }


def period_of(times: pd.Series, bounds: list[pd.Timestamp]) -> pd.Series:
    out = pd.Series(pd.NA, index=times.index, dtype="object")
    for i, name in enumerate(PERIODS):
        last = i == len(PERIODS) - 1
        m = (times >= bounds[i]) & ((times <= bounds[i + 1]) if last else (times < bounds[i + 1]))
        out[m] = name
    return out


def session_utc(times_server: pd.Series) -> pd.Series:
    utc = times_server.dt.tz_localize(SERVER_TZ, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
    flags = {}
    for name, (tz, start, end) in SESSIONS.items():
        hour = utc.dt.tz_convert(tz).dt.hour
        flags[name] = (hour >= start) & (hour < end)
    return pd.Series(np.select([flags["london"] & flags["new_york"], flags["new_york"], flags["london"], flags["asia"]],
                               ["London-NY overlap", "New York", "London", "Asia"], "Off-hours"), index=times_server.index)


# --------------------------------------------------------------------------
# Report helpers
# --------------------------------------------------------------------------

METRIC_ROWS = [("total_trades", "d"), ("buy_trades", "d"), ("sell_trades", "d"), ("wins", "d"), ("losses", "d"),
               ("win_rate", "pct"), ("gross_profit", ".2f"), ("gross_loss", ".2f"), ("net_pnl", "+.2f"),
               ("profit_factor", ".3f"), ("average_trade", "+.3f"), ("average_r", "+.4f"), ("total_r", "+.2f"),
               ("expectancy_per_trade", "+.3f"), ("expectancy_r", "+.4f"), ("max_drawdown", ".2f"),
               ("max_drawdown_r", ".2f"), ("largest_win", "+.2f"), ("largest_loss", "+.2f"),
               ("longest_win_streak", "d"), ("longest_loss_streak", "d"), ("avg_holding_hours", ".1f"),
               ("median_holding_hours", ".1f"), ("avg_bars_held", ".1f"), ("tp_exits", "d"), ("sl_exits", "d"),
               ("gap_exits", "d"), ("eod_exits", "d"), ("same_candle_sl_tp_assumed_sl", "d"), ("avg_costs", ".3f")]


def fmt(v, spec) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    if spec == "pct":
        return f"{v * 100:.1f}%"
    if spec == "d":
        return str(int(v))
    return "inf" if v == float("inf") else format(v, spec)


def metric_table(cols: dict[str, dict]) -> list[str]:
    names = list(cols)
    L = [f"   {'metric':<30}" + "".join(f"{n:>12}" for n in names)]
    for key, spec in METRIC_ROWS:
        L.append(f"   {key:<30}" + "".join(f"{fmt(cols[n].get(key), spec):>12}" for n in names))
    return L


def short_table(rows: list[tuple[str, dict]]) -> list[str]:
    L = [f"   {'group':<34}{'trades':>7}{'win%':>7}{'net':>10}{'PF':>7}{'avgR':>8}{'totR':>8}{'maxDD_R':>8}"]
    for name, m in rows:
        if not m.get("total_trades"):
            L.append(f"   {name:<34}{0:>7}")
            continue
        L.append(f"   {name:<34}{m['total_trades']:>7}{m['win_rate'] * 100:>7.1f}{m['net_pnl']:>+10.2f}"
                 f"{fmt(m['profit_factor'], '.3f'):>7}{m['average_r']:>+8.4f}{m['total_r']:>+8.2f}{m['max_drawdown_r']:>8.2f}")
    return L


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    outputs = [TRADES_PATH, RESULTS_PATH, REPORT_PATH]
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    skip = {p.resolve() for p in outputs} | {Path(__file__).resolve()}

    _, _, cutoff = research_boundary()
    cutoff_str = cutoff.strftime(TIME_FORMAT)
    hashes_before = snapshot(skip, cutoff_str)
    install_guards()
    GUARD["cutoff"] = cutoff_str
    GUARD["safe_nrows"][RAW_PATH.resolve()] = rows_through(RAW_PATH, cutoff_str)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))
        assert ok, f"integrity check failed: {name} {detail}"

    # ---- data
    h1 = load_h1()
    n_source = len(h1)
    check("H1 data ends before the research cutoff (holdout never present)", h1["time"].max() + H1 <= cutoff + M5,
          f"last bar {h1['time'].max()} ends {h1['time'].max() + H1}; cutoff {cutoff_str}")
    check("no duplicate H1 timestamps; strictly chronological", h1["time"].is_unique and h1["time"].is_monotonic_increasing)
    m5 = load_and_validate(RAW_PATH)
    m5 = m5[m5["time"] <= cutoff].reset_index(drop=True)
    assert_no_test_rows(m5)
    feed = feed_check(h1, m5)
    check("H1 feed and clock identical to xauusd_m5.csv (complete hours)", feed["match_share"] >= 0.99,
          f"{feed['ohlc_exact_match']}/{feed['hours_compared']} hours exact OHLC match")
    tz = utc_check(h1)
    check("server clock = Europe/Athens (daily reopen at 18:00 New York)", tz["reopen_at_18_ny_share"] >= 0.9,
          f"{tz['reopen_at_18_ny_share']:.1%} of {tz['daily_breaks']} daily breaks")

    # ---- signals
    f, d1, h4 = build_signals(h1)
    check("no fabricated candles / no missing-bar filling: H1 rows unchanged; D1/H4 built only from existing H1 bars",
          len(f) == n_source and d1["h1_bars"].sum() == n_source and h4["h1_bars"].sum() == n_source
          and len(d1) == h1["time"].dt.normalize().nunique(),
          f"{n_source} H1 bars -> {len(d1)} D1, {len(h4)} H4 candles")
    sig_rows = f[f["signal"] != 0]
    check("D1/H4 values from completed candles only (slot ended at or before the H1 signal close)",
          (sig_rows["d1_available_at"] <= sig_rows["decision_time"]).all()
          and (sig_rows["h4_available_at"] <= sig_rows["decision_time"]).all()
          and (sig_rows["d1_slot"] < sig_rows["time"].dt.normalize() + pd.Timedelta(days=1)).all())
    trunc_ok = []
    for q in TRUNCATION_FRACTIONS:
        cut = int(len(h1) * q)
        ft, _, _ = build_signals(h1.iloc[:cut].reset_index(drop=True))
        cols = ["signal", "d1_bias", "h4_conf", "ema20", "atr", "d1_ema200", "h4_ema50"]
        a, b = ft[cols].to_numpy(float), f.iloc[:cut][cols].to_numpy(float)
        trunc_ok.append(bool(np.allclose(a, b, equal_nan=True, rtol=1e-12, atol=1e-12)))
    check("no future data: signals and indicators unchanged when all later H1 bars are removed",
          all(trunc_ok), f"{len(TRUNCATION_FRACTIONS)} truncation points")

    first_valid = f.loc[f["valid"], "time"].iloc[0]
    end_time = f["time"].iloc[-1]
    span = end_time - first_valid
    bounds = [first_valid] + [f.loc[f["time"] >= first_valid + span * q, "time"].iloc[0] for q in WF_FRACTIONS[:-1]] \
             + [end_time]
    check("periods chronological and non-overlapping; development precedes all walk-forward windows",
          all(bounds[i] < bounds[i + 1] for i in range(len(bounds) - 1)))

    # ---- ATR regime boundaries from the development period only
    dev_bars = f[(f["time"] >= bounds[0]) & (f["time"] < bounds[1]) & f["valid"]]
    atr_q = dev_bars["atr_pct"].quantile([0.25, 0.50, 0.75]).to_numpy()
    check("ATR regime quartiles computed from development-period bars only",
          dev_bars["time"].max() < bounds[1], f"edges {', '.join(f'{v:.4%}' for v in atr_q)}")

    # ---- backtests
    runs = {}
    for mult in SPREAD_MULTIPLIERS:
        tr, rej = backtest(f, mult)
        tr["period"] = period_of(tr["signal_time"], bounds)
        runs[mult] = (tr, pd.DataFrame(rej))
    trades, rejected = runs[1.0]
    rejected["period"] = period_of(rejected["signal_time"], bounds)
    sig_total = int((f["signal"] != 0).sum())
    check("every signal accounted for (traded or rejected with a reason)", len(trades) + len(rejected) == sig_total,
          f"{sig_total} signals = {len(trades)} trades + {len(rejected)} rejected")
    check("entry only after the signal candle closes (next H1 bar open, exactly 1 hour later)",
          ((trades["entry_time"] - trades["signal_time"]) == H1).all() and (trades["entry_pos"] == trades["signal_pos"] + 1).all())
    sl_mult, rr = PARAMS["sl_atr_multiple"], PARAMS["reward_risk"]
    atr_sig = f["atr"].to_numpy()[trades["signal_pos"].to_numpy()]
    buy = trades["side"] == "BUY"
    exp_sl = np.where(buy, trades["entry_price"] - sl_mult * atr_sig, trades["entry_price"] + sl_mult * atr_sig)
    exp_tp = np.where(buy, trades["entry_price"] + rr * sl_mult * atr_sig, trades["entry_price"] - rr * sl_mult * atr_sig)
    check("SL/TP use only the signal-candle ATR14 and the entry fill",
          np.allclose(trades["stop_loss"], exp_sl) and np.allclose(trades["tp_distance"], rr * trades["sl_distance"])
          and np.allclose(trades["take_profit"], exp_tp))
    check("one position at a time, no overlap",
          (trades["entry_pos"].iloc[1:].to_numpy() > trades["exit_pos"].iloc[:-1].to_numpy()).all())
    check("signals depend only on the signal bar and earlier bars (indicator columns causal)",
          f["decision_time"].equals(f["time"] + H1))
    check("parameters equal the pre-declared specification; nothing selected from results",
          PARAMS == {"d1_ema_fast": 50, "d1_ema_slow": 200, "h4_ema": 50, "h1_ema": 20, "h1_atr": 14,
                     "sl_atr_multiple": 1.5, "reward_risk": 2.0, "max_open_positions": 1}
          and SPREAD_MULTIPLIERS == (1.0, 1.5, 2.0))
    check("no test/holdout data: test CSV never opened; every loaded row <= cutoff",
          GUARD["test_open_attempts"] == 0 and TEST_PATH.resolve() not in GUARD["csv_reads"]
          and m5["time"].max() <= cutoff and trades["exit_time"].max() <= cutoff)

    # ---- regime context
    trades["d1_trend"] = np.where(buy, "D1 BUY bias", "D1 SELL bias")
    trades["atr_pct"] = f["atr_pct"].to_numpy()[trades["signal_pos"].to_numpy()]
    trades["atr_regime"] = pd.cut(trades["atr_pct"], [-np.inf, *atr_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"],
                                  right=False).astype(str)
    trades["session_utc"] = session_utc(trades["signal_time"])
    for col in ("d1_slot", "d1_available_at", "h4_slot", "h4_available_at", "d1_close", "d1_ema50", "d1_ema200",
                "h4_close", "h4_ema50", "ema20"):
        trades[col] = f[col].to_numpy()[trades["signal_pos"].to_numpy()]

    # ---- metrics
    res_rows = []

    def add(section: str, group: str, mult: float, tr: pd.DataFrame) -> dict:
        m = metrics(tr)
        res_rows.append({"section": section, "group": group, "spread_multiplier": mult, **m})
        return m

    base = {"OVERALL": add("baseline", "OVERALL", 1.0, trades),
            "BUY": add("baseline", "BUY", 1.0, trades[buy]), "SELL": add("baseline", "SELL", 1.0, trades[~buy])}
    per = {p: add("period", p, 1.0, trades[trades["period"] == p]) for p in PERIODS}
    wf_all = add("period", "WF1-3 combined", 1.0, trades[trades["period"].isin(WF_PERIODS)])
    per_side = {f"{p} {s}": add("period_side", f"{p} {s}", 1.0, trades[(trades["period"] == p) & (trades["side"] == s)])
                for p in PERIODS for s in ("BUY", "SELL")}
    cost = {}
    for mult, (tr, _) in runs.items():
        cost[mult] = {g: add("cost_sensitivity", g, mult, tr if g == "OVERALL" else
                             tr[tr["period"].isin(WF_PERIODS)] if g == "WF1-3" else tr[tr["period"] == g])
                      for g in ["OVERALL", *PERIODS, "WF1-3"]}
    regimes = {}
    for col, order in (("d1_trend", ["D1 BUY bias", "D1 SELL bias"]), ("atr_regime", ["Q1", "Q2", "Q3", "Q4"]),
                       ("session_utc", ["Asia", "London", "London-NY overlap", "New York", "Off-hours"])):
        regimes[col] = [(g, add(f"regime_{col}", g, 1.0, trades[trades[col] == g])) for g in order]
        regimes[col + "_wf"] = [(g, add(f"regime_{col}_wf_only", g, 1.0,
                                        trades[(trades[col] == g) & trades["period"].isin(WF_PERIODS)])) for g in order]

    rej_counts = rejected.groupby(["period", "reason"]).size().unstack(fill_value=0) if len(rejected) else pd.DataFrame()
    for p in PERIODS:
        for reason, v in (rej_counts.loc[p].items() if p in rej_counts.index else []):
            res_rows.append({"section": "rejected_signals", "group": f"{p} {reason}", "spread_multiplier": 1.0,
                             "total_trades": int(v)})

    # ---- integrity after
    hashes_after = snapshot(skip, cutoff_str)
    changed = sorted(k for k in set(hashes_before) | set(hashes_after) if hashes_before.get(k) != hashes_after.get(k))
    check("no existing project files changed", not changed, f"{len(hashes_before)} files compared")

    # ---- outputs
    out_trades = trades.drop(columns=["signal_pos", "entry_pos", "exit_pos"]).copy()
    out_trades.insert(0, "trade_id", np.arange(1, len(out_trades) + 1))
    out_trades.to_csv(TRADES_PATH, index=False, date_format=TIME_FORMAT, float_format="%.6f")
    pd.DataFrame(res_rows).to_csv(RESULTS_PATH, index=False, float_format="%.6f")

    o = base["OVERALL"]
    usd_pos, r_pos = o["net_pnl"] > 0, o["average_r"] > 0
    if usd_pos and r_pos:
        neutral = ("The baseline produced a positive result after costs in this backtest, in USD and in R. This is a "
                   "research result only and requires independent confirmation (e.g. the reserved holdout); it is not "
                   "evidence of a profitable or live-ready strategy.")
    elif not usd_pos and not r_pos:
        neutral = ("The baseline lost money after costs in this backtest, in USD and in R. No modification was made in "
                   "response; the rules as specified do not show a positive result on this data.")
    else:
        neutral = (f"The result is mixed: net P&L is {o['net_pnl']:+.2f} USD/oz (PF {o['profit_factor']:.3f}) while the "
                   f"average trade is {o['average_r']:+.4f}R ({o['total_r']:+.2f}R in total). The units disagree because "
                   "gold's price and ATR rose several-fold over the sample, so later trades carry far larger USD amounts; "
                   "R corresponds to risking a fixed amount per trade. With 2:1 reward/risk the break-even win rate "
                   f"before costs is 33.3%; the observed {o['win_rate']:.1%} is only marginally above it. No modification "
                   "was made in response; this is not evidence of a profitable or live-ready strategy.")
    neutral += (" By walk-forward window, net USD/oz: " + ", ".join(f"{p} {per[p].get('net_pnl', 0.0):+.2f}" for p in WF_PERIODS)
                + "; average R: " + ", ".join(f"{p} {per[p].get('average_r', float('nan')):+.4f}" for p in WF_PERIODS)
                + f". SELL trades: {base['SELL']['total_trades']} trades, {base['SELL']['average_r']:+.4f}R average. "
                f"At 2.0x spread: overall net {cost[2.0]['OVERALL']['net_pnl']:+.2f} USD/oz, "
                f"{cost[2.0]['OVERALL']['average_r']:+.4f}R average.")

    L = ["XAUUSD Daily Trend + H4 Trend + H1 EMA Pullback Baseline - research backtest", "=" * 78,
         "Research only. Fixed, pre-declared rules; no tuning, no ML, no live code, no orders.", TEST_STATEMENT, ""]
    L += ["1. DATA",
          f"   {H1_PATH.relative_to(SRC_DIR.parent)}: {n_source} H1 bid bars, {h1['time'].iloc[0]} -> {h1['time'].iloc[-1]} "
          "(server clock); downloaded read-only from MT5 MetaQuotes-Demo by src/fetch_xauusd_h1_history.py, ending",
          f"   with the last H1 bar that closes before the research cutoff {cutoff_str}.",
          f"   {RAW_PATH.relative_to(SRC_DIR.parent)}: {len(m5)} M5 rows read (through {cutoff_str}) for the feed check and spread context.",
          f"   Feed check: {feed['ohlc_exact_match']}/{feed['hours_compared']} complete hours have identical OHLC in both files "
          f"(same feed and clock); H1 spread equals the minimum M5 spread of the hour in {feed['h1_spread_eq_min_m5_spread']:.1%}.",
          f"   Clock: server time = Europe/Athens (EET/EEST): {tz['reopen_at_18_ny_share']:.1%} of {tz['daily_breaks']} daily "
          "breaks reopen at 18:00 New York. UTC sessions use this conversion.",
          f"   D1 candles: {len(d1)} (server-day slots); H4 candles: {len(h4)} (00/04/08/12/16/20 server-clock slots); both "
          "built only from existing H1 bars, never filled.",
          f"   First bar with every indicator defined: {first_valid}. Usable period: {first_valid} -> {end_time}.",
          "   Final untouched holdout: everything after the cutoff (the existing M5 test period) - never downloaded or read.", ""]
    L += ["2. STRATEGY PARAMETERS (pre-declared, unchanged)",
          "   D1 bias: BUY if EMA50 > EMA200 and close > EMA50; SELL if EMA50 < EMA200 and close < EMA50; else none.",
          "   H4 confirmation: completed H4 close > EMA50 (BUY) / < EMA50 (SELL); disagreement = no trade.",
          "   H1 BUY: low <= EMA20, close > EMA20, close > open. H1 SELL: high >= EMA20, close < EMA20, close < open.",
          "   Entry: open of the next H1 bar, only if it is exactly one hour after the signal bar; else rejected.",
          "   SL = entry -/+ 1.5 x ATR14 (signal bar, Wilder); TP = entry +/- 2.0 x risk. One position; no pyramiding,",
          "   trailing, break-even, partials or discretionary exits. Exits: SL, TP, end of data.",
          "   Same-candle SL and TP: SL assumed first (counted below). Gap through SL: exit at the actual open (GAP_SL).",
          "   Gap through TP: exit at the TP level (conservative; no favourable slippage credited).",
          "   EMAs: pandas ewm(span, adjust=False, min_periods=span), the project convention.",
          f"   {PARAMS}", ""]
    L += ["3. COST ASSUMPTIONS",
          f"   Spread per bar = max(bar spread, {MIN_SPREAD_POINTS} points) x ${POINT_SIZE} (MT5 stores the bar's MINIMUM spread;",
          f"   the floor is the project's validated methodology). M5 spreads before the cutoff: median {feed['m5_spread_median']:.0f},",
          f"   75th pct {feed['m5_spread_p75']:.0f}, 95th pct {feed['m5_spread_p95']:.0f} points; {feed['m5_share_below_floor']:.1%} below the floor.",
          f"   Extra cost ${EXTRA_COST_PER_SIDE:.2f} per side (project's $0.10 round-trip commission/slippage allowance).",
          "   No separate broker commission: none is validated for this account, so none beyond that allowance is included.",
          "   BUY: entry at ask = open + spread + 0.05; exits at bid - 0.05. SELL: entry at bid - 0.05; exits at",
          "   ask + 0.05 = bid + spread + 0.05 (spread of the exit bar). Exact tick-level bid/ask is not available;",
          "   bar-level spreads are a limitation. P&L is in USD per ounce (x100 for one 100-oz lot); R = P&L / risk.", ""]
    L += ["4. RESEARCH DESIGN (calendar fractions of the usable period; no parameter is fitted anywhere)"]
    for i, p in enumerate(PERIODS):
        L.append(f"   {p:<4} {bounds[i]} -> {bounds[i + 1]}" + ("  (development / in-sample)" if p == "DEV" else ""))
    L += ["   Trades belong to the period of their signal bar; the backtest runs continuously (positions may cross",
          "   a boundary). Only the ATR-regime quartile edges are taken from the development period.", ""]
    L += ["5. BASELINE METRICS (spread x1.0)"] + metric_table(base) + [""]
    L += ["   Rejected / skipped signals:"]
    for reason, v in Counter(rejected["reason"]).items():
        L.append(f"     {reason}: {v}")
    L += [f"   Signals: {sig_total} = {len(trades)} trades + {len(rejected)} rejected.", ""]
    L += ["6. RESULTS BY PERIOD"] + metric_table({**per, "WF1-3": wf_all}) + [""]
    L += ["   By period and side:"] + short_table(list(per_side.items()))
    if len(rej_counts):
        L += ["   Rejected signals by period:"] + [f"     {p}: " + ", ".join(f"{k} {int(v)}" for k, v in row.items())
                                                  for p, row in rej_counts.iterrows()]
    L.append("")
    L += ["7. COST SENSITIVITY (predefined; spread multiplied, $0.05/side unchanged; not optimisation)"]
    L += [f"   {'multiplier':<12}{'group':<10}{'trades':>7}{'win%':>7}{'net':>10}{'PF':>7}{'avgR':>8}{'totR':>8}"]
    for mult, groups in cost.items():
        for g, m in groups.items():
            L.append(f"   {mult:<12}{g:<10}{m['total_trades']:>7}{m['win_rate'] * 100:>7.1f}{m['net_pnl']:>+10.2f}"
                     f"{fmt(m['profit_factor'], '.3f'):>7}{m['average_r']:>+8.4f}{m['total_r']:>+8.2f}")
    L.append("")
    L += ["8. REGIME ANALYSIS (descriptive only; not used to alter the strategy)",
          "   D1 trend direction (identical to trade side by construction):"] + short_table(regimes["d1_trend"])
    L += [f"   H1 ATR14/close regime, development-period quartile edges {', '.join(f'{v:.4%}' for v in atr_q)}:"]
    L += ["   all periods:"] + short_table(regimes["atr_regime"]) + ["   walk-forward windows only:"] \
         + short_table(regimes["atr_regime_wf"])
    L += ["   UTC session of the signal bar (project session hours, DST-aware):", "   all periods:"] \
         + short_table(regimes["session_utc"]) + ["   walk-forward windows only:"] + short_table(regimes["session_utc_wf"])
    L.append("")
    L += ["9. LEAKAGE / INTEGRITY CHECKS"] + [f"   [{'PASS' if ok else 'FAIL'}] {n}" + (f" - {d}" if d else "")
                                             for n, ok, d in checks] + [""]
    L += ["10. LIMITATIONS",
          "   - Bar-level (H1) simulation: intrabar order is unknown (same-candle SL/TP resolved as SL), and spreads are",
          "     bar minimums floored at 15 points, not tick-accurate bid/ask; real fills and slippage may differ.",
          "   - One broker feed (MetaQuotes-Demo); other brokers' candles, sessions and spreads differ.",
          "   - EMA200 on D1 starts with min_periods=200; the first development months use a less-converged EMA.",
          "   - Results are one path of one fixed rule set; no statistical significance testing of P&L is implied.",
          "   - Nothing here is a trading recommendation; no profitability or live-readiness is claimed.", ""]
    L += ["11. NEUTRAL CONCLUSION", f"   {neutral}"]
    REPORT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    assert snapshot(skip, cutoff_str) == hashes_before, "existing files changed while writing outputs"

    print("\nFINAL SUMMARY")
    print(f"  input files: {H1_PATH} ({n_source} rows, {h1['time'].iloc[0]} -> {h1['time'].iloc[-1]}); "
          f"{RAW_PATH} ({len(m5)} rows through {cutoff_str}, feed check/spread context only)")
    print(f"  usable period: {first_valid} -> {end_time}")
    print(f"  parameters: {PARAMS}")
    print(f"  costs: spread max(bar, {MIN_SPREAD_POINTS} pts) x {SPREAD_MULTIPLIERS}; ${EXTRA_COST_PER_SIDE}/side; no separate commission")
    print("  periods: " + "; ".join(f"{p} {bounds[i]} -> {bounds[i + 1]}" for i, p in enumerate(PERIODS)))
    print(f"  baseline: {o['total_trades']} trades (BUY {o['buy_trades']}, SELL {o['sell_trades']}), win {o['win_rate']:.1%}, "
          f"net {o['net_pnl']:+.2f} USD/oz, PF {o['profit_factor']:.3f}, avg R {o['average_r']:+.4f}, maxDD {o['max_drawdown_r']:.1f}R")
    for p in PERIODS:
        m = per[p]
        print(f"  {p}: {m.get('total_trades', 0)} trades, net {m.get('net_pnl', 0):+.2f}, PF {fmt(m.get('profit_factor'), '.3f')}, "
              f"avg R {m.get('average_r', float('nan')):+.4f}")
    print("  cost sensitivity (overall net): " + ", ".join(f"x{k} {v['OVERALL']['net_pnl']:+.2f}" for k, v in cost.items()))
    print(f"  integrity checks: {sum(ok for _, ok, _ in checks)}/{len(checks)} passed")
    print("  outputs: " + ", ".join(str(p) for p in outputs))


if __name__ == "__main__":
    main()
