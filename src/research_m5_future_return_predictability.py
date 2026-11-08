"""Research: is the sign of the XAUUSD M5 close-to-close return 3, 6 or 12 bars ahead
walk-forward predictable from the existing 30 RF features?

Diagnostic only. The existing RF model, labels, splits, features and backtest are not
changed; no trading rule is produced.

Target (per feature row at bar t, bars counted in the raw M5 bar sequence exactly as the
existing return_h features and triple-barrier labels count them):
    future_return_h = close[t+h] / close[t] - 1,  h in {3, 6, 12}
    UP = future_return_h > 0, DOWN = future_return_h < 0; rows with a zero return or with
    bar t+h unavailable are excluded.

For each horizon and each of the three established walk-forward windows a fresh RF with the
baseline parameters is trained on every earlier feature row whose target bar t+h lies
strictly before the window start (expanding window, purged), and evaluated on the window.
All three horizons are pre-declared candidates; no horizon is selected and retested.

Test safety reuses the research_kronos_m5 guards (audit hook that raises on any attempt to
open the test CSV; raw/feature/labeled reads capped at the last purge-gap bar). File
integrity reuses the cutoff-limited hashing of research_rf_m5_conditional_edge (no byte after
the research cutoff is read; the test CSV is checked by size/mtime only).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, roc_auc_score

from features_m5 import BAR_MINUTES, build_features
from label_m5 import FEATURES_PATH, RAW_PATH, TARGET_COLUMN
from research_kronos_m5 import GUARD, TEST_PATH, assert_no_test_rows, install_guards, rows_through
from research_m5_label_horizon import FIXED_RF, load_research_data, research_boundary
from research_rf_m5_conditional_edge import snapshot
from train_rf_m5 import FORBIDDEN_INPUTS, MODEL_PATH, RF_FEATURES, RF_PARAMS, TRAIN_PATH, VALIDATION_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
LABELED_PATH = DATA_DIR / "xauusd_m5_labeled.csv"
RESULTS_PATH = DATA_DIR / "m5_future_return_predictability.csv"
REPORT_PATH = DATA_DIR / "m5_future_return_predictability_report.txt"

BAR = pd.Timedelta(minutes=BAR_MINUTES)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
HORIZONS = (3, 6, 12)
UP, DOWN = 1, 0

EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
WF = ["WF1", "WF2", "WF3"]

# Rules fixed before any result is seen.
MAJORITY_BALANCED_ACCURACY = 0.5   # always predicting one class, two classes
MIN_IMPROVEMENT = 0.02
MIN_WINDOWS_IMPROVED = 2
WORST_WINDOW = -0.01
MIN_MEAN_IMPROVEMENT = 0.02
BOOT_BLOCK = 288                   # one trading day of M5 bars; covers the 12-bar target overlap
BOOT_DRAWS = 1000
BOOT_SEED = 42
PERMUTATION_HORIZON = 6
PERMUTATION_SEED = 42
PERMUTATION_WINDOW_TOL = 0.02      # |shuffled balanced accuracy - 0.5| per window
PERMUTATION_MEAN_TOL = 0.01        # |mean shuffled improvement|
CORRELATION_TRIPWIRE = 0.5         # |corr(feature, future return)| above this flags leakage
TRUNCATION_POINTS = 4

KEY_FILES = ["models/rf_m5_baseline.pkl", "data/xauusd_m5_train.csv", "data/xauusd_m5_validation.csv",
             "data/xauusd_m5_labeled.csv", "data/xauusd_m5_features.csv", "data/xauusd_m5.csv",
             "data/xauusd_m5_test.csv"]
INTEGRITY_GROUPS = {
    "existing model": ["models/rf_m5_baseline.pkl"],
    "existing labels": ["data/xauusd_m5_labeled.csv"],
    "existing splits": ["data/xauusd_m5_train.csv", "data/xauusd_m5_validation.csv", "data/xauusd_m5_test.csv"],
    "existing feature file": ["data/xauusd_m5_features.csv"],
    "existing raw data file": ["data/xauusd_m5.csv"],
}

TEST_STATEMENT = "The untouched TEST dataset was never opened, read or used."
CONCLUSION_A = "No convincing walk-forward predictability found."
CONCLUSION_B = "Potential walk-forward predictability found; independent confirmation required."


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------

def target_columns(h: int) -> tuple[str, str]:
    return f"future_return_{h}", f"direction_{h}"


def add_targets(features: pd.DataFrame, raw: pd.DataFrame, positions: np.ndarray) -> tuple[pd.DataFrame, dict]:
    close, times = raw["close"].to_numpy(float), raw["time"].to_numpy()
    out, info = features.copy(), {}
    for h in HORIZONS:
        ret_col, dir_col = target_columns(h)
        fut = positions + h
        ok = fut <= len(raw) - 1
        ret = np.full(len(out), np.nan)
        ret[ok] = close[fut[ok]] / close[positions[ok]] - 1
        tgt_time = np.full(len(out), np.datetime64("NaT", "ns"))
        tgt_time[ok] = times[fut[ok]]
        direction = np.where(ret > 0, UP, np.where(ret < 0, DOWN, -1))
        direction[~ok] = -1
        out[ret_col], out[dir_col], out[f"target_time_{h}"] = ret, direction, tgt_time
        crossed = ok & ((tgt_time - out["time"].to_numpy()) != h * BAR)
        info[h] = {"unavailable": int((~ok).sum()), "zero_return": int((ok & (ret == 0)).sum()),
                   "crosses_market_gap": int(crossed.sum())}
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
    X = train[RF_FEATURES]
    assert list(X.columns) == RF_FEATURES and np.isfinite(X.to_numpy(float)).all()
    return RandomForestClassifier(**FIXED_RF).fit(X, y)


def score(model, ev: pd.DataFrame, y: np.ndarray, majority: int) -> tuple[dict, np.ndarray]:
    X = ev[RF_FEATURES]
    pred = model.predict(X)
    half = len(X) // 2
    assert (model.predict(X.iloc[:half]) == pred[:half]).all(), "predictions depend on later rows"
    proba_up = model.predict_proba(X)[:, list(model.classes_).index(UP)]
    cm = confusion_matrix(y, pred, labels=[DOWN, UP])
    ba = balanced_accuracy_score(y, pred)
    return {
        "eval_rows": len(y),
        "accuracy": accuracy_score(y, pred),
        "balanced_accuracy": ba,
        "roc_auc": roc_auc_score(y, proba_up) if len(np.unique(y)) == 2 else np.nan,
        "up_pct": (y == UP).mean() * 100,
        "down_pct": (y == DOWN).mean() * 100,
        "pred_up_pct": (pred == UP).mean() * 100,
        "cm_true_down_pred_down": int(cm[0, 0]), "cm_true_down_pred_up": int(cm[0, 1]),
        "cm_true_up_pred_down": int(cm[1, 0]), "cm_true_up_pred_up": int(cm[1, 1]),
        "majority_class_train": "UP" if majority == UP else "DOWN",
        "majority_accuracy": (y == majority).mean(),
        "majority_balanced_accuracy": MAJORITY_BALANCED_ACCURACY,
        "improvement_vs_majority": ba - MAJORITY_BALANCED_ACCURACY,
        "accuracy_improvement_vs_majority": accuracy_score(y, pred) - (y == majority).mean(),
    }, pred


def window_data(data: pd.DataFrame, h: int, a, b, last: bool):
    _, dir_col = target_columns(h)
    valid = data[data[dir_col] >= 0]
    train = valid[valid[f"target_time_{h}"] < a]
    in_win = (valid["time"] >= a) & ((valid["time"] <= b) if last else (valid["time"] < b))
    ev = valid[in_win]
    assert train["time"].max() < a and train[f"target_time_{h}"].max() < a, "training target reaches the window"
    assert ev["time"].min() >= a and ev["time"].is_monotonic_increasing and ev["time"].is_unique
    return train, ev, train[dir_col].to_numpy(int), ev[dir_col].to_numpy(int)


def run_walk_forward(data: pd.DataFrame, wf_windows) -> tuple[pd.DataFrame, dict, list[dict]]:
    rows, boot, leak = [], {}, []
    rng = np.random.default_rng(BOOT_SEED)
    for h in HORIZONS:
        boot[h] = []
        for i, (a, b) in enumerate(wf_windows):
            last = i == len(wf_windows) - 1
            train, ev, y_tr, y_ev = window_data(data, h, a, b, last)
            majority = UP if (y_tr == UP).mean() >= 0.5 else DOWN
            model = fit(train, y_tr)
            metrics, pred = score(model, ev, y_ev, majority)
            boot[h].append(block_bootstrap_ba(y_ev, pred, rng) - MAJORITY_BALANCED_ACCURACY)
            rows.append({"horizon": f"H{h}", "horizon_bars": h, "window": WF[i], "window_start": a,
                         "window_end": b, "train_rows": len(train), "train_start": train["time"].min(),
                         "train_end": train["time"].max(), "train_last_target_bar": train[f"target_time_{h}"].max(),
                         "train_up_pct": (y_tr == UP).mean() * 100, "eval_start": ev["time"].min(),
                         "eval_end": ev["time"].max(), **metrics})
            leak.append({"h": h, "window": WF[i], "train_end": train["time"].max(),
                         "train_target_end": train[f"target_time_{h}"].max(), "eval_start": ev["time"].min()})
    return pd.DataFrame(rows), boot, leak


def summarize(results: pd.DataFrame, boot: dict) -> pd.DataFrame:
    out = []
    for h in HORIZONS:
        r = results[results["horizon_bars"] == h]
        imp = r["improvement_vs_majority"].to_numpy()
        draws = np.mean(boot[h], axis=0)
        lo, hi = np.percentile(draws, [2.5, 97.5])
        checks = {
            "rule_windows_improved": int((imp >= MIN_IMPROVEMENT).sum()) >= MIN_WINDOWS_IMPROVED,
            "rule_worst_window": bool(imp.min() >= WORST_WINDOW),
            "rule_mean_improvement": bool(imp.mean() >= MIN_MEAN_IMPROVEMENT),
            "rule_ci_excludes_zero": bool(lo > 0 or hi < 0),
        }
        out.append({"horizon": f"H{h}", "horizon_bars": h,
                    "wf_mean_balanced_accuracy": r["balanced_accuracy"].mean(),
                    "wf_std_balanced_accuracy": r["balanced_accuracy"].std(ddof=1),
                    "wf_mean_improvement": imp.mean(), "wf_improvement_ci95_low": lo, "wf_improvement_ci95_high": hi,
                    "wf_positive_improvements": int((imp > 0).sum()), "wf_negative_improvements": int((imp < 0).sum()),
                    "wf_windows_improved_ge_0_02": int((imp >= MIN_IMPROVEMENT).sum()),
                    "wf_mean_roc_auc": r["roc_auc"].mean(), **checks,
                    "verdict": ("Potentially predictable" if all(checks.values())
                                else "No convincing walk-forward predictability.")})
    return pd.DataFrame(out)


def permutation_check(data: pd.DataFrame, wf_windows) -> tuple[pd.DataFrame, bool]:
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
    ok = bool((perm["improvement_vs_majority"].abs() <= PERMUTATION_WINDOW_TOL).all()
              and abs(perm["improvement_vs_majority"].mean()) <= PERMUTATION_MEAN_TOL)
    return perm, ok


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------

def feature_causality(raw: pd.DataFrame, features: pd.DataFrame, wf_windows) -> list[str]:
    """Recompute features from raw bars truncated at several points: a feature row must not
    change when every later bar is removed."""
    points = [a for a, _ in wf_windows] + [features["time"].iloc[int(len(features) * 0.35)]]
    assert len(points) == TRUNCATION_POINTS
    lines = []
    for t in points:
        rebuilt = build_features(raw[raw["time"] <= t].reset_index(drop=True))
        rebuilt = rebuilt.set_index("time").reindex(features.loc[features["time"] <= t, "time"])
        expected = features.loc[features["time"] <= t].set_index("time")[RF_FEATURES]
        tail = expected.index[-2000:]
        assert np.allclose(rebuilt.loc[tail, RF_FEATURES].to_numpy(float), expected.loc[tail].to_numpy(float),
                           rtol=1e-9, atol=1e-12), f"features change when bars after {t} are removed"
        lines.append(str(t))
    return lines


def past_return_check(raw: pd.DataFrame, features: pd.DataFrame, positions: np.ndarray) -> None:
    close = raw["close"].to_numpy(float)
    for h in (3, 6, 12):
        ok = positions - h >= 0
        past = close[positions[ok]] / close[positions[ok] - h] - 1
        assert np.allclose(features.loc[ok, f"return_{h}"].to_numpy(float), past, rtol=1e-9, atol=1e-12), \
            f"return_{h} is not the backward-looking return"
    lr = np.log(close[positions[1:]] / close[positions[1:] - 1])
    assert np.allclose(features["log_return_1"].to_numpy(float)[1:], lr, rtol=1e-9, atol=1e-12)


def max_feature_target_corr(data: pd.DataFrame) -> tuple[float, str]:
    best, name = 0.0, ""
    for h in HORIZONS:
        ret_col, _ = target_columns(h)
        v = data[data[ret_col].notna()]
        for c in RF_FEATURES:
            x = v[c].astype(float)
            if x.std() == 0:
                continue
            rho = abs(np.corrcoef(x, v[ret_col])[0, 1])
            if rho > best:
                best, name = rho, f"{c} vs {ret_col}"
    return best, name


def check_existing_splits(features: pd.DataFrame, val_start, val_end, cutoff_str: str) -> dict:
    feats = features.set_index("time")[RF_FEATURES]
    counts = {}
    for path in (TRAIN_PATH, VALIDATION_PATH, LABELED_PATH):
        df = pd.read_csv(path)
        df["time"] = pd.to_datetime(df["time"], format=TIME_FORMAT)
        assert_no_test_rows(df.assign(time=df["time"].dt.strftime(TIME_FORMAT)))
        assert df["time"].is_unique and df["time"].is_monotonic_increasing
        within = df[df["time"] <= val_end]
        matched = feats.reindex(within["time"])
        assert matched.notna().all().all(), f"{path.name}: rows missing from the features file"
        assert np.allclose(matched.to_numpy(float), within[RF_FEATURES].to_numpy(float)), \
            f"{path.name}: feature values differ from the features file"
        counts[path.name] = (len(df), df["time"].min(), df["time"].max())
    assert counts[TRAIN_PATH.name][2] < val_start and counts[VALIDATION_PATH.name][1] == val_start
    assert counts[VALIDATION_PATH.name][2] == val_end and str(counts[LABELED_PATH.name][2]) <= cutoff_str
    return counts


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def f(v, spec=".4f") -> str:
    return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else format(v, spec)


def build_report(results, summary, perm, perm_ok, target_info, wf_windows, leak, checks, inputs, hashes,
                 integrity, conclusion) -> list[str]:
    L = ["XAUUSD M5 future-return direction predictability (walk-forward research; no trading rule)", "=" * 78,
         TEST_STATEMENT, ""]
    L += ["1. TARGET DEFINITIONS (bars counted in the raw M5 bar sequence, as for the existing return_h features)"]
    for h in HORIZONS:
        L.append(f"   H{h}: future_return_{h} = close[t+{h}] / close[t] - 1;  UP if > 0, DOWN if < 0 (no WAIT class)")
    L += ["   Excluded: rows whose bar t+h is not available inside the research boundary, and rows with an exactly",
          "   zero future return (neither UP nor DOWN). Future returns are never model inputs."]
    for h, i in target_info.items():
        L.append(f"   H{h}: unavailable {i['unavailable']}, zero return {i['zero_return']}, targets spanning a market gap "
                 f"(kept, as in the existing labels) {i['crosses_market_gap']}")
    L.append("")
    L += ["2. MODEL",
          "   Fresh RandomForestClassifier per horizon and window: " + ", ".join(f"{k}={v!r}" for k, v in FIXED_RF.items()),
          f"   Features (exactly the existing {len(RF_FEATURES)} RF_FEATURES):"]
    L += [f"     {', '.join(RF_FEATURES[i:i + 6])}" for i in range(0, len(RF_FEATURES), 6)]
    L += ["   Training: every earlier feature row whose target bar t+h is strictly before the window start",
          "   (expanding, purged). Majority baseline: always predicting the training-majority class; its balanced",
          "   accuracy is exactly 0.5 for two classes. Improvement = balanced accuracy - 0.5.", ""]
    L += ["3. WALK-FORWARD WINDOWS (unchanged from earlier experiments; WF3 includes its end bar)"]
    L += [f"   {w}: {a} -> {b}" for w, (a, b) in zip(WF, wf_windows)] + [""]

    L += ["4. RESULTS - every horizon x window"]
    hdr = (f"   {'H':<4}{'win':<5}{'train':>7} {'eval':>6} {'acc':>7} {'bal_acc':>8} {'AUC':>7} {'UP%':>6} {'DOWN%':>6} "
           f"{'predUP%':>8} {'maj':>5} {'maj_acc':>8} {'maj_BA':>7} {'impr':>8}   confusion [[DD DU] [UD UU]]")
    L.append(hdr)
    for _, r in results.iterrows():
        L.append(f"   {r.horizon:<4}{r.window:<5}{r.train_rows:>7} {r.eval_rows:>6} {r.accuracy:>7.4f} "
                 f"{r.balanced_accuracy:>8.4f} {f(r.roc_auc):>7} {r.up_pct:>6.2f} {r.down_pct:>6.2f} {r.pred_up_pct:>8.2f} "
                 f"{r.majority_class_train:>5} {r.majority_accuracy:>8.4f} {r.majority_balanced_accuracy:>7.4f} "
                 f"{r.improvement_vs_majority:>+8.4f}   [[{r.cm_true_down_pred_down} {r.cm_true_down_pred_up}] "
                 f"[{r.cm_true_up_pred_down} {r.cm_true_up_pred_up}]]")
    L += ["   (DD = true DOWN predicted DOWN, DU = true DOWN predicted UP, etc. maj = training-majority class.)", ""]

    L += ["5. HORIZON SUMMARY AND PRIMARY DECISION RULE",
          f"   Potentially predictable only if: improvement >= +{MIN_IMPROVEMENT} in >= {MIN_WINDOWS_IMPROVED} of 3 windows;",
          f"   no window below {WORST_WINDOW}; WF mean improvement >= +{MIN_MEAN_IMPROVEMENT}; 95% block-bootstrap CI of the",
          f"   mean improvement excludes zero ({BOOT_BLOCK}-bar blocks within each window, {BOOT_DRAWS} draws, seed {BOOT_SEED}).",
          f"   {'H':<4}{'WF mean BA':>11} {'WF std':>8} {'mean impr':>10} {'CI95 mean impr':>20} {'+/-':>4} "
          f"{'>=0.02':>7} {'mean AUC':>9}  rules (windows/worst/mean/CI)  verdict"]
    for _, s in summary.iterrows():
        rules = "/".join("Y" if s[c] else "N" for c in ("rule_windows_improved", "rule_worst_window",
                                                         "rule_mean_improvement", "rule_ci_excludes_zero"))
        L.append(f"   {s.horizon:<4}{s.wf_mean_balanced_accuracy:>11.4f} {s.wf_std_balanced_accuracy:>8.4f} "
                 f"{s.wf_mean_improvement:>+10.4f} [{s.wf_improvement_ci95_low:+.4f}, {s.wf_improvement_ci95_high:+.4f}] "
                 f"{s.wf_positive_improvements}/{s.wf_negative_improvements} {s.wf_windows_improved_ge_0_02:>7} "
                 f"{s.wf_mean_roc_auc:>9.4f}  {rules:<29}  {s.verdict}")
    L += ["   Three horizons are pre-declared candidates evaluated once each; no horizon was selected and retested.",
          "   The CIs are not adjusted for testing three horizons (a Bonferroni-style adjustment would only widen them).",
          ""]

    L += [f"6. PERMUTATION SANITY CHECK (H{PERMUTATION_HORIZON}; training targets shuffled with seed {PERMUTATION_SEED}, "
          "same features, parameters and windows)"]
    for _, r in perm.iterrows():
        L.append(f"   {r.window}: balanced accuracy {r.balanced_accuracy:.4f} (improvement {r.improvement_vs_majority:+.4f}), "
                 f"AUC {f(r.roc_auc)}, predicted UP {r.pred_up_pct:.1f}%")
    L += [f"   Pre-declared pass: every window within +/-{PERMUTATION_WINDOW_TOL} of 0.5 and mean improvement within "
          f"+/-{PERMUTATION_MEAN_TOL}: {'PASS - shuffled-label performance collapses to the majority baseline' if perm_ok else 'FAIL - shuffled labels did not collapse; results above are suspect'}",
          ""]

    L += ["7. LEAKAGE CHECKS"] + [f"   {c}" for c in checks]
    L += ["   Per-window purge (latest training row / latest training target bar / first evaluation row):"]
    L += [f"     H{x['h']} {x['window']}: {x['train_end']} / {x['train_target_end']} / {x['eval_start']}" for x in leak]
    L.append("")

    L += ["8. INPUT FILES (read only)"] + [f"   {k:<40} {v}" for k, v in inputs.items()] + [""]
    L += ["9. FILE INTEGRITY (recorded before the run, verified after)"]
    L += [f"   {k:<40} {hashes[k][0]:<19} {hashes[k][1]}" for k in KEY_FILES]
    L += [f"   [PASS] {name} unchanged" for name in integrity]
    L += [f"   [PASS] all {len(hashes)} files in src/, src/data/, src/models/ unchanged.", ""]
    L += ["10. TEST-DATA SAFETY",
          f"   {TEST_STATEMENT}",
          f"   The audit hook recorded {GUARD['test_open_attempts']} attempts to open xauusd_m5_test.csv; raw, feature and",
          f"   labeled reads stopped at {GUARD['cutoff']} (the end of the purge gap before the test split); every loaded",
          "   frame was asserted to contain no later timestamp; integrity hashing read no byte after the cutoff and",
          "   checked the test CSV by size and modification time only.", ""]
    L += ["11. LIMITATIONS",
          "   - Three walk-forward windows of about five weeks each; small effects (< ~0.01 balanced accuracy) cannot be",
          "     distinguished from noise, and regime changes within ~7.5 months of data are not covered.",
          "   - Overlapping h-bar targets make neighbouring rows dependent; the block bootstrap mitigates but does not",
          "     remove this, and the CI ignores model-fitting variance (one fixed seed).",
          "   - Direction-only targets ignore magnitude, spread and costs; predictability of direction would not imply",
          "     a profitable strategy, and none is claimed.",
          "   - Only the existing 30 features and fixed RF parameters were tested; other information or models are",
          "     outside this experiment.",
          "   - Session/hour features come from the existing pipeline unchanged.",
          "", "Conclusion:", conclusion]
    return L


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    outputs = [RESULTS_PATH, REPORT_PATH]
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    skip = {p.resolve() for p in outputs} | {Path(__file__).resolve()}

    val_start, val_end, cutoff = research_boundary()
    cutoff_str = cutoff.strftime(TIME_FORMAT)
    hashes_before = snapshot(skip, cutoff_str)
    install_guards()
    GUARD["cutoff"] = cutoff_str
    for path in (RAW_PATH, FEATURES_PATH, LABELED_PATH):
        GUARD["safe_nrows"][path.resolve()] = rows_through(path, cutoff_str)
    assert RF_PARAMS == FIXED_RF, "RF parameters differ from the baseline configuration"
    assert len(RF_FEATURES) == 30 and len(set(RF_FEATURES)) == 30

    raw, features, positions = load_research_data(val_end, cutoff)
    for frame in (raw, features):
        assert_no_test_rows(frame)
        assert frame["time"].is_unique and frame["time"].is_monotonic_increasing
    split_counts = check_existing_splits(features, val_start, val_end, cutoff_str)
    print("existing train/validation/labeled rows match the features file")

    times = features["time"]
    starts = [times.iloc[int(len(times) * q)] for q in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"

    data, target_info = add_targets(features, raw, positions)
    target_cols = {c for h in HORIZONS for c in (*target_columns(h), f"target_time_{h}")}
    assert not target_cols & set(RF_FEATURES) and TARGET_COLUMN not in RF_FEATURES
    assert not FORBIDDEN_INPUTS & set(RF_FEATURES)
    assert not any(c.startswith(("future_", "direction_", "target")) for c in RF_FEATURES)
    for h in HORIZONS:
        ok = data[f"target_time_{h}"].notna()
        assert (data.loc[ok, f"target_time_{h}"] > data.loc[ok, "time"]).all()
        assert data[f"target_time_{h}"].max() <= cutoff
    past_return_check(raw, features, positions)
    truncations = feature_causality(raw, features, wf_windows)
    corr, corr_name = max_feature_target_corr(data)
    assert corr < CORRELATION_TRIPWIRE, f"feature/target correlation {corr:.3f} ({corr_name}) suggests leakage"
    print(f"leakage checks passed (max |corr| feature vs future return {corr:.4f})")

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
        f"[PASS] No future return among the 30 feature columns: target columns are disjoint from RF_FEATURES; "
        f"return_3/6/12 and log_return_1 equal the BACKWARD returns close[t]/close[t-h]-1 on every row; max "
        f"|corr(feature, future return)| = {corr:.4f} ({corr_name}), below the {CORRELATION_TRIPWIRE} tripwire.",
        f"[PASS] No target column used as a feature: models are fitted on exactly RF_FEATURES (asserted per fit); "
        f"existing target, time and price columns excluded ({', '.join(sorted(FORBIDDEN_INPUTS))}).",
        "[PASS] Training rows strictly before evaluation rows: every training row and its target bar t+h precede "
        "the window start (asserted per horizon and window; listed below).",
        f"[PASS] No test timestamps loaded: every loaded frame and every target bar <= {cutoff_str}.",
        f"[PASS] No test file opened: audit hook recorded {GUARD['test_open_attempts']} attempts.",
        f"[PASS] No future bars in features: features recomputed from raw bars truncated at {', '.join(truncations)} "
        "are identical to the stored rows up to each point; each target uses bar t+h only; predictions on a prefix "
        "equal predictions on the full window.",
        "[PASS] Evaluation timestamps chronological and unique in every window.",
        "[PASS] No duplicate timestamps in raw bars, features, train, validation or labeled rows.",
        "[PASS] Same walk-forward windows as earlier experiments; RF parameters equal the baseline.",
    ]
    inputs = {
        "src/data/xauusd_m5.csv": f"{len(raw)} rows read (through {cutoff_str}); closes for targets",
        "src/data/xauusd_m5_features.csv": f"{GUARD['safe_nrows'][FEATURES_PATH.resolve()]} rows read (through "
                                           f"{cutoff_str}); {len(features)} rows used (through {val_end})",
        "src/data/xauusd_m5_labeled.csv": "{} rows read (through {}); consistency check only".format(*split_counts[LABELED_PATH.name][::2]),
        "src/data/xauusd_m5_train.csv": "{} rows ({} -> {}); consistency check".format(*split_counts[TRAIN_PATH.name]),
        "src/data/xauusd_m5_validation.csv": "{} rows ({} -> {}); boundary and consistency".format(*split_counts[VALIDATION_PATH.name]),
        "src/models/rf_m5_baseline.pkl": "not loaded; integrity check only",
        "CSV files opened by pandas": ", ".join(sorted({p.name for p in GUARD["csv_reads"]})),
    }
    lines = build_report(results, summary, perm, perm_ok, target_info, wf_windows, leak, checks, inputs,
                         hashes_after, INTEGRITY_GROUPS, conclusion)
    assert lines[-1] in (CONCLUSION_A, CONCLUSION_B)

    out = results.merge(summary, on=["horizon", "horizon_bars"], how="left")
    out.to_csv(RESULTS_PATH, index=False, date_format=TIME_FORMAT)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert snapshot(skip, cutoff_str) == hashes_before, "existing files changed while writing outputs"

    print("\nFINAL SUMMARY")
    for _, s in summary.iterrows():
        r = results[results["horizon"] == s.horizon]
        print(f"  {s.horizon}: balanced accuracy " + ", ".join(f"{w} {v:.4f}" for w, v in zip(r.window, r.balanced_accuracy))
              + f"; mean improvement {s.wf_mean_improvement:+.4f} [CI {s.wf_improvement_ci95_low:+.4f}, "
              f"{s.wf_improvement_ci95_high:+.4f}] -> {s.verdict}")
    print(f"  permutation check (H{PERMUTATION_HORIZON}): balanced accuracy "
          + ", ".join(f"{v:.4f}" for v in perm["balanced_accuracy"]) + f" -> {'PASS' if perm_ok else 'FAIL'}")
    print(f"  test data opened: no ({GUARD['test_open_attempts']} attempts); existing files changed: none "
          f"({len(hashes_before)} checked)")
    print(f"  conclusion: {conclusion}")
    print(f"  outputs: {RESULTS_PATH}\n           {REPORT_PATH}")


if __name__ == "__main__":
    main()
