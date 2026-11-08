"""Research: is a longer triple-barrier horizon a more learnable XAUUSD M5 target?

Diagnostic only. Pre-defined label configurations are built with the same
cost-aware triple-barrier logic as label_m5.py (next-bar entry, 15-point spread
floor, $0.05 per side, bid/ask conventions, SL-first same-bar rule, gap and
incomplete-window exclusion), parameterised only by TP/SL multiples and horizon.
label_m5.py hard-codes its horizon, so its logic is mirrored here and CONFIG_0
must reproduce the existing train/validation labels exactly.

The same fixed Random Forest (train_rf_m5.RF_PARAMS) and the same 30 features
are used for every configuration; nothing is tuned.

Data boundary: only bars up to the end of the purge gap after the validation
split (last validation bar + 12 bars) are used. split_m5.py guarantees the test
split starts after that point. Test-period rows in the shared raw/feature files
are discarded immediately after reading; the test CSV is never opened.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from features_m5 import BAR_MINUTES, load_and_validate
from label_m5 import (
    ATR_COLUMN,
    BUY,
    EXTRA_COST_PER_SIDE,
    EXTRA_COST_ROUND_TRIP,
    FEATURES_PATH,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    PURGE_BARS,
    RAW_PATH,
    SELL,
    TARGET_COLUMN,
    TARGET_NAMES,
    WAIT,
    align_features_to_raw,
    check_point_size,
)
from train_rf_m5 import MODEL_PATH, RF_FEATURES, RF_PARAMS, TRAIN_PATH, VALIDATION_PATH

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_PATH = DATA_DIR / "m5_label_horizon_research.csv"
REPORT_PATH = DATA_DIR / "m5_label_horizon_research_report.txt"
INPUT_PATHS = {RAW_PATH, FEATURES_PATH, TRAIN_PATH, VALIDATION_PATH, MODEL_PATH}

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BAR = pd.Timedelta(minutes=BAR_MINUTES)

CONFIGS = {
    "CONFIG_0_CURRENT": {"tp": 1.5, "sl": 1.0, "horizon": 12},
    "CONFIG_A": {"tp": 1.5, "sl": 1.0, "horizon": 24},
    "CONFIG_B": {"tp": 2.0, "sl": 1.0, "horizon": 24},
    "CONFIG_C": {"tp": 1.5, "sl": 1.0, "horizon": 24},
}
REFERENCE_CONFIG = "CONFIG_0_CURRENT"

FIXED_RF = {
    "n_estimators": 300, "max_depth": 8, "min_samples_leaf": 50, "max_features": "sqrt",
    "max_samples": 0.5, "bootstrap": True, "class_weight": "balanced", "criterion": "gini",
    "random_state": 42, "n_jobs": -1,
}

# Walk-forward: expanding training window, validation block = next slice of the
# pre-test research rows. Fractions are fixed in advance.
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)

# Pre-defined decision rule for the conclusion (not tuned).
MEANINGFUL_DELTA = 0.01   # balanced-accuracy difference treated as more than noise

CLASS_ORDER = [BUY, SELL, WAIT]
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
CHANCE_BALANCED_ACCURACY = 1 / len(CLASS_ORDER)

TEST_STATEMENT = "The untouched TEST dataset was not loaded or used."


# --------------------------------------------------------------------------
# Data within the research boundary
# --------------------------------------------------------------------------

def research_boundary() -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    val_times = pd.to_datetime(pd.read_csv(VALIDATION_PATH, usecols=["time"])["time"], format=TIME_FORMAT)
    val_start, val_end = val_times.iloc[0], val_times.iloc[-1]
    cutoff = val_end + PURGE_BARS * BAR
    return val_start, val_end, cutoff


def load_research_data(val_end: pd.Timestamp, cutoff: pd.Timestamp):
    raw = load_and_validate(RAW_PATH)
    raw = raw[raw["time"] <= cutoff].reset_index(drop=True)
    check_point_size(raw)

    features = pd.read_csv(FEATURES_PATH)
    features["time"] = pd.to_datetime(features["time"], format=TIME_FORMAT)
    features = features[features["time"] <= val_end].reset_index(drop=True)
    if features[ATR_COLUMN].isna().any() or (features[ATR_COLUMN] <= 0).any():
        raise ValueError(f"{ATR_COLUMN} must be positive on every feature row.")
    positions = align_features_to_raw(features, raw)
    assert raw["time"].max() <= cutoff and features["time"].max() <= val_end
    return raw, features, positions


# --------------------------------------------------------------------------
# Parameterised copy of label_m5.triple_barrier_labels
# --------------------------------------------------------------------------

def first_touch(hits: list[np.ndarray], horizon: int) -> np.ndarray:
    stacked = np.column_stack(hits)
    return np.where(stacked.any(axis=1), stacked.argmax(axis=1) + 1, horizon + 1)


def build_labels(raw, features, positions, tp_mult: float, sl_mult: float, horizon: int) -> pd.DataFrame:
    n_raw = len(raw)
    open_, high, low = (raw[c].to_numpy() for c in ("open", "high", "low"))
    spread = np.maximum(raw["spread"].to_numpy(), MIN_SPREAD_POINTS) * POINT_SIZE

    atr = features[ATR_COLUMN].to_numpy()
    tp, sl = tp_mult * atr, sl_mult * atr
    entry = np.minimum(positions + 1, n_raw - 1)
    long_entry = open_[entry] + spread[entry] + EXTRA_COST_PER_SIDE
    short_entry = open_[entry] - EXTRA_COST_PER_SIDE

    long_tp, long_sl, short_tp, short_sl = [], [], [], []
    for offset in range(1, horizon + 1):
        k = np.minimum(positions + offset, n_raw - 1)
        long_tp.append(high[k] - EXTRA_COST_PER_SIDE >= long_entry + tp)
        long_sl.append(low[k] - EXTRA_COST_PER_SIDE <= long_entry - sl)
        short_tp.append(low[k] + spread[k] + EXTRA_COST_PER_SIDE <= short_entry - tp)
        short_sl.append(high[k] + spread[k] + EXTRA_COST_PER_SIDE >= short_entry + sl)

    long_win = first_touch(long_tp, horizon) < first_touch(long_sl, horizon)
    short_win = first_touch(short_tp, horizon) < first_touch(short_sl, horizon)

    contiguous = (raw["time"].diff() == BAR).to_numpy()
    incomplete = positions + horizon > n_raw - 1
    crosses_gap = np.zeros(len(positions), dtype=bool)
    for offset in range(1, horizon + 1):
        crosses_gap |= ~contiguous[np.minimum(positions + offset, n_raw - 1)]
    crosses_gap &= ~incomplete
    excluded = incomplete | crosses_gap

    both = long_win & short_win & ~excluded
    if both.any():
        raise AssertionError(f"BUY and SELL both true on {int(both.sum())} rows.")

    target = np.full(len(positions), WAIT, dtype=np.int64)
    target[long_win] = BUY
    target[short_win] = SELL
    return pd.DataFrame({
        "time": features["time"].to_numpy(),
        TARGET_COLUMN: target,
        "incomplete_window": incomplete,
        "crosses_gap": crosses_gap,
        "excluded": excluded,
        "approx_round_trip_cost": spread[entry] + EXTRA_COST_ROUND_TRIP,
        "tp_distance": tp,
    })


def label_statistics(name: str, labels: pd.DataFrame) -> dict:
    kept = labels[~labels["excluded"]]
    counts = kept[TARGET_COLUMN].value_counts()
    shares = {TARGET_NAMES[c]: counts.get(c, 0) / len(kept) for c in CLASS_ORDER}
    return {
        "section": "label_stats", "config": name, "evaluation": "all_research_rows",
        "feature_rows": len(labels), "labeled_rows": len(kept),
        "buy_count": int(counts.get(BUY, 0)), "sell_count": int(counts.get(SELL, 0)),
        "wait_count": int(counts.get(WAIT, 0)),
        "buy_pct": shares["BUY"], "sell_pct": shares["SELL"], "wait_pct": shares["WAIT"],
        "missing_targets": int(kept[TARGET_COLUMN].isna().sum()),
        "excluded_rows": int(labels["excluded"].sum()),
        "incomplete_window_exclusions": int(labels["incomplete_window"].sum()),
        "gap_exclusions": int(labels["crosses_gap"].sum()),
        "class_balance_max_min_ratio": max(shares.values()) / min(shares.values()),
        "median_cost_to_tp": float(np.median(kept["approx_round_trip_cost"] / kept["tp_distance"])),
    }


# --------------------------------------------------------------------------
# Splits and evaluation
# --------------------------------------------------------------------------

def purged_split(labeled: pd.DataFrame, horizon: int, val_start, val_stop, inclusive_stop: bool):
    window = horizon * BAR
    train = labeled[(labeled["time"] < val_start) & (labeled["time"] + window < val_start)]
    in_val = labeled["time"] <= val_stop if inclusive_stop else labeled["time"] < val_stop
    val = labeled[(labeled["time"] >= val_start) & in_val]
    assert train["time"].max() + window < val["time"].min(), "label window leaks into validation"
    return train, val


def evaluate(train: pd.DataFrame, val: pd.DataFrame):
    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(train[RF_FEATURES], train[TARGET_COLUMN])
    y_tr, y_val = train[TARGET_COLUMN], val[TARGET_COLUMN]
    p_tr, p_val = model.predict(train[RF_FEATURES]), model.predict(val[RF_FEATURES])

    precision, recall, _, support = precision_recall_fscore_support(
        y_val, p_val, labels=CLASS_ORDER, zero_division=0)
    cm = confusion_matrix(y_val, p_val, labels=CLASS_ORDER)
    val_share = y_val.value_counts(normalize=True)
    train_share = y_tr.value_counts(normalize=True)

    train_bal = balanced_accuracy_score(y_tr, p_tr)
    val_bal = balanced_accuracy_score(y_val, p_val)
    out = {
        "train_rows": len(train), "val_rows": len(val),
        "train_start": train["time"].iloc[0], "train_end": train["time"].iloc[-1],
        "val_start": val["time"].iloc[0], "val_end": val["time"].iloc[-1],
        "train_accuracy": accuracy_score(y_tr, p_tr), "train_balanced_accuracy": train_bal,
        "val_accuracy": accuracy_score(y_val, p_val), "val_balanced_accuracy": val_bal,
        "majority_class_accuracy": val_share.max(),
        "majority_class_balanced_accuracy": CHANCE_BALANCED_ACCURACY,
        "train_val_gap": train_bal - val_bal,
        "confusion_matrix": ";".join(",".join(str(v) for v in row) for row in cm),
    }
    for i, (cls, name) in enumerate(zip(CLASS_ORDER, CLASS_LABELS)):
        key = name.lower()
        prevalence = val_share.get(cls, 0.0)
        out.update({
            f"{key}_precision": precision[i], f"{key}_recall": recall[i], f"{key}_support": int(support[i]),
            f"{key}_predicted": int((p_val == cls).sum()),
            f"{key}_val_share": prevalence, f"{key}_train_share": train_share.get(cls, 0.0),
            f"{key}_precision_lift": precision[i] / prevalence if prevalence else float("nan"),
        })
    return out, cm, model


# --------------------------------------------------------------------------
# Reproducibility of the current pipeline
# --------------------------------------------------------------------------

def check_current_reproduced(labels_0: pd.DataFrame, train_0: pd.DataFrame, val_0: pd.DataFrame, model_0) -> None:
    existing_train = pd.read_csv(TRAIN_PATH, usecols=["time", TARGET_COLUMN])
    existing_val = pd.read_csv(VALIDATION_PATH, usecols=["time"] + RF_FEATURES + [TARGET_COLUMN])
    for df in (existing_train, existing_val):
        df["time"] = pd.to_datetime(df["time"], format=TIME_FORMAT)

    kept = labels_0[~labels_0["excluded"]].set_index("time")[TARGET_COLUMN]
    for name, existing in (("train", existing_train), ("validation", existing_val)):
        mine = kept.reindex(existing["time"])
        assert mine.notna().all(), f"CONFIG_0 is missing existing {name} rows"
        assert (mine.to_numpy() == existing[TARGET_COLUMN].to_numpy()).all(), f"CONFIG_0 {name} labels differ"
    assert train_0["time"].tolist() == existing_train["time"].tolist(), "CONFIG_0 training rows differ"
    assert val_0["time"].tolist() == existing_val["time"].tolist(), "CONFIG_0 validation rows differ"

    saved = joblib.load(MODEL_PATH)["model"]
    assert (saved.predict(existing_val[RF_FEATURES]) == model_0.predict(existing_val[RF_FEATURES])).all(), \
        "retrained CONFIG_0 model differs from the saved baseline"


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def fmt_pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


def eval_table(results: pd.DataFrame, evaluation: str) -> str:
    sub = results[(results["section"] == "evaluation") & (results["evaluation"] == evaluation)].set_index("config")
    cols = ["train_rows", "val_rows", "train_balanced_accuracy", "val_accuracy", "val_balanced_accuracy",
            "majority_class_accuracy", "train_val_gap", "buy_precision", "buy_recall", "sell_precision",
            "sell_recall", "wait_precision", "wait_recall"]
    t = sub[cols].copy()
    for c in cols[2:]:
        t[c] = t[c].map(lambda v: f"{v:+.4f}" if c == "train_val_gap" else fmt_pct(v))
    return t.to_string()


def build_report(results, wf_windows, boundary, duplicates, confusions) -> list[str]:
    val_start, val_end, cutoff = boundary
    stats = results[results["section"] == "label_stats"].set_index("config")
    ev = results[results["section"] == "evaluation"]
    lines = ["XAUUSD M5 label-horizon research (diagnostic only)", "=" * 72, TEST_STATEMENT,
             f"Research data: bars up to {cutoff} (end of purge gap after validation; test starts later).",
             f"Main split: existing train/validation boundary, validation {val_start} -> {val_end}.",
             "Fixed RF for every config: " + ", ".join(f"{k}={v}" for k, v in RF_PARAMS.items()),
             "CONFIG_0 reproduction check: labels, train/validation rows and saved-model predictions match exactly."]
    if duplicates:
        lines.append("NOTE: identical configurations requested: " + "; ".join(" = ".join(d) for d in duplicates)
                     + " (results must match; serves as a determinism check).")
    lines.append("")

    lines += ["LABEL STATISTICS (all pre-test research rows)"]
    t = stats[["tp_mult", "sl_mult", "horizon", "labeled_rows", "buy_count", "buy_pct", "sell_count",
               "sell_pct", "wait_count", "wait_pct", "missing_targets", "excluded_rows", "gap_exclusions",
               "incomplete_window_exclusions", "class_balance_max_min_ratio", "median_cost_to_tp"]].copy()
    for c in ("buy_pct", "sell_pct", "wait_pct", "median_cost_to_tp"):
        t[c] = t[c].map(fmt_pct)
    t["class_balance_max_min_ratio"] = t["class_balance_max_min_ratio"].map("{:.2f}".format)
    lines += [t.to_string(), ""]

    lines += ["LEARNABILITY - main split (existing train/validation boundary)", eval_table(results, "main"), ""]
    lines.append("Confusion matrices, main split (rows = true BUY/SELL/WAIT, columns = predicted BUY/SELL/WAIT):")
    for name, cm in confusions.items():
        lines.append(f"  {name}: " + " | ".join(" ".join(f"{v:5d}" for v in row) for row in cm))
    lines.append("")

    lines.append("WALK-FORWARD windows (expanding train, purged by each config's horizon):")
    for i, (start, stop) in enumerate(wf_windows, 1):
        lines.append(f"  WF{i}: train = research rows before {start}; validation = {start} -> {stop}")
    for i in range(1, len(wf_windows) + 1):
        lines += [f"\nWF{i}", eval_table(results, f"WF{i}")]
    lines.append("")

    wf = ev[ev["evaluation"].str.startswith("WF")]
    dist = wf.pivot(index="config", columns="evaluation", values=["buy_val_share", "sell_val_share", "wait_val_share"])
    lines += ["Validation class distribution by walk-forward window:",
              dist.apply(lambda s: s.map(fmt_pct)).to_string(), ""]
    return lines


def conclusion(results: pd.DataFrame, duplicates) -> list[str]:
    ev = results[results["section"] == "evaluation"]
    stats = results[results["section"] == "label_stats"].set_index("config")
    bal = ev.pivot(index="config", columns="evaluation", values="val_balanced_accuracy")
    gap = ev.pivot(index="config", columns="evaluation", values="train_val_gap")
    wf_cols = [c for c in bal.columns if c.startswith("WF")]
    ref = bal.loc[REFERENCE_CONFIG]
    dup_of = {b: a for a, b in duplicates}

    lines = ["", "FINAL CONCLUSION", "=" * 72]

    cur_wf = bal.loc[REFERENCE_CONFIG, wf_cols]
    lines += ["1. CURRENT LABEL",
              f"   CONFIG_0 validation balanced accuracy: main {ref['main']:.4f}; walk-forward "
              f"{cur_wf.min():.4f}-{cur_wf.max():.4f} (mean {cur_wf.mean():.4f}); chance level {CHANCE_BALANCED_ACCURACY:.4f}.",
              f"   It is above chance by {ref['main'] - CHANCE_BALANCED_ACCURACY:+.4f} on the main split, i.e. weakly learnable."]
    others = [c for c in bal.index if c != REFERENCE_CONFIG]
    harder = all((bal.loc[c, ["main"] + wf_cols] - ref[["main"] + wf_cols] > MEANINGFUL_DELTA).all() for c in others)
    lines.append("   Relative to the tested alternatives it is " +
                 ("consistently harder." if harder else "not unusually difficult (no alternative beats it "
                  f"by > {MEANINGFUL_DELTA} in every window)."))

    lines.append("2. HORIZON EFFECT")
    for c in others:
        if c in dup_of:
            lines.append(f"   {c}: identical to {dup_of[c]} (same TP/SL/horizon); see that config.")
            continue
        deltas = bal.loc[c, ["main"] + wf_cols] - ref[["main"] + wf_cols]
        better = int((deltas > MEANINGFUL_DELTA).sum())
        worse = int((deltas < -MEANINGFUL_DELTA).sum())
        lines.append(f"   {c} (TP {stats.loc[c, 'tp_mult']}, SL {stats.loc[c, 'sl_mult']}, H {int(stats.loc[c, 'horizon'])}): "
                     f"balanced-accuracy change vs CONFIG_0 = " +
                     ", ".join(f"{k} {v:+.4f}" for k, v in deltas.items()) +
                     f"; better by > {MEANINGFUL_DELTA} in {better}/{len(deltas)}, worse in {worse}/{len(deltas)}.")

    lines.append("3. GENERALIZATION")
    for c in bal.index:
        if c in dup_of:
            continue
        lines.append(f"   {c}: train-val gap main {gap.loc[c, 'main']:+.4f}, walk-forward mean "
                     f"{gap.loc[c, wf_cols].mean():+.4f}; val balanced accuracy walk-forward range "
                     f"{bal.loc[c, wf_cols].min():.4f}-{bal.loc[c, wf_cols].max():.4f}.")
    consistent = [c for c in others if c not in dup_of and
                  ((bal.loc[c, ["main"] + wf_cols] - ref[["main"] + wf_cols]) > MEANINGFUL_DELTA).all()]
    lines.append("   Improvement consistent across main split and all walk-forward windows: " +
                 (", ".join(consistent) if consistent else "none") + ".")

    lines.append("4. CLASS BALANCE")
    for c in bal.index:
        if c in dup_of:
            continue
        s = stats.loc[c]
        lines.append(f"   {c}: BUY {s['buy_pct']:.1%}, SELL {s['sell_pct']:.1%}, WAIT {s['wait_pct']:.1%} "
                     f"(max/min ratio {s['class_balance_max_min_ratio']:.2f}; gap exclusions {int(s['gap_exclusions'])}).")

    lines.append("5. COST IMPLICATION")
    main = ev[ev["evaluation"] == "main"].set_index("config")
    for c in bal.index:
        if c in dup_of:
            continue
        s, m = stats.loc[c], main.loc[c]
        ref_rate = s["sl_mult"] / (s["tp_mult"] + s["sl_mult"])
        lines.append(f"   {c}: median round-trip cost = {s['median_cost_to_tp']:.1%} of TP distance; "
                     f"theoretical TP/SL reference {ref_rate:.1%} (excluding time exits); validation precision "
                     f"BUY {m['buy_precision']:.1%} (lift {m['buy_precision_lift']:.2f}x), "
                     f"SELL {m['sell_precision']:.1%} (lift {m['sell_precision_lift']:.2f}x).")
    lines.append("   Precision is a label-level diagnostic, not P&L; time exits and costs are not simulated here.")

    lines.append("6. RECOMMENDED NEXT RESEARCH STEP")
    if consistent:
        lines.append(f"   {', '.join(consistent)} improved in every window. Next: run the existing cost-aware "
                     "backtest for those label definitions on the same walk-forward windows (still not the test set) "
                     "before drawing any conclusion.")
    else:
        lines.append("   No horizon change improved learnability consistently. The bottleneck appears to be the "
                     "information in the 30 features rather than the label horizon. Next: research new, pre-defined "
                     "feature families (e.g. higher-timeframe context) evaluated with this same walk-forward "
                     "diagnostic, without touching the test set.")
    lines += ["", "No production strategy is recommended. Validation and walk-forward results are diagnostic only.",
              TEST_STATEMENT]
    return lines


def main() -> None:
    assert RF_PARAMS == FIXED_RF, "train_rf_m5.RF_PARAMS differs from the fixed research configuration"
    boundary = research_boundary()
    val_start, val_end, cutoff = boundary
    raw, features, positions = load_research_data(val_end, cutoff)

    times = features["time"]
    wf_starts = [times.iloc[int(len(times) * f)] for f in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(wf_starts[i], wf_starts[i + 1] if i + 1 < len(wf_starts) else val_end)
                  for i in range(len(wf_starts))]

    seen, duplicates = {}, []
    for name, cfg in CONFIGS.items():
        key = (cfg["tp"], cfg["sl"], cfg["horizon"])
        if key in seen:
            duplicates.append((seen[key], name))
        seen.setdefault(key, name)

    rows, confusions, main_scores = [], {}, {}
    for name, cfg in CONFIGS.items():
        labels = build_labels(raw, features, positions, cfg["tp"], cfg["sl"], cfg["horizon"])
        labeled = features[~labels["excluded"].to_numpy()].assign(
            **{TARGET_COLUMN: labels.loc[~labels["excluded"], TARGET_COLUMN].to_numpy()})
        rows.append({**label_statistics(name, labels), "tp_mult": cfg["tp"], "sl_mult": cfg["sl"],
                     "horizon": cfg["horizon"]})

        train, val = purged_split(labeled, cfg["horizon"], val_start, val_end, inclusive_stop=True)
        result, cm, model = evaluate(train, val)
        if name == REFERENCE_CONFIG:
            check_current_reproduced(labels, train, val, model)
        confusions[name] = cm
        main_scores[name] = result["val_balanced_accuracy"]
        rows.append({"section": "evaluation", "config": name, "evaluation": "main", "tp_mult": cfg["tp"],
                     "sl_mult": cfg["sl"], "horizon": cfg["horizon"], **result})

        for i, (start, stop) in enumerate(wf_windows, 1):
            last = i == len(wf_windows)
            train, val = purged_split(labeled, cfg["horizon"], start, stop, inclusive_stop=last)
            result, _, _ = evaluate(train, val)
            rows.append({"section": "evaluation", "config": name, "evaluation": f"WF{i}", "tp_mult": cfg["tp"],
                         "sl_mult": cfg["sl"], "horizon": cfg["horizon"], **result})
        print(f"finished {name}: main val balanced accuracy {main_scores[name]:.4f}")

    results = pd.DataFrame(rows)
    for a, b in duplicates:
        ea = results[(results.config == a) & (results.section == "evaluation")]["val_balanced_accuracy"].to_numpy()
        eb = results[(results.config == b) & (results.section == "evaluation")]["val_balanced_accuracy"].to_numpy()
        assert np.allclose(ea, eb), f"identical configs {a} and {b} gave different results"

    for path in (RESULTS_PATH, REPORT_PATH):
        if path in INPUT_PATHS:
            raise RuntimeError(f"Refusing to overwrite input file {path}")
    results.to_csv(RESULTS_PATH, index=False)

    lines = build_report(results, wf_windows, boundary, duplicates, confusions) + conclusion(results, duplicates)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("\n".join(lines))
    print(f"\nSaved results: {RESULTS_PATH}")
    print(f"Saved report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()
