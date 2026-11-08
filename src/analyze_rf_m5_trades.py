"""Read-only descriptive analysis of the RF M5 validation backtest trades.

Trades are grouped by side, UTC hour, trading session, RSI bucket and ATR%
volatility bucket. Group context (hour, session, RSI, ATR%) comes from the
feature row at each trade's signal bar, i.e. exactly what the model saw when
the signal was generated.

ATR% bucket edges are the quartiles of atr_14_pct in the training split, so the
validation trades do not define their own buckets. RSI buckets use fixed edges.

This is descriptive only. With one validation period and many groups, some
groups will look profitable or unprofitable by chance. Nothing here is evidence
that a subgroup is predictively profitable, and no subgroup should become a
trading filter without testing on data that played no part in choosing it.

Inputs are only read. Outputs are three new CSV files under src/data/.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from features_m5 import SESSION_IDS

DATA_DIR = Path(__file__).resolve().parent / "data"
TRADES_PATH = DATA_DIR / "rf_m5_validation_trades.csv"
FEATURES_PATH = DATA_DIR / "xauusd_m5_features.csv"
TRAIN_PATH = DATA_DIR / "xauusd_m5_train.csv"

REPORT_PATH = DATA_DIR / "rf_m5_trade_analysis.csv"
STREAKS_PATH = DATA_DIR / "rf_m5_trade_loss_streaks.csv"
DRAWDOWNS_PATH = DATA_DIR / "rf_m5_trade_drawdowns.csv"
INPUT_PATHS = {TRADES_PATH, FEATURES_PATH, TRAIN_PATH}

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
OUNCES_PER_LOT = 100

VERY_SMALL_SAMPLE = 30
SMALL_SAMPLE = 100

RSI_EDGES = [-np.inf, 30, 40, 50, 60, 70, np.inf]
RSI_LABELS = ["<30", "30-40", "40-50", "50-60", "60-70", ">=70"]
SESSION_NAMES = {code: name for name, code in SESSION_IDS.items()}
CONTEXT_COLUMNS = ["hour_utc", "session_id", "rsi_14", "atr_14_pct", "atr_14"]

DIMENSIONS = [
    ("overall", None),
    ("exit_reason", "exit_reason"),
    ("hour_utc", "hour_utc"),
    ("session", "session"),
    ("rsi_bucket", "rsi_bucket"),
    ("atr_pct_bucket", "atr_pct_bucket"),
]

REQUIRED_TRADE_COLUMNS = [
    "trade_id", "side", "signal_time", "entry_time", "exit_time", "exit_reason",
    "atr", "net_pnl", "net_pnl_r",
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    missing = [c for c in REQUIRED_TRADE_COLUMNS if c not in trades.columns]
    if missing:
        raise ValueError(f"Trades file is missing columns: {missing}")
    for col in ("signal_time", "entry_time", "exit_time"):
        trades[col] = pd.to_datetime(trades[col], format=TIME_FORMAT)

    if trades.empty:
        raise ValueError("Trades file contains no trades.")
    if not trades["trade_id"].is_unique:
        raise ValueError("Duplicate trade_id values.")
    if not trades["entry_time"].is_monotonic_increasing:
        raise ValueError("Trades are not in chronological order.")
    if not (trades["entry_time"] > trades["signal_time"]).all():
        raise ValueError("A trade enters at or before its signal bar.")
    if not (trades["entry_time"].iloc[1:].to_numpy() > trades["exit_time"].iloc[:-1].to_numpy()).all():
        raise ValueError("Overlapping trades found.")
    if not np.isfinite(trades[["net_pnl", "net_pnl_r"]].to_numpy(float)).all():
        raise ValueError("Non-finite P&L values found.")
    return trades


def attach_signal_context(trades: pd.DataFrame) -> pd.DataFrame:
    features = pd.read_csv(FEATURES_PATH, usecols=["time"] + CONTEXT_COLUMNS)
    features["time"] = pd.to_datetime(features["time"], format=TIME_FORMAT)
    merged = trades.merge(features, left_on="signal_time", right_on="time", how="left", validate="many_to_one")
    if merged[CONTEXT_COLUMNS].isna().any().any():
        raise ValueError("Some signal bars have no matching feature row.")
    if not np.allclose(merged["atr"], merged["atr_14"]):
        raise ValueError("Trade ATR differs from feature atr_14 at the signal bar; files are misaligned.")
    return merged.drop(columns=["time", "atr_14"])


def atr_pct_bucket_edges() -> tuple[list[float], list[str]]:
    train = pd.read_csv(TRAIN_PATH, usecols=["atr_14_pct"])
    q1, q2, q3 = train["atr_14_pct"].quantile([0.25, 0.50, 0.75]).to_numpy()
    edges = [-np.inf, q1, q2, q3, np.inf]
    labels = [
        f"Q1 low (<{q1:.4%})",
        f"Q2 ({q1:.4%}-{q2:.4%})",
        f"Q3 ({q2:.4%}-{q3:.4%})",
        f"Q4 high (>={q3:.4%})",
    ]
    return edges, labels


def add_buckets(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades["session"] = trades["session_id"].astype(int).map(SESSION_NAMES)
    trades["rsi_bucket"] = pd.cut(trades["rsi_14"], bins=RSI_EDGES, labels=RSI_LABELS, right=False)
    edges, labels = atr_pct_bucket_edges()
    trades["atr_pct_bucket"] = pd.cut(trades["atr_14_pct"], bins=edges, labels=labels, right=False)
    if trades[["session", "rsi_bucket", "atr_pct_bucket"]].isna().any().any():
        raise ValueError("Some trades could not be assigned to a bucket.")
    return trades


# --------------------------------------------------------------------------
# Group statistics
# --------------------------------------------------------------------------

def sample_flag(n: int) -> str:
    if n < VERY_SMALL_SAMPLE:
        return f"VERY SMALL (<{VERY_SMALL_SAMPLE}): unreliable"
    if n < SMALL_SAMPLE:
        return f"SMALL (<{SMALL_SAMPLE}): interpret with caution"
    return "adequate count (still one period)"


def profit_factor(net: pd.Series) -> float:
    profits, losses = net[net > 0].sum(), -net[net < 0].sum()
    if losses > 0:
        return profits / losses
    return float("inf") if profits > 0 else float("nan")


def group_stats(g: pd.DataFrame) -> dict:
    net, r, n = g["net_pnl"], g["net_pnl_r"], len(g)
    mean_r = r.mean()
    se = r.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    low, high = mean_r - 1.96 * se, mean_r + 1.96 * se
    return {
        "trades": n,
        "wins": int((net > 0).sum()),
        "losses": int((net < 0).sum()),
        "tp_exits": int((g["exit_reason"] == "TP").sum()),
        "sl_exits": int((g["exit_reason"] == "SL").sum()),
        "time_exits": int((g["exit_reason"] == "TIME").sum()),
        "win_rate": (net > 0).mean(),
        "net_pnl": net.sum(),
        "net_pnl_per_lot": net.sum() * OUNCES_PER_LOT,
        "avg_net_pnl": net.mean(),
        "avg_r": mean_r,
        "profit_factor": profit_factor(net),
        "avg_r_ci95_low": low,
        "avg_r_ci95_high": high,
        "ci_includes_zero": bool(not np.isfinite(se) or low <= 0 <= high),
        "sample_flag": sample_flag(n),
    }


def build_report(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side in ("ALL", "BUY", "SELL"):
        subset = trades if side == "ALL" else trades[trades["side"] == side]
        for dimension, column in DIMENSIONS:
            groups = [("all", subset)] if column is None else subset.groupby(column, observed=True, sort=True)
            for key, g in groups:
                if len(g):
                    rows.append({"dimension": dimension, "side": side, "group": str(key), **group_stats(g)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Loss streaks and drawdown periods
# --------------------------------------------------------------------------

def loss_streaks(trades: pd.DataFrame) -> pd.DataFrame:
    """Runs of consecutive losing trades (net P&L < 0); a zero or positive trade ends a run."""
    rows = []
    for scope in ("ALL", "BUY", "SELL"):
        seq = (trades if scope == "ALL" else trades[trades["side"] == scope]).reset_index(drop=True)
        is_loss = seq["net_pnl"] < 0
        run_id = (is_loss != is_loss.shift()).cumsum()
        for _, run in seq[is_loss].groupby(run_id[is_loss]):
            rows.append({
                "scope": scope,
                "length": len(run),
                "first_trade_id": int(run["trade_id"].iloc[0]),
                "last_trade_id": int(run["trade_id"].iloc[-1]),
                "start_entry_time": run["entry_time"].iloc[0],
                "end_exit_time": run["exit_time"].iloc[-1],
                "net_pnl": run["net_pnl"].sum(),
                "net_pnl_per_lot": run["net_pnl"].sum() * OUNCES_PER_LOT,
                "net_r": run["net_pnl_r"].sum(),
            })
    streaks = pd.DataFrame(rows)
    if not streaks.empty:
        streaks = streaks.sort_values(["scope", "length", "net_pnl"], ascending=[True, False, True])
    return streaks.reset_index(drop=True)


def drawdown_periods(trades: pd.DataFrame) -> pd.DataFrame:
    """Closed-trade equity drawdowns: from an equity peak to the trade that regains it.

    Equity starts at 0 before the first trade. Floating intratrade drawdown is not included.
    """
    equity = trades["net_pnl"].cumsum().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    underwater = (peak - equity) > 1e-9

    rows, i, n = [], 0, len(trades)
    while i < n:
        if not underwater[i]:
            i += 1
            continue
        start = i
        while i < n and underwater[i]:
            i += 1
        end = i - 1
        trough = start + int(np.argmax((peak - equity)[start : end + 1]))
        recovered = i < n
        peak_idx = start - 1
        rows.append({
            "peak_after_trade_id": int(trades["trade_id"].iloc[peak_idx]) if peak_idx >= 0 else 0,
            "peak_time": trades["exit_time"].iloc[peak_idx] if peak_idx >= 0 else trades["entry_time"].iloc[0],
            "peak_equity": peak[start],
            "trough_trade_id": int(trades["trade_id"].iloc[trough]),
            "trough_time": trades["exit_time"].iloc[trough],
            "trough_equity": equity[trough],
            "depth": peak[start] - equity[trough],
            "depth_per_lot": (peak[start] - equity[trough]) * OUNCES_PER_LOT,
            "trades_to_trough": trough - peak_idx,
            "recovered": recovered,
            "recovery_trade_id": int(trades["trade_id"].iloc[i]) if recovered else None,
            "recovery_time": trades["exit_time"].iloc[i] if recovered else None,
            "trades_underwater": end - start + 1,
            "calendar_duration": (trades["exit_time"].iloc[i] if recovered else trades["exit_time"].iloc[-1])
                                 - (trades["exit_time"].iloc[peak_idx] if peak_idx >= 0 else trades["entry_time"].iloc[0]),
        })
    periods = pd.DataFrame(rows)
    if not periods.empty:
        periods = periods.sort_values("depth", ascending=False).reset_index(drop=True)
    return periods


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_dimension(report: pd.DataFrame, dimension: str) -> None:
    cols = ["side", "group", "trades", "win_rate", "net_pnl", "avg_r", "profit_factor", "ci_includes_zero", "sample_flag"]
    table = report.loc[report["dimension"] == dimension, cols].copy()
    table["win_rate"] = (table["win_rate"] * 100).round(1).astype(str) + "%"
    table["net_pnl"] = table["net_pnl"].round(2)
    table["avg_r"] = table["avg_r"].round(4)
    table["profit_factor"] = table["profit_factor"].round(3)
    print(f"\n=== {dimension} ===")
    print(table.to_string(index=False))


def print_summary(trades: pd.DataFrame, report: pd.DataFrame, streaks: pd.DataFrame, periods: pd.DataFrame) -> None:
    print(f"Trades analysed: {len(trades)}  ({trades['entry_time'].iloc[0]} -> {trades['exit_time'].iloc[-1]})")
    print("Net P&L in $ per ounce; x100 for one 1-lot position. avg_r is net P&L in units of the SL distance.")
    print("win_rate = share of trades with net P&L > 0. ci_includes_zero refers to the 95% interval of avg_r.")

    for dimension, _ in DIMENSIONS:
        print_dimension(report, dimension)

    print("\n=== Longest consecutive loss streaks ===")
    if streaks.empty:
        print("No losing trades.")
    else:
        for scope in ("ALL", "BUY", "SELL"):
            top = streaks[streaks["scope"] == scope].head(5)
            if top.empty:
                continue
            print(f"{scope}:")
            print(top[["length", "first_trade_id", "last_trade_id", "start_entry_time", "end_exit_time",
                       "net_pnl", "net_r"]].round(3).to_string(index=False))

    print("\n=== Closed-trade equity drawdown periods (largest 5) ===")
    print("Closed-trade equity only; intratrade floating drawdown is not included.")
    if periods.empty:
        print("No drawdown periods.")
    else:
        print(periods.head(5)[["peak_time", "trough_time", "depth", "depth_per_lot", "trades_to_trough",
                               "recovered", "recovery_time", "trades_underwater"]].round(3).to_string(index=False))
        print(f"Drawdown periods: {len(periods)}, still open at end: {int((~periods['recovered']).sum())}")

    subgroups = report[report["dimension"] != "overall"]
    flagged = int((subgroups["trades"] < SMALL_SAMPLE).sum())
    ci_excludes_zero = int((~subgroups["ci_includes_zero"]).sum())
    print("\n=== Interpretation limits ===")
    print(f"- {len(subgroups)} subgroups were evaluated; {flagged} have fewer than {SMALL_SAMPLE} trades.")
    print(f"- {ci_excludes_zero} subgroups have a 95% avg_r interval excluding zero. With this many groups,")
    print(f"  about {len(subgroups) * 0.05:.0f} would do so by chance alone, even if no group had a real edge.")
    print("- Groups overlap (ALL contains BUY and SELL; every dimension re-slices the same trades),")
    print("  and the confidence intervals ignore serial correlation between neighbouring trades.")
    print("- All results come from one validation period. They describe what happened and do not show that")
    print("  any subgroup is predictively profitable. Selecting a subgroup here and reporting it on the same")
    print("  data would be data snooping; any candidate filter needs evaluation on unseen data.")


def save_outputs(report: pd.DataFrame, streaks: pd.DataFrame, periods: pd.DataFrame) -> None:
    for path in (REPORT_PATH, STREAKS_PATH, DRAWDOWNS_PATH):
        if path in INPUT_PATHS:
            raise RuntimeError(f"Refusing to overwrite input file {path}")
    report.to_csv(REPORT_PATH, index=False)
    streaks.to_csv(STREAKS_PATH, index=False)
    periods.to_csv(DRAWDOWNS_PATH, index=False)
    print(f"\nSaved group report: {REPORT_PATH}")
    print(f"Saved loss streaks: {STREAKS_PATH}")
    print(f"Saved drawdown periods: {DRAWDOWNS_PATH}")


def main() -> None:
    trades = add_buckets(attach_signal_context(load_trades(TRADES_PATH)))
    report = build_report(trades)
    streaks = loss_streaks(trades)
    periods = drawdown_periods(trades)
    print_summary(trades, report, streaks, periods)
    save_outputs(report, streaks, periods)


if __name__ == "__main__":
    main()
