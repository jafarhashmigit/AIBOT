"""Research: is the sign of the XAUUSD M15 close-to-close return 2, 4 or 8 candles ahead
walk-forward predictable from causal M15 features?

Diagnostic only. Nothing in the M5 project (model, labels, splits, features, backtester) is
changed; no trading rule is produced.

M15 candles are aggregated from the existing raw M5 bars, but only from bars up to the M5
research cutoff (end of the purge gap before the M5 test split), so no test-period bar is
ever read. A candle stamped T (bar open time, the MT5 convention of the source) exists only
if the three M5 bars T, T+5 and T+10 are all present; any other slot is rejected, never
filled. Indicators are recomputed on the M15 candles with the same causal formulas as the M5
feature pipeline (features_m5), so every feature on candle t uses candles <= t only.

Target per feature row t (candles counted in the M15 candle sequence, as the return_h features
count them): future_return_h = close[t+h] / close[t] - 1, h in {2, 4, 8}; UP if > 0, DOWN if
< 0; zero returns and unavailable t+h excluded.

Feature rows are limited to candles whose last M5 bar is at or before the M5 validation end;
candles inside the purge gap are used only as target closes (as the M5 labels do).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, roc_auc_score

from features_m5 import (
    add_atr,
    add_bollinger_bands,
    add_candle_features,
    add_return_features,
    add_rsi,
    add_time_features,
    add_trend_indicators,
    add_volume_features,
    load_and_validate,
)
from label_m5 import RAW_PATH
from research_kronos_m5 import GUARD, TEST_PATH, assert_no_test_rows, install_guards, rows_through
from research_m5_label_horizon import FIXED_RF, research_boundary
from research_rf_m5_conditional_edge import snapshot

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
M15_PATH = DATA_DIR / "xauusd_m15.csv"
RESULTS_PATH = DATA_DIR / "m15_future_return_predictability.csv"
REPORT_PATH = DATA_DIR / "m15_future_return_predictability_report.txt"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
M5 = pd.Timedelta(minutes=5)
M15 = pd.Timedelta(minutes=15)
HORIZONS = (2, 4, 8)
HORIZON_MINUTES = {2: 30, 4: 60, 8: 120}
UP, DOWN = 1, 0

BASELINE_RF = {"n_estimators": 300, "max_depth": 8, "min_samples_leaf": 50, "max_features": "sqrt",
               "max_samples": 0.5, "bootstrap": True, "class_weight": "balanced", "criterion": "gini",
               "random_state": 42, "n_jobs": -1}

M15_FEATURES = [
    # trend (scale-free)
    "close_to_ema_9", "close_to_ema_50", "ema_9_20_spread", "ema_20_50_spread",
    # MACD normalised by price
    "macd_pct", "macd_signal_pct", "macd_hist_pct",
    # oscillators / bands
    "rsi_14", "bb_percent_b", "bb_width",
    # volatility
    "atr_14_pct", "volatility_12", "volatility_48", "volatility_ratio_12_48",
    # candle shape
    "candle_body_abs_to_range", "upper_wick_to_range", "lower_wick_to_range", "candle_range_to_atr",
    # returns / momentum (in M15 candles)
    "log_return_1", "return_3", "return_6", "return_12", "roc_20",
    # tick volume (sum of the three M5 tick volumes)
    "log_tick_volume", "tick_volume_change", "tick_volume_ratio_20",
    # time / session / gaps
    "hour_utc", "weekday", "session_asia", "session_london", "session_new_york", "session_london_ny_overlap",
    "minutes_since_prev_bar",
]
FEATURE_NOTES = {
    "close_to_ema_9/50": "close / EMA(9 or 50 candles) - 1",
    "ema_9_20_spread, ema_20_50_spread": "EMA9/EMA20 - 1, EMA20/EMA50 - 1",
    "macd_pct, macd_signal_pct, macd_hist_pct": "MACD(12,26), signal(9), histogram, each divided by close",
    "rsi_14": "Wilder RSI over 14 candles",
    "bb_percent_b, bb_width": "Bollinger(20, 2): %B and band width / middle",
    "atr_14_pct": "Wilder ATR(14) / close",
    "volatility_12/48, volatility_ratio_12_48": "std of 1-candle log returns over 12/48 candles, and their ratio",
    "candle_*_to_range, candle_range_to_atr": "body/upper wick/lower wick as share of range; range / ATR14",
    "log_return_1, return_3/6/12, roc_20": "backward returns over 1, 3, 6, 12, 20 candles",
    "log_tick_volume, tick_volume_change, tick_volume_ratio_20": "log1p(volume), its 1-candle change, volume / 20-candle mean",
    "hour_utc, weekday, session_*": "from the candle timestamp, same convention and session hours as the M5 pipeline",
    "minutes_since_prev_bar": "minutes since the previous valid M15 candle (exposes closures and rejected slots)",
}
PRICE_LEVEL_COLUMNS = {"open", "high", "low", "close", "ema_9", "ema_20", "ema_50", "macd", "macd_signal", "macd_hist",
                       "bb_middle", "bb_upper", "bb_lower", "atr_14", "candle_body", "candle_body_abs", "upper_wick",
                       "lower_wick", "candle_range", "momentum_10", "momentum_20", "tick_volume"}

WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)   # same construction as the M5 windows, applied to M15 rows
WF = ["WF1", "WF2", "WF3"]

# Rules fixed before any result is seen.
MAJORITY_BALANCED_ACCURACY = 0.5
MIN_IMPROVEMENT = 0.02
MIN_WINDOWS_IMPROVED = 2
WORST_WINDOW = -0.01
MIN_MEAN_IMPROVEMENT = 0.02
BOOT_BLOCK = 96          # one trading day of M15 candles; covers the 8-candle target overlap
BOOT_DRAWS = 1000
BOOT_SEED = 42
PERMUTATION_HORIZON = 4
PERMUTATION_SEED = 42
PERMUTATION_WINDOW_TOL = 0.02
PERMUTATION_MEAN_TOL = 0.01
CORRELATION_TRIPWIRE = 0.5
TRUNCATION_FRACTIONS = (0.30, 0.55, 0.70, 0.85, 0.97)

INTEGRITY_GROUPS = {
    "existing M5 model": ["models/rf_m5_baseline.pkl"],
    "existing M5 labels": ["data/xauusd_m5_labeled.csv"],
    "existing M5 splits": ["data/xauusd_m5_train.csv", "data/xauusd_m5_validation.csv", "data/xauusd_m5_test.csv"],
    "existing M5 feature files": ["data/xauusd_m5_features.csv", "features_m5.py"],
    "existing M5 backtester": ["backtest_rf_m5.py"],
    "existing M5 raw data": ["data/xauusd_m5.csv"],
}

TEST_STATEMENT = "The untouched M5 TEST dataset was never opened, read or used."
CONCLUSION_A = "No convincing M15 walk-forward predictability found."
CONCLUSION_B = "Potential M15 walk-forward predictability found; independent confirmation required."


# --------------------------------------------------------------------------
# M15 candles
# --------------------------------------------------------------------------

def aggregate_m15(m5: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    df = m5[["time", "open", "high", "low", "close", "tick_volume"]].copy()
    df["slot"] = df["time"].dt.floor("15min")
    g = df.groupby("slot", sort=True)
    agg = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "tick_volume": g["tick_volume"].sum(), "m5_bars": g["time"].size(),
        "first_m5": g["time"].min(), "last_m5": g["time"].max(),
    }).reset_index().rename(columns={"slot": "time"})
    complete = ((agg["m5_bars"] == 3) & (agg["first_m5"] == agg["time"])
                & (agg["last_m5"] == agg["time"] + 2 * M5))
    boundary = ~complete & (agg["time"] + 2 * M5 > cutoff)
    stats = {
        "source_m5_bars": len(m5),
        "slots_with_any_m5_bar": len(agg),
        "valid_m15_candles": int(complete.sum()),
        "rejected_missing_m5_bars": int((~complete & ~boundary).sum()),
        "rejected_1_of_3_bars": int((~complete & ~boundary & (agg["m5_bars"] == 1)).sum()),
        "rejected_2_of_3_bars": int((~complete & ~boundary & (agg["m5_bars"] == 2)).sum()),
        "rejected_at_research_boundary": int(boundary.sum()),
        "m5_bars_in_rejected_slots": int(agg.loc[~complete, "m5_bars"].sum()),
    }
    m15 = agg[complete].drop(columns=["first_m5", "last_m5"]).reset_index(drop=True)
    return m15, stats


def verify_aggregation(m15: pd.DataFrame, m5: pd.DataFrame) -> None:
    """Every M15 value must equal the corresponding source M5 value - nothing filled or invented."""
    src = m5.set_index("time")
    bars = [src.reindex(m15["time"] + k * M5) for k in range(3)]
    for b in bars:
        assert b[["open", "high", "low", "close", "tick_volume"]].notna().all().all(), "M15 candle uses a missing M5 bar"
    col = {c: [b[c].to_numpy(float) for b in bars] for c in ("open", "high", "low", "close", "tick_volume")}
    assert np.array_equal(m15["open"].to_numpy(float), col["open"][0])
    assert np.array_equal(m15["close"].to_numpy(float), col["close"][2])
    assert np.array_equal(m15["high"].to_numpy(float), np.maximum.reduce(col["high"]))
    assert np.array_equal(m15["low"].to_numpy(float), np.minimum.reduce(col["low"]))
    assert np.array_equal(m15["tick_volume"].to_numpy(float), col["tick_volume"][0] + col["tick_volume"][1]
                          + col["tick_volume"][2])
    assert (m15["m5_bars"] == 3).all() and (m15["time"].dt.minute % 15 == 0).all() and (m15["time"].dt.second == 0).all()
    assert m15["time"].is_unique and m15["time"].is_monotonic_increasing
    assert (m15["high"] >= m15[["open", "close", "low"]].max(axis=1)).all()
    assert (m15["low"] <= m15[["open", "close", "high"]].min(axis=1)).all()


# --------------------------------------------------------------------------
# M15 features and targets
# --------------------------------------------------------------------------

def build_m15_features(m15: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = m15[["time", "open", "high", "low", "close", "tick_volume"]].copy()
    add_trend_indicators(df)
    add_rsi(df)
    add_bollinger_bands(df)
    add_atr(df)
    add_candle_features(df)
    add_return_features(df)
    add_volume_features(df)
    add_time_features(df)
    for col in ("macd", "macd_signal", "macd_hist"):
        df[f"{col}_pct"] = df[col] / df["close"]
    df[M15_FEATURES] = df[M15_FEATURES].replace([np.inf, -np.inf], np.nan)
    complete = df[M15_FEATURES].notna().all(axis=1)
    first = int(complete.to_numpy().argmax())
    out = df.iloc[first:]
    interior = out[M15_FEATURES].isna().any(axis=1)
    out = out[~interior].reset_index(drop=True)
    return out, {"warmup_candles": first, "interior_nan_rows_dropped": int(interior.sum())}


def target_columns(h: int) -> tuple[str, str, str]:
    return f"future_return_{h}", f"direction_{h}", f"target_time_{h}"


def add_targets(feats: pd.DataFrame, m15: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    pos = m15.set_index("time").index.get_indexer(feats["time"])
    assert (pos >= 0).all()
    close, times = m15["close"].to_numpy(float), m15["time"].to_numpy()
    out, info = feats.copy(), {}
    for h in HORIZONS:
        ret_col, dir_col, time_col = target_columns(h)
        fut = pos + h
        ok = fut <= len(m15) - 1
        ret = np.full(len(out), np.nan)
        ret[ok] = close[fut[ok]] / close[pos[ok]] - 1
        tgt = np.full(len(out), np.datetime64("NaT", "ns"))
        tgt[ok] = times[fut[ok]]
        direction = np.where(ret > 0, UP, np.where(ret < 0, DOWN, -1))
        direction[~ok] = -1
        out[ret_col], out[dir_col], out[time_col] = ret, direction, tgt
        spans_gap = ok & ((tgt - out["time"].to_numpy()) != h * M15)
        info[h] = {"unavailable": int((~ok).sum()), "zero_return": int((ok & (ret == 0)).sum()),
                   "spans_gap_or_rejected_slot": int(spans_gap.sum())}
    return out, info


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def balanced_accuracy_fast(y: np.ndarray, p: np.ndarray) -> float:
    up = y == UP
    return 0.5 * ((p[up] == UP).mean() + (p[~up] == DOWN).mean())


def block_bootstrap_ba(y: np.ndarray, p: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    n = len(y)
    n_blocks = int(np.ceil(n / BOOT_BLOCK))
    out = np.empty(BOOT_DRAWS)
    for d in range(BOOT_DRAWS):
        starts = rng.integers(0, n - BOOT_BLOCK + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(BOOT_BLOCK)).ravel()[:n]
        out[d] = balanced_accuracy_fast(y[idx], p[idx])
    return out


def fit(train: pd.DataFrame, y: np.ndarray) -> RandomForestClassifier:
    X = train[M15_FEATURES]
    assert list(X.columns) == M15_FEATURES and np.isfinite(X.to_numpy(float)).all()
    return RandomForestClassifier(**BASELINE_RF).fit(X, y)


def score(model, ev: pd.DataFrame, y: np.ndarray, majority: int) -> tuple[dict, np.ndarray]:
    X = ev[M15_FEATURES]
    pred = model.predict(X)
    half = len(X) // 2
    assert (model.predict(X.iloc[:half]) == pred[:half]).all(), "predictions depend on later rows"
    proba_up = model.predict_proba(X)[:, list(model.classes_).index(UP)]
    cm = confusion_matrix(y, pred, labels=[DOWN, UP])
    ba = balanced_accuracy_score(y, pred)
    return {
        "eval_rows": len(y), "accuracy": accuracy_score(y, pred), "balanced_accuracy": ba,
        "roc_auc": roc_auc_score(y, proba_up) if len(np.unique(y)) == 2 else np.nan,
        "up_pct": (y == UP).mean() * 100, "down_pct": (y == DOWN).mean() * 100, "pred_up_pct": (pred == UP).mean() * 100,
        "cm_true_down_pred_down": int(cm[0, 0]), "cm_true_down_pred_up": int(cm[0, 1]),
        "cm_true_up_pred_down": int(cm[1, 0]), "cm_true_up_pred_up": int(cm[1, 1]),
        "majority_class_train": "UP" if majority == UP else "DOWN",
        "majority_accuracy": (y == majority).mean(),
        "majority_balanced_accuracy": MAJORITY_BALANCED_ACCURACY,
        "improvement_vs_0_5": ba - MAJORITY_BALANCED_ACCURACY,
    }, pred


def window_data(data: pd.DataFrame, h: int, a, b, last: bool):
    _, dir_col, time_col = target_columns(h)
    valid = data[data[dir_col] >= 0]
    train = valid[valid[time_col] + M15 <= a]
    in_win = (valid["time"] >= a) & ((valid["time"] <= b) if last else (valid["time"] < b))
    ev = valid[in_win]
    assert train["time"].max() < a and (train[time_col] + M15).max() <= a, "training target reaches the window"
    assert ev["time"].min() >= a and ev["time"].is_monotonic_increasing and ev["time"].is_unique
    return train, ev, train[dir_col].to_numpy(int), ev[dir_col].to_numpy(int)


def run_walk_forward(data, wf_windows):
    rows, boot, leak = [], {}, []
    rng = np.random.default_rng(BOOT_SEED)
    for h in HORIZONS:
        boot[h] = []
        for i, (a, b) in enumerate(wf_windows):
            train, ev, y_tr, y_ev = window_data(data, h, a, b, i == len(wf_windows) - 1)
            majority = UP if (y_tr == UP).mean() >= 0.5 else DOWN
            metrics, pred = score(fit(train, y_tr), ev, y_ev, majority)
            boot[h].append(block_bootstrap_ba(y_ev, pred, rng) - MAJORITY_BALANCED_ACCURACY)
            _, _, time_col = target_columns(h)
            rows.append({"horizon": f"H{h}", "horizon_candles": h, "horizon_minutes": HORIZON_MINUTES[h],
                         "window": WF[i], "window_start": a, "window_end": b, "train_rows": len(train),
                         "train_start": train["time"].min(), "train_end": train["time"].max(),
                         "train_last_target_candle": train[time_col].max(), "train_up_pct": (y_tr == UP).mean() * 100,
                         "eval_start": ev["time"].min(), "eval_end": ev["time"].max(), **metrics})
            leak.append((h, WF[i], train["time"].max(), train[time_col].max(), ev["time"].min()))
    return pd.DataFrame(rows), boot, leak


def summarize(results, boot) -> pd.DataFrame:
    out = []
    for h in HORIZONS:
        r = results[results["horizon_candles"] == h]
        imp = r["improvement_vs_0_5"].to_numpy()
        lo, hi = np.percentile(np.mean(boot[h], axis=0), [2.5, 97.5])
        rules = {
            "rule_windows_improved": int((imp >= MIN_IMPROVEMENT).sum()) >= MIN_WINDOWS_IMPROVED,
            "rule_worst_window": bool(imp.min() >= WORST_WINDOW),
            "rule_mean_improvement": bool(imp.mean() >= MIN_MEAN_IMPROVEMENT),
            "rule_ci_excludes_zero": bool(lo > 0 or hi < 0),
        }
        out.append({"horizon": f"H{h}", "horizon_candles": h,
                    "wf_mean_balanced_accuracy": r["balanced_accuracy"].mean(),
                    "wf_std_balanced_accuracy": r["balanced_accuracy"].std(ddof=1),
                    "wf_mean_improvement": imp.mean(), "wf_improvement_ci95_low": lo, "wf_improvement_ci95_high": hi,
                    "wf_positive_improvements": int((imp > 0).sum()), "wf_negative_improvements": int((imp < 0).sum()),
                    "wf_windows_improved_ge_0_02": int((imp >= MIN_IMPROVEMENT).sum()),
                    "wf_mean_roc_auc": r["roc_auc"].mean(), **rules,
                    "verdict": "Potentially predictable" if all(rules.values())
                               else "No convincing M15 walk-forward predictability."})
    return pd.DataFrame(out)


def permutation_check(data, wf_windows):
    rng = np.random.default_rng(PERMUTATION_SEED)
    rows = []
    for i, (a, b) in enumerate(wf_windows):
        train, ev, y_tr, y_ev = window_data(data, PERMUTATION_HORIZON, a, b, i == len(wf_windows) - 1)
        y_shuffled = rng.permutation(y_tr)
        assert (np.bincount(y_shuffled) == np.bincount(y_tr)).all() and not (y_shuffled == y_tr).all()
        majority = UP if (y_tr == UP).mean() >= 0.5 else DOWN
        metrics, _ = score(fit(train, y_shuffled), ev, y_ev, majority)
        rows.append({"window": WF[i], **metrics})
    perm = pd.DataFrame(rows)
    ok = bool((perm["improvement_vs_0_5"].abs() <= PERMUTATION_WINDOW_TOL).all()
              and abs(perm["improvement_vs_0_5"].mean()) <= PERMUTATION_MEAN_TOL)
    return perm, ok


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------

def recompute_from_truncated_m5(m5, feats, cutoff) -> list[str]:
    """Rebuild candles and features from M5 bars truncated at several cutoffs; every feature
    row whose candle is complete before the cutoff must be identical."""
    points = [feats["time"].iloc[int(len(feats) * q)] + pd.Timedelta(minutes=7) for q in TRUNCATION_FRACTIONS]
    done = []
    for t in points:
        m15_t, _ = aggregate_m15(m5[m5["time"] <= t], cutoff)
        feats_t, _ = build_m15_features(m15_t)
        common = feats.loc[feats["time"] + 2 * M5 <= t, "time"]
        rebuilt = feats_t.set_index("time").reindex(common)[M15_FEATURES]
        assert rebuilt.notna().all().all(), f"rows missing after truncating M5 at {t}"
        assert np.allclose(rebuilt.to_numpy(float), feats.set_index("time").loc[common, M15_FEATURES].to_numpy(float),
                           rtol=1e-9, atol=1e-12), f"features change when M5 bars after {t} are removed"
        assert not (feats_t["time"] + 2 * M5 > t).any(), "incomplete candle created at a truncation point"
        done.append(t.strftime(TIME_FORMAT))
    return done


def backward_return_check(feats, m15) -> None:
    pos = m15.set_index("time").index.get_indexer(feats["time"])
    close = m15["close"].to_numpy(float)
    for h in (3, 6, 12, 20):
        col = "roc_20" if h == 20 else f"return_{h}"
        ok = pos - h >= 0
        assert np.allclose(feats.loc[ok, col].to_numpy(float), close[pos[ok]] / close[pos[ok] - h] - 1,
                           rtol=1e-9, atol=1e-12), f"{col} is not a backward return"
    ok = pos - 1 >= 0
    assert np.allclose(feats.loc[ok, "log_return_1"].to_numpy(float), np.log(close[pos[ok]] / close[pos[ok] - 1]))


def max_feature_target_corr(data) -> tuple[float, str]:
    best, name = 0.0, ""
    for h in HORIZONS:
        ret_col = target_columns(h)[0]
        v = data[data[ret_col].notna()]
        for c in M15_FEATURES:
            x = v[c].astype(float)
            if x.std() == 0:
                continue
            rho = abs(np.corrcoef(x, v[ret_col])[0, 1])
            if rho > best:
                best, name = rho, f"{c} vs {ret_col}"
    return best, name


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def f(v, spec=".4f") -> str:
    return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else format(v, spec)


def build_report(ctx: dict) -> list[str]:
    s, results, summary, perm = ctx["agg_stats"], ctx["results"], ctx["summary"], ctx["perm"]
    L = ["XAUUSD M15 future-return direction predictability (walk-forward research; no trading rule)", "=" * 80,
         TEST_STATEMENT, ""]
    L += ["1. M15 DATA CONSTRUCTION",
          f"   Source: src/data/xauusd_m5.csv, read only through the M5 research cutoff {ctx['cutoff']} (end of the",
          "   purge gap before the M5 test split); no later M5 bar was read or aggregated.",
          "   Each 15-minute slot [T, T+15) is a candle only if the M5 bars T, T+5 and T+10 are all present:",
          "   open = first M5 open, high = max M5 high, low = min M5 low, close = last M5 close, tick_volume = sum.",
          "   Slots with 1 or 2 bars (missing bars, session open/close inside the slot) are rejected - never filled,",
          "   forward-filled or fabricated. Timestamps keep the source convention (bar open time, the same clock",
          "   the M5 pipeline labels UTC).",
          f"   Source M5 bars: {s['source_m5_bars']}  ({ctx['m5_start']} -> {ctx['m5_end']})",
          f"   15-minute slots containing any M5 bar: {s['slots_with_any_m5_bar']}",
          f"   Valid M15 candles created: {s['valid_m15_candles']}  ({ctx['m15_start']} -> {ctx['m15_end']})",
          f"   Rejected because of missing M5 bars/gaps: {s['rejected_missing_m5_bars']} (1 of 3 bars: "
          f"{s['rejected_1_of_3_bars']}, 2 of 3 bars: {s['rejected_2_of_3_bars']})",
          f"   Rejected because the slot extends past the research cutoff: {s['rejected_at_research_boundary']}",
          f"   M5 bars falling in rejected slots (unused): {s['m5_bars_in_rejected_slots']}",
          "   Saved to src/data/xauusd_m15.csv (valid candles only).", ""]
    L += ["2. M15 FEATURES (recomputed on M15 candles with the M5 pipeline's causal formulas; no M5 value copied;",
          f"   no price-level column). Warm-up candles dropped: {ctx['feat_stats']['warmup_candles']}; interior rows with",
          f"   undefined features dropped: {ctx['feat_stats']['interior_nan_rows_dropped']}. Feature rows: {ctx['n_feature_rows']}"
          f" ({ctx['feat_start']} -> {ctx['feat_end']}), limited to candles whose last M5 bar is <= the M5",
          f"   validation end {ctx['val_end']}.",
          f"   Feature list ({len(M15_FEATURES)}):"]
    L += [f"     {', '.join(M15_FEATURES[i:i + 6])}" for i in range(0, len(M15_FEATURES), 6)]
    L += [f"   - {k}: {v}" for k, v in FEATURE_NOTES.items()]
    L += [f"   Excluded price-level columns: {', '.join(sorted(PRICE_LEVEL_COLUMNS))}", ""]
    L += ["3. TARGETS (candles counted in the valid M15 candle sequence)"]
    for h in HORIZONS:
        i = ctx["target_info"][h]
        L.append(f"   H{h} (~{HORIZON_MINUTES[h]} min): future_return_{h} = close[t+{h}] / close[t] - 1; UP if > 0, DOWN if < 0. "
                 f"Excluded: unavailable {i['unavailable']}, zero return {i['zero_return']}. Kept but spanning a closure or "
                 f"rejected slot: {i['spans_gap_or_rejected_slot']}")
    L += ["   No WAIT class. Future returns, directions and target times are never model inputs.", ""]
    L += ["4. MODEL AND WALK-FORWARD",
          "   Fresh RandomForestClassifier per horizon and window: " + ", ".join(f"{k}={v!r}" for k, v in BASELINE_RF.items()),
          "   Windows: three equal-row, consecutive, non-overlapping windows starting at 55%, 70% and 85% of the M15",
          "   feature rows (the construction used for the M5 windows, recomputed for M15 - not the M5 dates). The",
          "   first 55% is the minimum training history. WF3 includes its end row.",
          "   Training: all earlier feature rows whose target candle closes at or before the window start (purged)."]
    L += [f"   {w}: {a} -> {b}" for w, (a, b) in zip(WF, ctx["wf_windows"])] + [""]
    L += ["5. RESULTS - every horizon x window (impr = balanced accuracy - 0.5; majority-class balanced accuracy = 0.5)",
          f"   {'H':<4}{'win':<5}{'train':>7} {'eval':>6} {'acc':>7} {'bal_acc':>8} {'AUC':>7} {'UP%':>6} {'DOWN%':>6} "
          f"{'predUP%':>8} {'maj':>5} {'maj_acc':>8} {'maj_BA':>7} {'impr':>8}   confusion [[DD DU] [UD UU]]"]
    for _, r in results.iterrows():
        L.append(f"   {r.horizon:<4}{r.window:<5}{r.train_rows:>7} {r.eval_rows:>6} {r.accuracy:>7.4f} "
                 f"{r.balanced_accuracy:>8.4f} {f(r.roc_auc):>7} {r.up_pct:>6.2f} {r.down_pct:>6.2f} {r.pred_up_pct:>8.2f} "
                 f"{r.majority_class_train:>5} {r.majority_accuracy:>8.4f} {r.majority_balanced_accuracy:>7.4f} "
                 f"{r.improvement_vs_0_5:>+8.4f}   [[{r.cm_true_down_pred_down} {r.cm_true_down_pred_up}] "
                 f"[{r.cm_true_up_pred_down} {r.cm_true_up_pred_up}]]")
    L += ["   (DD = true DOWN predicted DOWN, DU = true DOWN predicted UP, etc.; maj = training-majority class.)", ""]
    L += ["6. HORIZON SUMMARY AND PREDEFINED DECISION RULE",
          f"   Potentially predictable only if: improvement >= +{MIN_IMPROVEMENT} in >= {MIN_WINDOWS_IMPROVED} of 3 windows; no",
          f"   window below {WORST_WINDOW}; WF mean improvement >= +{MIN_MEAN_IMPROVEMENT}; 95% block-bootstrap CI of the mean",
          f"   improvement excludes zero ({BOOT_BLOCK}-candle blocks within each window, {BOOT_DRAWS} draws, seed {BOOT_SEED}).",
          f"   {'H':<4}{'WF mean BA':>11} {'WF std':>8} {'mean impr':>10} {'CI95 mean impr':>20} {'+/-':>4} "
          f"{'>=0.02':>7} {'mean AUC':>9}  rules (windows/worst/mean/CI)  verdict"]
    for _, x in summary.iterrows():
        rules = "/".join("Y" if x[c] else "N" for c in ("rule_windows_improved", "rule_worst_window",
                                                         "rule_mean_improvement", "rule_ci_excludes_zero"))
        L.append(f"   {x.horizon:<4}{x.wf_mean_balanced_accuracy:>11.4f} {x.wf_std_balanced_accuracy:>8.4f} "
                 f"{x.wf_mean_improvement:>+10.4f} [{x.wf_improvement_ci95_low:+.4f}, {x.wf_improvement_ci95_high:+.4f}] "
                 f"{x.wf_positive_improvements}/{x.wf_negative_improvements} {x.wf_windows_improved_ge_0_02:>7} "
                 f"{x.wf_mean_roc_auc:>9.4f}  {rules:<29}  {x.verdict}")
    L += ["   All three horizons are predefined candidates evaluated once; none was selected and retested. CIs are not",
          "   adjusted for three horizons (adjustment would only widen them).", ""]
    L += [f"7. PERMUTATION SANITY CHECK (H{PERMUTATION_HORIZON}; training targets shuffled with seed {PERMUTATION_SEED})"]
    for _, r in perm.iterrows():
        L.append(f"   {r.window}: balanced accuracy {r.balanced_accuracy:.4f} (improvement {r.improvement_vs_0_5:+.4f}), "
                 f"AUC {f(r.roc_auc)}, predicted UP {r.pred_up_pct:.1f}%")
    L += [f"   Pre-declared pass: every window within +/-{PERMUTATION_WINDOW_TOL} of 0.5 and mean within +/-{PERMUTATION_MEAN_TOL}: "
          + ("PASS - shuffled-label performance collapses to 0.5" if ctx["perm_ok"]
             else "FAIL - shuffled labels did not collapse; results are suspect"), ""]
    L += ["8. LEAKAGE CHECKS"] + [f"   {c}" for c in ctx["checks"]]
    L += ["   Per-window purge (latest training row / latest training target candle / first evaluation row):"]
    L += [f"     H{h} {w}: {a} / {b} / {c}" for h, w, a, b, c in ctx["leak"]] + [""]
    L += ["9. FILE INTEGRITY (recorded before the run, verified after; new files excluded)"]
    for name, files in INTEGRITY_GROUPS.items():
        for k in files:
            L.append(f"   {k:<36} {ctx['hashes'][k][0]:<19} {ctx['hashes'][k][1]}")
        L.append(f"   [PASS] {name} unchanged")
    L += [f"   [PASS] existing project files unchanged: all {len(ctx['hashes'])} files in src/, src/data/, src/models/.",
          "   New files: " + ", ".join(ctx["new_files"]), ""]
    L += ["10. TEST-DATA SAFETY",
          f"   {TEST_STATEMENT}",
          f"   Audit hook: {GUARD['test_open_attempts']} attempts to open xauusd_m5_test.csv. CSVs opened by pandas: "
          f"{', '.join(sorted({p.name for p in GUARD['csv_reads']}))}.",
          f"   The raw M5 read stopped at {GUARD['cutoff']}; every loaded frame, candle and target is <= that time.",
          "   Integrity hashing read no byte after the cutoff (prefix hashes; the test CSV by size/mtime only).", ""]
    L += ["11. LIMITATIONS",
          "   - About 7.5 months of data; three windows of roughly five weeks each, so effects below ~0.01-0.02",
          "     balanced accuracy cannot be separated from noise, and longer regimes are not covered.",
          "   - Overlapping h-candle targets make neighbouring rows dependent; the block bootstrap mitigates this",
          "     but ignores model-fitting variance (single seed).",
          "   - The M15 history and windows overlap the period used to develop the M5 project, so this is not a",
          "     fully independent sample.",
          "   - Direction-only targets ignore magnitude, spread and costs; directional skill would not imply a",
          "     profitable strategy, and none is claimed.",
          "   - Timestamps/sessions follow the existing M5 convention (server clock labelled UTC) unchanged.",
          "", "Conclusion:", ctx["conclusion"]]
    return L


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    new_files = [M15_PATH, RESULTS_PATH, REPORT_PATH]
    for path in new_files:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    skip = {p.resolve() for p in new_files} | {Path(__file__).resolve()}

    _, val_end, cutoff = research_boundary()
    cutoff_str = cutoff.strftime(TIME_FORMAT)
    hashes_before = snapshot(skip, cutoff_str)
    install_guards()
    GUARD["cutoff"] = cutoff_str
    GUARD["safe_nrows"][RAW_PATH.resolve()] = rows_through(RAW_PATH, cutoff_str)
    assert FIXED_RF == BASELINE_RF, "baseline RF parameters differ"
    assert len(set(M15_FEATURES)) == len(M15_FEATURES) and not PRICE_LEVEL_COLUMNS & set(M15_FEATURES)

    m5 = load_and_validate(RAW_PATH)
    m5 = m5[m5["time"] <= cutoff].reset_index(drop=True)
    assert_no_test_rows(m5)
    assert m5["time"].is_unique and m5["time"].is_monotonic_increasing

    m15, agg_stats = aggregate_m15(m5, cutoff)
    verify_aggregation(m15, m5)
    feats_all, feat_stats = build_m15_features(m15)
    feats = feats_all[feats_all["time"] + 2 * M5 <= val_end].reset_index(drop=True)
    data, target_info = add_targets(feats, m15)
    print(f"M15 candles: {agg_stats['valid_m15_candles']} valid, {agg_stats['rejected_missing_m5_bars']} rejected "
          f"(+{agg_stats['rejected_at_research_boundary']} at boundary); feature rows {len(feats)}")

    target_cols = {c for h in HORIZONS for c in target_columns(h)}
    assert not target_cols & set(M15_FEATURES)
    assert not any(c.startswith(("future_", "direction_", "target")) for c in M15_FEATURES)
    for h in HORIZONS:
        _, _, tc = target_columns(h)
        ok = data[tc].notna()
        assert (data.loc[ok, tc] > data.loc[ok, "time"]).all() and (data.loc[ok, tc] + 2 * M5 <= cutoff).all()
    backward_return_check(feats, m15)
    truncations = recompute_from_truncated_m5(m5, feats, cutoff)
    corr, corr_name = max_feature_target_corr(data)
    assert corr < CORRELATION_TRIPWIRE, f"feature/target correlation {corr:.3f} ({corr_name}) suggests leakage"
    print(f"leakage checks passed (max |corr| feature vs future return {corr:.4f})")

    times = data["time"]
    starts = [times.iloc[int(len(times) * q)] for q in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else times.iloc[-1]) for i in range(len(starts))]
    assert all(a < b for a, b in wf_windows) and all(wf_windows[i][1] == wf_windows[i + 1][0] for i in range(2))

    results, boot, leak = run_walk_forward(data, wf_windows)
    summary = summarize(results, boot)
    perm, perm_ok = permutation_check(data, wf_windows)
    conclusion = CONCLUSION_B if (summary["verdict"] == "Potentially predictable").any() else CONCLUSION_A

    hashes_after = snapshot(skip, cutoff_str)
    changed = sorted(k for k in set(hashes_before) | set(hashes_after) if hashes_before.get(k) != hashes_after.get(k))
    if changed:
        raise AssertionError(f"existing files changed: {changed}")
    for files in INTEGRITY_GROUPS.values():
        assert all(hashes_before[k] == hashes_after[k] for k in files)
    assert GUARD["test_open_attempts"] == 0 and TEST_PATH.resolve() not in GUARD["csv_reads"]

    checks = [
        f"[PASS] No future return in any feature: target columns are disjoint from the {len(M15_FEATURES)} features; "
        "return_3/6/12, roc_20 and log_return_1 equal BACKWARD returns over the M15 candle sequence on every row; "
        f"max |corr(feature, future return)| = {corr:.4f} ({corr_name}) < {CORRELATION_TRIPWIRE}.",
        "[PASS] No target column used as a feature: every fit uses exactly the M15 feature list (asserted).",
        f"[PASS] All features backward-looking / no future bars as features: candles and features rebuilt from M5 bars "
        f"truncated at {', '.join(truncations)} equal the stored rows for every candle completed before each cutoff, "
        "and no incomplete candle appears at a truncation point; predictions on a prefix equal those on the full window.",
        "[PASS] Training timestamps strictly before evaluation timestamps in every horizon x window (asserted).",
        "[PASS] Training target horizons never cross into the evaluation window: every training target candle closes "
        "at or before the window start (asserted; listed below).",
        f"[PASS] No test dataset opened: audit hook recorded {GUARD['test_open_attempts']} attempts; raw M5 read "
        f"capped at {cutoff_str}.",
        "[PASS] No duplicate M15 timestamps; M5 and M15 timestamps strictly chronological.",
        "[PASS] Aggregation never uses incomplete candles: every M15 candle has exactly the M5 bars T, T+5, T+10.",
        "[PASS] No fabricated/forward-filled OHLC: every M15 open/high/low/close/volume equals the first open, max "
        "high, min low, last close and summed volume of its three source M5 bars; no NaN filled anywhere.",
        "[PASS] Feature rows end with the last candle completed by the M5 validation end; purge-gap candles serve "
        "only as target closes.",
    ]
    ctx = {
        "agg_stats": agg_stats, "feat_stats": feat_stats, "target_info": target_info, "results": results,
        "summary": summary, "perm": perm, "perm_ok": perm_ok, "checks": checks, "leak": leak, "hashes": hashes_after,
        "wf_windows": wf_windows, "conclusion": conclusion, "cutoff": cutoff_str, "val_end": val_end,
        "m5_start": m5["time"].iloc[0], "m5_end": m5["time"].iloc[-1], "m15_start": m15["time"].iloc[0],
        "m15_end": m15["time"].iloc[-1], "n_feature_rows": len(feats), "feat_start": feats["time"].iloc[0],
        "feat_end": feats["time"].iloc[-1],
        "new_files": ["src/research_m15_future_return_predictability.py"]
                     + [f"src/data/{p.name}" for p in new_files],
    }
    lines = build_report(ctx)
    assert lines[-1] in (CONCLUSION_A, CONCLUSION_B)

    m15.drop(columns="m5_bars").to_csv(M15_PATH, index=False, date_format=TIME_FORMAT)
    results.merge(summary, on=["horizon", "horizon_candles"], how="left").to_csv(
        RESULTS_PATH, index=False, date_format=TIME_FORMAT)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert snapshot(skip, cutoff_str) == hashes_before, "existing files changed while writing outputs"

    print("\nFINAL SUMMARY")
    print(f"  M5 source bars {agg_stats['source_m5_bars']}; M15 valid {agg_stats['valid_m15_candles']}, rejected "
          f"{agg_stats['rejected_missing_m5_bars']} (+{agg_stats['rejected_at_research_boundary']} at boundary)")
    print("  WF windows: " + "; ".join(f"{w} {a} -> {b}" for w, (a, b) in zip(WF, wf_windows)))
    for _, x in summary.iterrows():
        r = results[results["horizon"] == x.horizon]
        print(f"  {x.horizon}: balanced accuracy " + ", ".join(f"{w} {v:.4f}" for w, v in zip(r.window, r.balanced_accuracy))
              + f"; mean improvement {x.wf_mean_improvement:+.4f} [CI {x.wf_improvement_ci95_low:+.4f}, "
              f"{x.wf_improvement_ci95_high:+.4f}] -> {x.verdict}")
    print(f"  permutation check (H{PERMUTATION_HORIZON}): " + ", ".join(f"{v:.4f}" for v in perm["balanced_accuracy"])
          + f" -> {'PASS' if perm_ok else 'FAIL'}")
    print(f"  test data opened: no ({GUARD['test_open_attempts']} attempts); existing files changed: none "
          f"({len(hashes_before)} checked)")
    print(f"  conclusion: {conclusion}")
    print("  outputs: " + ", ".join(str(p) for p in new_files))


if __name__ == "__main__":
    main()
