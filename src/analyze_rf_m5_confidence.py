"""Read-only analysis of RF M5 prediction confidence versus realized validation trades.

Uses the saved baseline model, the validation split and the existing validation
backtest trades. Nothing is retrained, filtered or changed; the test split is
never loaded. Probabilities are joined to trades on the signal timestamp.

Trades whose signal bar is not in the validation split (the backtest also
signals on feature rows that labeling excluded because their future window
crossed a market gap) cannot be matched and are reported as unmatched.

These results are descriptive only and must not be used to choose a
production confidence threshold.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from train_rf_m5 import RF_FEATURES

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
MODEL_PATH = SRC_DIR / "models" / "rf_m5_baseline.pkl"
VALIDATION_PATH = DATA_DIR / "xauusd_m5_validation.csv"
TRADES_PATH = DATA_DIR / "rf_m5_validation_trades.csv"
RESULTS_PATH = DATA_DIR / "rf_m5_confidence_analysis.csv"
REPORT_PATH = DATA_DIR / "rf_m5_confidence_report.txt"
INPUT_PATHS = {MODEL_PATH, VALIDATION_PATH, TRADES_PATH}

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CLASS_COLUMNS = {-1: "P_SELL", 0: "P_WAIT", 1: "P_BUY"}
CLASS_NAMES = {-1: "SELL", 0: "WAIT", 1: "BUY"}

CONFIDENCE_EDGES = [0.33, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, np.inf]
CONFIDENCE_LABELS = ["0.33-0.40", "0.40-0.45", "0.45-0.50", "0.50-0.55",
                     "0.55-0.60", "0.60-0.65", "0.65-0.70", "0.70+"]
# A BUY/SELL argmax can have its own probability just above 1/3, so a "<0.35"
# bucket keeps every traded row assigned.
SIDE_PROB_EDGES = [-np.inf, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, np.inf]
SIDE_PROB_LABELS = ["<0.35", "0.35-0.40", "0.40-0.45", "0.45-0.50", "0.50-0.55",
                    "0.55-0.60", "0.60-0.65", "0.65-0.70", "0.70+"]
N_DECILES = 10

VERY_SMALL_SAMPLE = 30
SMALL_SAMPLE = 100

WARNING = ("These results are descriptive analysis on the validation set and must not be used to "
           "select a production confidence threshold. Any threshold discovered here must be tested "
           "on untouched data.")


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_model():
    bundle = joblib.load(MODEL_PATH)
    model, features = bundle["model"], list(bundle["features"])
    if features != RF_FEATURES or list(model.feature_names_in_) != RF_FEATURES:
        raise ValueError("Saved model features differ from train_rf_m5.RF_FEATURES.")
    if not hasattr(model, "predict_proba"):
        raise TypeError("Saved model does not support predict_proba().")
    if sorted(model.classes_.tolist()) != [-1, 0, 1]:
        raise ValueError(f"Unexpected model classes: {model.classes_.tolist()}")
    return model


def validation_probabilities(model) -> pd.DataFrame:
    val = pd.read_csv(VALIDATION_PATH)
    val["time"] = pd.to_datetime(val["time"], format=TIME_FORMAT)
    X = val[RF_FEATURES]
    if not np.isfinite(X.to_numpy(float)).all():
        raise ValueError("Validation features contain missing or infinite values.")

    proba = model.predict_proba(X)
    probs = pd.DataFrame({"time": val["time"]})
    for idx, cls in enumerate(model.classes_):
        probs[CLASS_COLUMNS[int(cls)]] = proba[:, idx]
    probs["predicted_class"] = model.classes_[proba.argmax(axis=1)]
    probs["confidence"] = proba.max(axis=1)
    if not np.allclose(probs[list(CLASS_COLUMNS.values())].sum(axis=1), 1.0):
        raise ValueError("Class probabilities do not sum to 1.")
    return probs


def load_trades() -> pd.DataFrame:
    trades = pd.read_csv(TRADES_PATH)
    for col in ("signal_time", "entry_time", "exit_time"):
        trades[col] = pd.to_datetime(trades[col], format=TIME_FORMAT)
    if not trades["trade_id"].is_unique or not trades["signal_time"].is_unique:
        raise ValueError("Trades must have unique trade_id and signal_time values.")
    return trades.sort_values("entry_time").reset_index(drop=True)


def join_trades(trades: pd.DataFrame, probs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    merged = trades.merge(probs, left_on="signal_time", right_on="time", how="left", validate="one_to_one")
    unmatched = merged[merged["confidence"].isna()][["trade_id", "side", "signal_time", "net_pnl", "net_pnl_r"]]
    matched = merged[merged["confidence"].notna()].drop(columns="time").copy()

    side_code = matched["side"].map({"BUY": 1, "SELL": -1})
    class_mismatch = int((matched["predicted_class"] != side_code).sum())
    matched["side_probability"] = np.where(matched["side"] == "BUY", matched["P_BUY"], matched["P_SELL"])
    return matched.reset_index(drop=True), unmatched.reset_index(drop=True), class_mismatch


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def sample_flag(n: int) -> str:
    if n < VERY_SMALL_SAMPLE:
        return "VERY SMALL"
    if n < SMALL_SAMPLE:
        return "SMALL"
    return "ok"


def profit_factor(net: pd.Series) -> float:
    profits, losses = net[net > 0].sum(), -net[net < 0].sum()
    if losses > 0:
        return profits / losses
    return float("inf") if profits > 0 else float("nan")


def closed_trade_max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum().to_numpy()
    if not len(equity):
        return float("nan")
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return float((peak - equity).max())


def metrics(g: pd.DataFrame) -> dict:
    g = g.sort_values("entry_time")
    net, r = g["net_pnl"], g["net_pnl_r"]
    return {
        "trades": len(g),
        "buy_trades": int((g["side"] == "BUY").sum()),
        "sell_trades": int((g["side"] == "SELL").sum()),
        "tp": int((g["exit_reason"] == "TP").sum()),
        "sl": int((g["exit_reason"] == "SL").sum()),
        "time": int((g["exit_reason"] == "TIME").sum()),
        "win_rate": (net > 0).mean() if len(g) else float("nan"),
        "total_net_pnl": net.sum(),
        "avg_net_pnl": net.mean() if len(g) else float("nan"),
        "avg_r": r.mean() if len(g) else float("nan"),
        "total_r": r.sum(),
        "profit_factor": profit_factor(net),
        "max_dd_usd_per_oz": closed_trade_max_drawdown(net),
        "max_dd_r": closed_trade_max_drawdown(r),
        "conf_min": g["confidence"].min() if len(g) else float("nan"),
        "conf_max": g["confidence"].max() if len(g) else float("nan"),
        "sample_flag": sample_flag(len(g)),
    }


def bucket_table(trades: pd.DataFrame, value_col: str, edges, labels, section: str, scope: str) -> pd.DataFrame:
    buckets = pd.cut(trades[value_col], bins=edges, labels=labels, right=False)
    if buckets.isna().any():
        raise ValueError(f"{section}/{scope}: some rows fall outside the bucket edges.")
    rows = []
    for label in labels:
        g = trades[buckets == label]
        rows.append({"section": section, "scope": scope, "bucket": label, "value_column": value_col, **metrics(g)})
    return pd.DataFrame(rows)


def decile_table(trades: pd.DataFrame) -> pd.DataFrame:
    order = trades["confidence"].rank(method="first")
    decile = pd.qcut(order, N_DECILES, labels=range(1, N_DECILES + 1))
    rows = []
    for d in range(1, N_DECILES + 1):
        g = trades[decile == d]
        rows.append({"section": "confidence_decile", "scope": "ALL", "bucket": f"D{d}",
                     "value_column": "confidence", **metrics(g)})
    return pd.DataFrame(rows)


def correlation(x: pd.Series, y: pd.Series) -> dict:
    n = len(x)
    pearson = x.corr(y)
    spearman = x.rank().corr(y.rank())
    t = pearson * np.sqrt((n - 2) / (1 - pearson ** 2)) if n > 2 and abs(pearson) < 1 else float("nan")
    return {"n": n, "pearson": pearson, "spearman": spearman, "pearson_t_stat": t}


def correlation_table(trades: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("ALL", "confidence", trades),
        ("BUY", "P_BUY", trades[trades["side"] == "BUY"]),
        ("SELL", "P_SELL", trades[trades["side"] == "SELL"]),
    ]
    rows = []
    for scope, col, g in specs:
        for target in ("net_pnl", "net_pnl_r"):
            rows.append({"section": "correlation", "scope": scope, "bucket": f"{col} vs {target}",
                         "value_column": col, **correlation(g[col], g[target])})
    return pd.DataFrame(rows)


def monotonic_note(table: pd.DataFrame) -> str:
    usable = table[table["trades"] >= VERY_SMALL_SAMPLE]
    if len(usable) < 3:
        return "fewer than 3 buckets with >= 30 trades; monotonicity not assessed"
    diffs = np.diff(usable["avg_r"].to_numpy())
    if (diffs > 0).all():
        return "avg R increases across every bucket with >= 30 trades"
    if (diffs < 0).all():
        return "avg R decreases across every bucket with >= 30 trades"
    return f"not monotonic: avg R rises in {int((diffs > 0).sum())} and falls in {int((diffs < 0).sum())} of {len(diffs)} steps (buckets with >= 30 trades)"


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def format_table(table: pd.DataFrame) -> str:
    cols = ["bucket", "trades", "buy_trades", "sell_trades", "tp", "sl", "time", "win_rate",
            "total_net_pnl", "avg_net_pnl", "avg_r", "profit_factor", "max_dd_usd_per_oz", "sample_flag"]
    t = table[cols].copy()
    t["win_rate"] = t["win_rate"].map(lambda v: "-" if pd.isna(v) else f"{v:.1%}")
    for col, digits in (("total_net_pnl", 2), ("avg_net_pnl", 3), ("avg_r", 4),
                        ("profit_factor", 3), ("max_dd_usd_per_oz", 2)):
        t[col] = t[col].map(lambda v, d=digits: "-" if pd.isna(v) else f"{v:.{d}f}")
    return t.to_string(index=False)


def format_deciles(table: pd.DataFrame) -> str:
    t = table[["bucket", "conf_min", "conf_max", "trades", "avg_r", "total_r", "win_rate", "profit_factor"]].copy()
    t["conf_min"] = t["conf_min"].map("{:.4f}".format)
    t["conf_max"] = t["conf_max"].map("{:.4f}".format)
    t["avg_r"] = t["avg_r"].map("{:.4f}".format)
    t["total_r"] = t["total_r"].map("{:.2f}".format)
    t["win_rate"] = t["win_rate"].map("{:.1%}".format)
    t["profit_factor"] = t["profit_factor"].map("{:.3f}".format)
    return t.to_string(index=False)


def build_report(model, probs, matched, unmatched, class_mismatch, conf_tables, buy_table, sell_table,
                 deciles, corr) -> list[str]:
    lines = ["RF M5 baseline - prediction confidence vs realized validation trades", "=" * 70,
             f"WARNING: {WARNING}", ""]

    lines += ["1. Model classes",
              f"   classes_ = {model.classes_.tolist()} -> columns P_SELL (-1), P_WAIT (0), P_BUY (1)", ""]

    lines += ["2. Validation rows analyzed",
              f"   {len(probs)} rows, {probs['time'].iloc[0]} -> {probs['time'].iloc[-1]}", ""]

    lines += ["3. Traded rows matched",
              f"   {len(matched)} of {len(matched) + len(unmatched)} trades matched on signal_time",
              f"   predicted_class (argmax of predict_proba) disagrees with trade side: {class_mismatch}", ""]

    lines += ["4. Unmatched trade rows",
              f"   {len(unmatched)} trades have a signal bar outside xauusd_m5_validation.csv",
              "   (signals on feature rows that labeling excluded because their window crossed a gap)."]
    if len(unmatched):
        lines += [f"   unmatched: BUY {int((unmatched['side'] == 'BUY').sum())}, "
                  f"SELL {int((unmatched['side'] == 'SELL').sum())}, "
                  f"net P&L {unmatched['net_pnl'].sum():.2f} $/oz, avg R {unmatched['net_pnl_r'].mean():.4f}",
                  "   first 5: " + ", ".join(f"#{r.trade_id} {r.signal_time}" for r in unmatched.head(5).itertuples())]
    lines.append("")

    dist = probs["predicted_class"].map(CLASS_NAMES).value_counts()
    lines += ["5. Overall confidence statistics",
              "   all validation rows: predicted " + ", ".join(f"{k} {int(dist.get(k, 0))}" for k in ("BUY", "SELL", "WAIT")),
              "   " + describe(probs["confidence"], "confidence, all validation rows"),
              "   " + describe(matched["confidence"], "confidence, matched trades"),
              "   " + describe(matched.loc[matched.side == "BUY", "P_BUY"], "P_BUY, matched BUY trades"),
              "   " + describe(matched.loc[matched.side == "SELL", "P_SELL"], "P_SELL, matched SELL trades"), ""]

    lines.append("6. Confidence bucket table (confidence = max class probability)")
    for scope, table in conf_tables.items():
        lines += [f"   [{scope}]  {monotonic_note(table)}", format_table(table), ""]

    lines += ["7. BUY probability bucket table (BUY trades, bucketed by P_BUY)",
              f"   {monotonic_note(buy_table)}", format_table(buy_table), ""]
    lines += ["8. SELL probability bucket table (SELL trades, bucketed by P_SELL)",
              f"   {monotonic_note(sell_table)}", format_table(sell_table), ""]

    lines += ["9. Confidence decile table (matched trades, ~equal-sized groups by confidence)",
              format_deciles(deciles), ""]

    lines.append("10. Correlations (matched trades)")
    for r in corr.itertuples():
        lines.append(f"   {r.scope:<4} {r.bucket:<26} n={r.n:<5} pearson={r.pearson:+.4f}  "
                     f"spearman={r.spearman:+.4f}  t={r.pearson_t_stat:+.2f}")
    lines.append("")

    lines += ["11. Important warnings and limitations",
              f"   - {WARNING}",
              "   - No threshold was optimized and none is recommended; the strategy is unchanged.",
              "   - Trades come from a single-position backtest: which signals became trades depends on",
              "     earlier trades, so these are not independent samples of every signal.",
              "   - Buckets with fewer than 30 trades are flagged VERY SMALL, fewer than 100 SMALL.",
              "   - Many buckets and slices are compared; some will look different by chance alone.",
              "   - Correlation t-statistics assume independent trades and ignore serial correlation.",
              "   - net_pnl is in $/oz and scales with ATR; R (net P&L / SL distance) is the comparable unit.",
              f"   - {len(unmatched)} traded signals are not in the validation split and are excluded here.",
              "   - Random Forest probabilities are vote shares, not calibrated probabilities.",
              "   - One validation period (2026-08-20 to 2026-09-29) only."]
    return lines


def describe(s: pd.Series, name: str) -> str:
    q = s.quantile([0.1, 0.5, 0.9])
    return (f"{name}: n={len(s)} mean={s.mean():.4f} min={s.min():.4f} p10={q[0.1]:.4f} "
            f"median={q[0.5]:.4f} p90={q[0.9]:.4f} max={s.max():.4f}")


def main() -> None:
    model = load_model()
    probs = validation_probabilities(model)
    trades = load_trades()
    matched, unmatched, class_mismatch = join_trades(trades, probs)

    conf_tables = {
        scope: bucket_table(g, "confidence", CONFIDENCE_EDGES, CONFIDENCE_LABELS, "confidence_bucket", scope)
        for scope, g in (("ALL", matched), ("BUY", matched[matched.side == "BUY"]),
                         ("SELL", matched[matched.side == "SELL"]))
    }
    buy_table = bucket_table(matched[matched.side == "BUY"], "P_BUY", SIDE_PROB_EDGES, SIDE_PROB_LABELS,
                             "buy_probability_bucket", "BUY")
    sell_table = bucket_table(matched[matched.side == "SELL"], "P_SELL", SIDE_PROB_EDGES, SIDE_PROB_LABELS,
                              "sell_probability_bucket", "SELL")
    deciles = decile_table(matched)
    corr = correlation_table(matched)

    for path in (RESULTS_PATH, REPORT_PATH):
        if path in INPUT_PATHS:
            raise RuntimeError(f"Refusing to overwrite input file {path}")
    results = pd.concat([*conf_tables.values(), buy_table, sell_table, deciles, corr], ignore_index=True)
    results.to_csv(RESULTS_PATH, index=False)

    lines = build_report(model, probs, matched, unmatched, class_mismatch, conf_tables, buy_table,
                         sell_table, deciles, corr)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved results: {RESULTS_PATH}")
    print(f"Saved report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()
