"""Pre-defined Random Forest configuration comparison for the XAUUSD M5 baseline.

Research only. Every candidate is trained on the existing training split and
evaluated on the existing validation split with the same 30 features, labels
and the unchanged backtest engine imported from backtest_rf_m5.py (entry
timing, TP/SL, spread and cost model, gap handling, one position at a time).
The test split is never loaded. No model is saved and no existing file is
modified. Candidates differ from the baseline only in max_depth,
min_samples_leaf and max_samples; the list and the warning rules below are
fixed before any result is seen.

Before comparing, the retrained baseline must reproduce the saved model's
predictions and the existing validation trades exactly.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score

from backtest_rf_m5 import (
    WARNINGS as BACKTEST_WARNINGS,
    VALIDATION_PATH as BACKTEST_VALIDATION_PATH,
    check_against_validation,
    count_boundary_signals,
    generate_signals,
    load_market,
    load_validation_period,
    run_backtest,
)
from backtest_rf_m5 import TRADES_PATH as BASELINE_TRADES_PATH
from train_rf_m5 import (
    CLASS_ORDER,
    MODEL_PATH,
    RF_FEATURES,
    RF_PARAMS,
    TRAIN_PATH,
    VALIDATION_PATH,
    load_split,
    validate_inputs,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_PATH = DATA_DIR / "rf_m5_model_comparison.csv"
REPORT_PATH = DATA_DIR / "rf_m5_model_comparison_report.txt"
INPUT_PATHS = {TRAIN_PATH, VALIDATION_PATH, MODEL_PATH, BASELINE_TRADES_PATH}

# Only these three parameters vary; everything else is the baseline's RF_PARAMS.
CANDIDATES = {
    "BASELINE":    {"max_depth": 8,  "min_samples_leaf": 50, "max_samples": 0.5},
    "CANDIDATE_A": {"max_depth": 10, "min_samples_leaf": 50, "max_samples": 0.5},
    "CANDIDATE_B": {"max_depth": 12, "min_samples_leaf": 50, "max_samples": 0.5},
    "CANDIDATE_C": {"max_depth": 10, "min_samples_leaf": 25, "max_samples": 0.5},
    "CANDIDATE_D": {"max_depth": 12, "min_samples_leaf": 25, "max_samples": 0.5},
    "CANDIDATE_E": {"max_depth": 10, "min_samples_leaf": 50, "max_samples": None},
    "CANDIDATE_F": {"max_depth": 12, "min_samples_leaf": 50, "max_samples": None},
}

# Pre-defined overfitting / noise warning rules (fixed before running).
GAP_ABSOLUTE_WARNING = 0.10      # train - validation balanced accuracy
GAP_INCREASE_WARNING = 0.03      # gap larger than the baseline's gap by this much
NOISE_SE_MULTIPLE = 2.0          # avg R change smaller than 2 standard errors = within noise

REPORT_WARNING = (
    "Validation results are NOT the final performance estimate. Seven configurations were "
    "compared on the same validation period, so the best-looking one is optimistically biased. "
    "The untouched TEST set has not been loaded or used in any way."
)


# --------------------------------------------------------------------------
# Training and ML metrics
# --------------------------------------------------------------------------

def candidate_params(name: str) -> dict:
    params = {**RF_PARAMS, **CANDIDATES[name]}
    changed = {k for k in params if params[k] != RF_PARAMS[k]}
    assert changed <= {"max_depth", "min_samples_leaf", "max_samples"}, f"{name} changes {changed}"
    return params


def ml_metrics(model, X_train, y_train, X_val, y_val) -> dict:
    train_pred, val_pred = model.predict(X_train), model.predict(X_val)
    precision = precision_score(y_val, val_pred, labels=CLASS_ORDER, average=None, zero_division=0)
    train_bal = balanced_accuracy_score(y_train, train_pred)
    val_bal = balanced_accuracy_score(y_val, val_pred)
    return {
        "train_accuracy": accuracy_score(y_train, train_pred),
        "train_balanced_accuracy": train_bal,
        "val_accuracy": accuracy_score(y_val, val_pred),
        "val_balanced_accuracy": val_bal,
        "val_buy_precision": precision[CLASS_ORDER.index(1)],
        "val_sell_precision": precision[CLASS_ORDER.index(-1)],
        "val_wait_precision": precision[CLASS_ORDER.index(0)],
        "balanced_accuracy_gap": train_bal - val_bal,
    }


# --------------------------------------------------------------------------
# Backtest metrics (trades come from the unchanged backtest_rf_m5.run_backtest)
# --------------------------------------------------------------------------

def profit_factor(net: pd.Series) -> float:
    profits, losses = net[net > 0].sum(), -net[net < 0].sum()
    if losses > 0:
        return profits / losses
    return float("inf") if profits > 0 else float("nan")


def max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum().to_numpy()
    if not len(equity):
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return float((peak - equity).max())


def longest_losing_streak(net: pd.Series) -> int:
    longest = current = 0
    for value in net:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def trade_metrics(trades: pd.DataFrame, prefix: str = "") -> dict:
    net = trades["net_pnl"] if len(trades) else pd.Series(dtype=float)
    r = trades["net_pnl_r"] if len(trades) else pd.Series(dtype=float)
    n = len(trades)
    out = {
        "trades": n,
        "win_rate": (net > 0).mean() if n else float("nan"),
        "net_pnl": net.sum(),
        "avg_pnl": net.mean() if n else float("nan"),
        "avg_r": r.mean() if n else float("nan"),
        "total_r": r.sum(),
        "avg_r_se": r.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan"),
        "profit_factor": profit_factor(net),
    }
    if not prefix:
        out.update({
            "buy_trades": int((trades["side"] == "BUY").sum()),
            "sell_trades": int((trades["side"] == "SELL").sum()),
            "tp": int((trades["exit_reason"] == "TP").sum()),
            "sl": int((trades["exit_reason"] == "SL").sum()),
            "time": int((trades["exit_reason"] == "TIME").sum()),
            "gross_pnl": trades["gross_pnl"].sum(),
            "total_costs": trades["costs"].sum(),
            "max_closed_trade_dd": max_drawdown(net),
            "max_closed_trade_dd_r": max_drawdown(r),
            "longest_losing_streak": longest_losing_streak(net),
        })
        assert np.isclose(out["gross_pnl"] - out["total_costs"], out["net_pnl"])
    return {f"{prefix}{k}": v for k, v in out.items()}


def backtest_candidate(model, market) -> tuple[pd.DataFrame, dict]:
    raw, features, positions = market
    signals = generate_signals(model, features, RF_FEATURES)
    trades, skipped = run_backtest(raw, features, positions, signals)
    metrics = trade_metrics(trades)
    for side in ("BUY", "SELL"):
        metrics.update(trade_metrics(trades[trades["side"] == side], prefix=f"{side.lower()}_"))
    metrics.update({
        "signals_buy": int((signals == 1).sum()),
        "signals_sell": int((signals == -1).sum()),
        "signals_wait": int((signals == 0).sum()),
        "skipped_position_open": sum(v for k, v in skipped.items() if "position" in k),
        "skipped_boundary": count_boundary_signals(signals, positions, len(raw)),
    })
    return trades, metrics


# --------------------------------------------------------------------------
# Reproducibility of the baseline
# --------------------------------------------------------------------------

def check_baseline_reproducible(model, X_val, market, trades: pd.DataFrame) -> None:
    saved = joblib.load(MODEL_PATH)["model"]
    _, features, _ = market
    assert (saved.predict(X_val) == model.predict(X_val)).all(), "retrained baseline differs on validation rows"
    assert (saved.predict(features[RF_FEATURES]) == model.predict(features[RF_FEATURES])).all(), \
        "retrained baseline differs on backtest rows"

    existing = pd.read_csv(BASELINE_TRADES_PATH)
    assert len(existing) == len(trades), "baseline trade count differs from existing backtest"
    assert np.allclose(existing["net_pnl"].to_numpy(), trades["net_pnl"].to_numpy()), \
        "baseline trade P&L differs from existing backtest"


# --------------------------------------------------------------------------
# Comparison flags
# --------------------------------------------------------------------------

def add_flags(results: pd.DataFrame) -> pd.DataFrame:
    base = results.loc["BASELINE"]
    rows = {}
    for name, row in results.iterrows():
        se_diff = np.sqrt(row["avg_r_se"] ** 2 + base["avg_r_se"] ** 2)
        delta_r = row["avg_r"] - base["avg_r"]
        improved = []
        if name != "BASELINE":
            for col, label in (("val_balanced_accuracy", "val balanced accuracy"), ("net_pnl", "net P&L"),
                               ("avg_r", "avg R"), ("profit_factor", "profit factor"),
                               ("max_closed_trade_dd", "max drawdown")):
                better = row[col] < base[col] if col == "max_closed_trade_dd" else row[col] > base[col]
                if better:
                    improved.append(label)

        warnings = []
        if row["balanced_accuracy_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"train-val gap {row['balanced_accuracy_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        if row["balanced_accuracy_gap"] > base["balanced_accuracy_gap"] + GAP_INCREASE_WARNING:
            warnings.append(f"gap exceeds baseline gap by > {GAP_INCREASE_WARNING}")
        if name != "BASELINE" and delta_r > 0 and abs(delta_r) < NOISE_SE_MULTIPLE * se_diff:
            warnings.append(f"avg R gain {delta_r:+.4f} is within {NOISE_SE_MULTIPLE:.0f} SE ({se_diff:.4f}) of baseline")
        if name != "BASELINE" and row["net_pnl"] > base["net_pnl"] and \
                row["val_balanced_accuracy"] <= base["val_balanced_accuracy"]:
            warnings.append("P&L improved without better validation balanced accuracy")
        if row["avg_r"] > 0 and row["avg_r"] - NOISE_SE_MULTIPLE * row["avg_r_se"] <= 0:
            warnings.append("positive avg R is not distinguishable from zero")

        rows[name] = {
            "delta_avg_r_vs_baseline": delta_r,
            "delta_avg_r_se": se_diff,
            "improved_vs_baseline": "; ".join(improved) if improved else ("-" if name == "BASELINE" else "none"),
            "overfitting_or_noise_warnings": "; ".join(warnings) if warnings else "none",
        }
    return results.join(pd.DataFrame.from_dict(rows, orient="index"))


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def pct(series: pd.Series) -> pd.Series:
    return series.map(lambda v: "-" if pd.isna(v) else f"{v:.2%}")


def build_report(results: pd.DataFrame, n_train: int, n_val: int, n_backtest_rows: int) -> list[str]:
    lines = ["RF M5 pre-defined model comparison (validation only, research)", "=" * 72,
             f"WARNING: {REPORT_WARNING}",
             f"Training rows: {n_train}   validation rows (ML metrics): {n_val}   "
             f"backtest signal rows (validation period): {n_backtest_rows}",
             "Baseline reproducibility: retrained baseline matches the saved model's predictions and the "
             "existing validation trades exactly.", ""]

    cfg = results[["max_depth", "min_samples_leaf", "max_samples"]].copy()
    cfg["max_samples"] = cfg["max_samples"].map(lambda v: "None (all rows)" if pd.isna(v) else v)
    lines += ["1. Candidate configuration table",
              "   Fixed for all: n_estimators=300, max_features='sqrt', bootstrap=True, class_weight='balanced',",
              "   criterion='gini', random_state=42, n_jobs=-1", cfg.to_string(), ""]

    ml_cols = ["train_accuracy", "train_balanced_accuracy", "val_accuracy", "val_balanced_accuracy",
               "val_buy_precision", "val_sell_precision", "val_wait_precision"]
    ml = results[ml_cols].apply(pct)
    lines += ["2. ML metrics comparison",
              ml.to_string(), ""]

    bt_cols = ["trades", "buy_trades", "sell_trades", "tp", "sl", "time", "win_rate", "gross_pnl", "total_costs",
               "net_pnl", "avg_pnl", "avg_r", "total_r", "profit_factor", "max_closed_trade_dd",
               "longest_losing_streak"]
    bt = results[bt_cols].copy()
    bt["win_rate"] = pct(bt["win_rate"])
    for col, d in (("gross_pnl", 2), ("total_costs", 2), ("net_pnl", 2), ("avg_pnl", 3), ("avg_r", 4),
                   ("total_r", 2), ("profit_factor", 3), ("max_closed_trade_dd", 2)):
        bt[col] = bt[col].map(lambda v, d=d: f"{v:.{d}f}")
    lines += ["3. Backtest metrics comparison ($ per ounce; x100 for 1 lot; drawdown = closed-trade equity only)",
              bt.to_string(), ""]

    side_rows = []
    for name, row in results.iterrows():
        for side in ("buy", "sell"):
            side_rows.append({"candidate": name, "side": side.upper(), "trades": row[f"{side}_trades"],
                              "win_rate": f"{row[f'{side}_win_rate']:.2%}", "net_pnl": f"{row[f'{side}_net_pnl']:.2f}",
                              "avg_r": f"{row[f'{side}_avg_r']:.4f}", "total_r": f"{row[f'{side}_total_r']:.2f}",
                              "profit_factor": f"{row[f'{side}_profit_factor']:.3f}"})
    lines += ["4. BUY vs SELL comparison", pd.DataFrame(side_rows).to_string(index=False), ""]

    gap = results[["train_balanced_accuracy", "val_balanced_accuracy", "balanced_accuracy_gap"]].copy()
    gap["gap_vs_baseline"] = gap["balanced_accuracy_gap"] - gap.loc["BASELINE", "balanced_accuracy_gap"]
    lines += ["5. Train-validation gap comparison (balanced accuracy)",
              gap.apply(lambda s: s.map(lambda v: f"{v:+.4f}" if s.name == "gap_vs_baseline" else f"{v:.4f}")).to_string(),
              ""]

    rank = results[["val_balanced_accuracy", "avg_r", "delta_avg_r_vs_baseline", "delta_avg_r_se"]].copy()
    rank["rank_val_bal_acc"] = rank["val_balanced_accuracy"].rank(ascending=False).astype(int)
    rank["rank_avg_r"] = rank["avg_r"].rank(ascending=False).astype(int)
    lines += ["6. Which candidates improved versus baseline (descriptive only; not a selection)"]
    for name, row in results.iterrows():
        if name != "BASELINE":
            lines.append(f"   {name}: {row['improved_vs_baseline']}  "
                         f"(avg R {row['delta_avg_r_vs_baseline']:+.4f} vs baseline, SE {row['delta_avg_r_se']:.4f})")
    lines += ["   Descriptive ranks (1 = highest):",
              rank[["rank_val_bal_acc", "rank_avg_r"]].to_string(), ""]

    lines += ["7. Overfitting / noise warning signs (rules fixed before running)",
              f"   rules: gap > {GAP_ABSOLUTE_WARNING}; gap > baseline gap + {GAP_INCREASE_WARNING}; "
              f"avg R gain < {NOISE_SE_MULTIPLE:.0f} SE; P&L up without better balanced accuracy;",
              "   positive avg R not distinguishable from zero"]
    for name, row in results.iterrows():
        lines.append(f"   {name}: {row['overfitting_or_noise_warnings']}")
    lines.append("")

    lines += ["8. Validation is NOT the final performance estimate",
              "   Seven configurations were compared on one validation period (2026-08-20 to 2026-09-29).",
              "   Choosing the best of them on this data biases its validation result upward. No winner is",
              "   declared; any configuration worth pursuing needs walk-forward evaluation and, at the very",
              "   end, a single evaluation on the untouched test set.", "",
              "9. TEST set status",
              "   The untouched TEST set (xauusd_m5_test.csv) has not been loaded or used in any way.", "",
              "Backtest assumptions (unchanged from backtest_rf_m5.py):"]
    lines += [f"   - {w}" for w in BACKTEST_WARNINGS]
    return lines


def main() -> None:
    train, X_train, y_train = load_split(TRAIN_PATH)
    val, X_val, y_val = load_split(VALIDATION_PATH)
    validate_inputs(X_train, X_val, train, val)
    assert VALIDATION_PATH == BACKTEST_VALIDATION_PATH

    val_bt, start, end = load_validation_period(BACKTEST_VALIDATION_PATH)
    raw, features, positions, _ = load_market(start, end)
    check_against_validation(features, val_bt, RF_FEATURES)
    market = (raw, features, positions)

    rows = {}
    for name in CANDIDATES:
        params = candidate_params(name)
        model = RandomForestClassifier(**params).fit(X_train, y_train)
        trades, bt = backtest_candidate(model, market)
        if name == "BASELINE":
            assert params == RF_PARAMS, "baseline parameters differ from train_rf_m5.RF_PARAMS"
            check_baseline_reproducible(model, X_val, market, trades)
        rows[name] = {**CANDIDATES[name], **ml_metrics(model, X_train, y_train, X_val, y_val), **bt}
        print(f"finished {name}: val balanced acc {rows[name]['val_balanced_accuracy']:.4f}, "
              f"trades {bt['trades']}, avg R {bt['avg_r']:+.4f}")

    results = add_flags(pd.DataFrame.from_dict(rows, orient="index"))
    results.index.name = "candidate"

    for path in (RESULTS_PATH, REPORT_PATH):
        if path in INPUT_PATHS:
            raise RuntimeError(f"Refusing to overwrite input file {path}")
    results.to_csv(RESULTS_PATH)
    lines = build_report(results, len(X_train), len(X_val), len(features))
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("\n".join(lines))
    print(f"\nSaved results: {RESULTS_PATH}")
    print(f"Saved report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()
