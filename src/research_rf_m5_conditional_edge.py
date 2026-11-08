"""Research: does the existing RF M5 strategy have a STABLE conditional edge in
pre-defined subgroups (side, RSI bucket, ATR% quartile, session and their pairs)?

Diagnostic only. No feature, label, split, model or backtest rule is changed and
no trading rule is produced.

Trade sources
* Main validation period: the existing trades in rf_m5_validation_trades.csv, produced
  by the saved model src/models/rf_m5_baseline.pkl. They are regenerated here with the
  unchanged backtest engine and must match the file exactly (baseline integrity).
* Walk-forward windows WF1-WF3 (the windows used by every earlier experiment): the saved
  model was trained on data up to 2026-08-20, so its trades inside WF1/WF2 would be
  in-sample. For each window an RF with the identical 30 features and fixed parameters is
  trained only on labeled rows whose 12-bar label window ends before the window starts
  (expanding window, same purge as before), and its signals are traded with the unchanged
  backtest engine. This is the same retraining procedure as the earlier walk-forward
  classification experiments.

Group context (RSI 14, ATR% and session) is read from the feature row of each trade's
signal bar - what the model saw. RSI buckets use fixed edges and ATR% quartile edges come
from the training split, both exactly as in analyze_rf_m5_trades.py.

Test safety: research_kronos_m5 guards (an audit hook that raises on any attempt to open
the test CSV, and raw/feature reads capped at the last purge-gap bar). File integrity is
checked without reading any byte after the research cutoff: files that contain test-period
rows are hashed only up to the cutoff row plus size/modification time, and the test CSV is
checked by size/modification time only.
"""

import hashlib
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier

from analyze_rf_m5_trades import RSI_EDGES, RSI_LABELS, atr_pct_bucket_edges
from backtest_rf_m5 import (
    MODEL_PATH,
    TRADES_PATH,
    VALIDATION_PATH,
    check_against_validation,
    generate_signals,
    load_market,
    load_model,
    load_validation_period,
    run_backtest,
)
from features_m5 import BAR_MINUTES, SESSION_IDS
from label_m5 import ATR_COLUMN, FEATURES_PATH, HORIZON_BARS, RAW_PATH, TARGET_COLUMN, align_features_to_raw
from research_kronos_m5 import GUARD, TEST_PATH, assert_no_test_rows, install_guards, rows_through
from research_m5_label_horizon import (
    FIXED_RF,
    build_labels,
    check_current_reproduced,
    load_research_data,
    purged_split,
    research_boundary,
)
from research_m5_label_horizon import evaluate as evaluate_rf_only
from train_rf_m5 import RF_FEATURES, RF_PARAMS, TRAIN_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
MODELS_DIR = SRC_DIR / "models"
RESULTS_PATH = DATA_DIR / "rf_m5_conditional_edge_research.csv"
REPORT_PATH = DATA_DIR / "rf_m5_conditional_edge_research_report.txt"
LABELED_PATH = DATA_DIR / "xauusd_m5_labeled.csv"

BAR = pd.Timedelta(minutes=BAR_MINUTES)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
WF = ["WF1", "WF2", "WF3"]

SESSION_LABELS = {"asia": "Asia", "london": "London", "london_ny_overlap": "London-NY overlap",
                  "new_york": "New York", "off_hours": "Off-hours"}
SESSION_ORDER = ["Asia", "London", "London-NY overlap", "New York", "Off-hours"]
SESSION_NAMES = {code: SESSION_LABELS[name] for name, code in SESSION_IDS.items()}
ATR_LABELS = ["Q1", "Q2", "Q3", "Q4"]
SIDES = ["BUY", "SELL"]

# Rules fixed before any result is seen.
MIN_TRADES = 100
MIN_WINDOW_TRADES = 50
MIN_WINDOWS_POPULATED = 2
MIN_POSITIVE_WINDOWS = 2
MIN_WF_MEAN_R = 0.02
WORST_WINDOW_R = -0.02
BOOT_SAMPLES = 2000
BOOT_SEED = 42
FDR_Q = 0.10

# Files whose rows extend past the research cutoff: only the part up to the cutoff row is hashed.
PREFIX_HASH_FILES = {"xauusd_m5.csv", "xauusd_m5_features.csv", "xauusd_m5_labeled.csv"}
# Test files and legacy files of unknown date range: size and modification time only.
STAT_ONLY_FILES = {"xauusd_m5_test.csv", "test.csv", "gold_history.csv", "train.csv", "validation.csv",
                   "train_features.csv"}
KEY_FILES = ["models/rf_m5_baseline.pkl", "data/xauusd_m5_train.csv", "data/xauusd_m5_validation.csv",
             "data/rf_m5_validation_trades.csv", "data/xauusd_m5_labeled.csv", "data/xauusd_m5_features.csv",
             "data/xauusd_m5.csv", "data/xauusd_m5_test.csv"]

TEST_STATEMENT = "The untouched TEST dataset was never opened, read or used."


# --------------------------------------------------------------------------
# File integrity without reading past the research cutoff
# --------------------------------------------------------------------------

def prefix_sha256(path: Path, cutoff: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        header = fh.readline()
        if not header.startswith(b"time,"):
            raise RuntimeError(f"{path.name}: unexpected header")
        h.update(header)
        for line in fh:
            if line[:19].decode("ascii") > cutoff:
                break
            h.update(line)
    return h.hexdigest()


def snapshot(skip: set, cutoff: str) -> dict:
    out = {}
    for folder in (SRC_DIR, DATA_DIR, MODELS_DIR):
        for path in sorted(folder.iterdir()):
            resolved = path.resolve()
            if not path.is_file() or resolved in skip:
                continue
            st = os.stat(path)
            key = str(resolved.relative_to(SRC_DIR)).replace("\\", "/")
            if resolved == TEST_PATH or (folder == DATA_DIR and path.name in STAT_ONLY_FILES):
                out[key] = ("stat", f"size={st.st_size} mtime_ns={st.st_mtime_ns}")
            elif folder == DATA_DIR and path.name in PREFIX_HASH_FILES:
                out[key] = ("prefix-sha256+stat", f"{prefix_sha256(path, cutoff)} size={st.st_size} "
                                                  f"mtime_ns={st.st_mtime_ns}")
            else:
                out[key] = ("sha256", hashlib.sha256(path.read_bytes()).hexdigest())
    return out


# --------------------------------------------------------------------------
# Trades and context
# --------------------------------------------------------------------------

def attach_context(trades: pd.DataFrame, features: pd.DataFrame, atr_edges) -> pd.DataFrame:
    ctx = features[["time", "rsi_14", "atr_14_pct", "session_id", ATR_COLUMN]]
    t = trades.merge(ctx, left_on="signal_time", right_on="time", how="left", validate="many_to_one")
    assert t[["rsi_14", "atr_14_pct", "session_id"]].notna().all().all(), "signal bar without a feature row"
    assert np.allclose(t["atr"], t[ATR_COLUMN]), "trade ATR differs from the signal-bar feature row"
    t["rsi_bucket"] = pd.cut(t["rsi_14"], bins=RSI_EDGES, labels=RSI_LABELS, right=False).astype(str)
    t["atr_quartile"] = pd.cut(t["atr_14_pct"], bins=atr_edges, labels=ATR_LABELS, right=False).astype(str)
    t["session"] = t["session_id"].astype(int).map(SESSION_NAMES)
    assert t[["rsi_bucket", "atr_quartile", "session"]].notna().all().all()
    assert not t[["rsi_bucket", "atr_quartile"]].isin(["nan"]).any().any()
    return t.drop(columns=["time", ATR_COLUMN])


def normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    t = trades.copy()
    for col in ("signal_time", "entry_time", "exit_time"):
        t[col] = pd.to_datetime(t[col])
    return t.sort_values("entry_time").reset_index(drop=True)


def walk_forward_trades(raw, features, full_labeled, wf_windows) -> tuple[pd.DataFrame, list[dict]]:
    out, meta = [], []
    for i, (a, b) in enumerate(wf_windows, 1):
        last = i == len(wf_windows)
        train, _ = purged_split(full_labeled, HORIZON_BARS, a, b, inclusive_stop=last)
        assert train["time"].max() + HORIZON_BARS * BAR < a, "training label window reaches into the WF window"
        model = RandomForestClassifier(**FIXED_RF).fit(train[RF_FEATURES], train[TARGET_COLUMN])
        in_win = (features["time"] >= a) & ((features["time"] <= b) if last else (features["time"] < b))
        feats = features[in_win].reset_index(drop=True)
        bar_limit = feats["time"].max() + HORIZON_BARS * BAR
        raw_w = raw[(raw["time"] >= a) & (raw["time"] <= bar_limit)].reset_index(drop=True)
        positions = align_features_to_raw(feats, raw_w)
        signals = generate_signals(model, feats, RF_FEATURES)
        trades, skipped = run_backtest(raw_w, feats, positions, signals)
        trades = normalize_trades(trades).assign(window=f"WF{i}")
        assert trades["signal_time"].between(a, b).all() and (trades["entry_time"] > trades["signal_time"]).all()
        out.append(trades)
        meta.append({"window": f"WF{i}", "train_rows": len(train), "train_end": train["time"].max(),
                     "window_start": a, "window_end": b, "feature_rows": len(feats),
                     "buy_signals": int((signals == 1).sum()), "sell_signals": int((signals == -1).sum()),
                     "trades": len(trades), "skipped": dict(skipped)})
    return pd.concat(out, ignore_index=True), meta


# --------------------------------------------------------------------------
# Group statistics
# --------------------------------------------------------------------------

def profit_factor(net: np.ndarray) -> float:
    gains, losses = net[net > 0].sum(), -net[net < 0].sum()
    return gains / losses if losses > 0 else (float("inf") if gains > 0 else float("nan"))


def longest_losing_streak(net: np.ndarray) -> int:
    best = run = 0
    for v in net:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return best


def bootstrap_ci(r: np.ndarray) -> tuple[float, float]:
    if len(r) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(BOOT_SEED)
    means = r[rng.integers(0, len(r), size=(BOOT_SAMPLES, len(r)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def trade_stats(g: pd.DataFrame, prefix: str) -> dict:
    r, net = g["net_pnl_r"].to_numpy(float), g["net_pnl"].to_numpy(float)
    n = len(r)
    lo, hi = bootstrap_ci(r)
    return {f"{prefix}trades": n, f"{prefix}total_r": r.sum() if n else np.nan,
            f"{prefix}avg_r": r.mean() if n else np.nan, f"{prefix}median_r": np.median(r) if n else np.nan,
            f"{prefix}win_rate": (net > 0).mean() if n else np.nan,
            f"{prefix}profit_factor": profit_factor(net) if n else np.nan,
            f"{prefix}std_r": r.std(ddof=1) if n > 1 else np.nan,
            f"{prefix}ci95_low": lo, f"{prefix}ci95_high": hi,
            f"{prefix}longest_losing_streak": longest_losing_streak(net)}


def group_definitions() -> list[tuple[str, str, dict]]:
    """(dimension, group label, {column: value}) - every pre-declared group."""
    groups = [("SIDE", "ALL", {})] + [("SIDE", s, {"side": s}) for s in SIDES]
    groups += [("RSI", b, {"rsi_bucket": b}) for b in RSI_LABELS]
    groups += [("ATR", q, {"atr_quartile": q}) for q in ATR_LABELS]
    groups += [("SESSION", s, {"session": s}) for s in SESSION_ORDER]
    groups += [("SIDE x RSI", f"{s} | {b}", {"side": s, "rsi_bucket": b}) for s in SIDES for b in RSI_LABELS]
    groups += [("SIDE x ATR", f"{s} | {q}", {"side": s, "atr_quartile": q}) for s in SIDES for q in ATR_LABELS]
    groups += [("SIDE x SESSION", f"{s} | {x}", {"side": s, "session": x}) for s in SIDES for x in SESSION_ORDER]
    groups += [("RSI x SESSION", f"{b} | {x}", {"rsi_bucket": b, "session": x}) for b in RSI_LABELS
               for x in SESSION_ORDER]
    groups += [("RSI x ATR", f"{b} | {q}", {"rsi_bucket": b, "atr_quartile": q}) for b in RSI_LABELS
               for q in ATR_LABELS]
    return groups


def select(trades: pd.DataFrame, cond: dict) -> pd.DataFrame:
    mask = np.ones(len(trades), dtype=bool)
    for col, val in cond.items():
        mask &= (trades[col] == val).to_numpy()
    return trades[mask]


def benjamini_hochberg(p: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1.0)
    out = np.empty(n)
    out[order] = adj
    return out, out <= q


def analyse_groups(main: pd.DataFrame, wf: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dim, label, cond in group_definitions():
        gm, gw = select(main, cond), select(wf, cond)
        row = {"section": "group", "dimension": dim, "group": label, **trade_stats(gm, "main_"),
               **trade_stats(gw, "wf_pooled_")}
        row["main_low_sample"] = len(gm) < MIN_TRADES
        avgs = []
        for w in WF:
            gx = gw[gw["window"] == w]
            row[f"{w}_trades"], row[f"{w}_avg_r"] = len(gx), gx["net_pnl_r"].mean() if len(gx) else np.nan
            avgs.append(row[f"{w}_avg_r"])
        avgs = np.array(avgs, dtype=float)
        row["wf_mean_avg_r"] = np.nanmean(avgs) if np.isfinite(avgs).any() else np.nan
        row["wf_std_avg_r"] = np.nanstd(avgs, ddof=1) if np.isfinite(avgs).sum() > 1 else np.nan
        row["wf_positive_windows"] = int((avgs > 0).sum())
        row["wf_negative_windows"] = int((avgs < 0).sum())
        row["wf_sufficient"] = len(gw) >= MIN_TRADES
        r = gw["net_pnl_r"].to_numpy(float)
        row["wf_p_value_mean_gt_0"] = (float(stats.ttest_1samp(r, 0.0, alternative="greater").pvalue)
                                       if len(r) > 2 else np.nan)
        populated = sum(row[f"{w}_trades"] >= MIN_WINDOW_TRADES for w in WF)
        checks = {
            "crit_total_trades": len(gw) >= MIN_TRADES,
            "crit_windows_populated": populated >= MIN_WINDOWS_POPULATED,
            "crit_positive_windows": row["wf_positive_windows"] >= MIN_POSITIVE_WINDOWS,
            "crit_wf_mean": bool(row["wf_mean_avg_r"] > MIN_WF_MEAN_R),
            "crit_worst_window": bool(np.isfinite(avgs).all() and avgs.min() >= WORST_WINDOW_R),
            "crit_ci_not_negative": bool(row["wf_pooled_ci95_high"] > 0),
        }
        row.update(checks)
        row["wf_candidate"] = all(checks.values())
        row["main_profitable"] = bool(row["main_avg_r"] > 0) if len(gm) else False
        rows.append(row)
    g = pd.DataFrame(rows)

    tested = g["wf_sufficient"].to_numpy()
    g["fdr_adjusted_p"], g["fdr_reject"] = np.nan, False
    adj, rej = benjamini_hochberg(g.loc[tested, "wf_p_value_mean_gt_0"].to_numpy(float), FDR_Q)
    g.loc[tested, "fdr_adjusted_p"], g.loc[tested, "fdr_reject"] = adj, rej
    g["wf_candidate_after_fdr"] = g["wf_candidate"] & g["fdr_reject"]

    def classify(r) -> str:
        if r["wf_candidate_after_fdr"]:
            return "REPEATED_BEHAVIOUR_CANDIDATE"
        if r["wf_candidate"]:
            return "MULTIPLE_TESTING_ARTIFACT_RISK"
        if not r["wf_sufficient"]:
            return "LOW_SAMPLE"
        if not r["main_low_sample"] and r["main_profitable"]:
            return "VALIDATION_PERIOD_NOISE"
        return "NO_EDGE"
    g["classification"] = g.apply(classify, axis=1)
    return g


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def f(v, spec="+.4f") -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "inf" if v == float("inf") else "-"
    return format(v, spec)


def main_table(g: pd.DataFrame) -> list[str]:
    hdr = (f"   {'dimension':<15}{'group':<28}{'n':>5} {'totR':>8} {'avgR':>8} {'medR':>8} {'win%':>6} {'PF':>6} "
           f"{'stdR':>6} {'CI95 avgR':>19} {'streak':>6}  flag")
    L = [hdr]
    for _, r in g.iterrows():
        L.append(f"   {r.dimension:<15}{r.group:<28}{int(r.main_trades):>5} {f(r.main_total_r, '+.2f'):>8} "
                 f"{f(r.main_avg_r):>8} {f(r.main_median_r):>8} {f(r.main_win_rate * 100 if r.main_trades else np.nan, '.1f'):>6} "
                 f"{f(r.main_profit_factor, '.3f'):>6} {f(r.main_std_r, '.3f'):>6} "
                 f"[{f(r.main_ci95_low)}, {f(r.main_ci95_high)}] {int(r.main_longest_losing_streak):>6}  "
                 f"{'LOW_SAMPLE' if r.main_low_sample else ''}")
    return L


def wf_table(g: pd.DataFrame) -> list[str]:
    hdr = (f"   {'dimension':<15}{'group':<28}{'n':>5}" + "".join(f" {w + ' n':>6} {w + ' avgR':>9}" for w in WF)
           + f" {'WFmean':>8} {'WFstd':>7} {'+/-':>4} {'pooled CI95':>19} {'FDR p':>6}  classification")
    L = [hdr]
    for _, r in g.iterrows():
        L.append(f"   {r.dimension:<15}{r.group:<28}{int(r.wf_pooled_trades):>5}"
                 + "".join(f" {int(r[f'{w}_trades']):>6} {f(r[f'{w}_avg_r']):>9}" for w in WF)
                 + f" {f(r.wf_mean_avg_r):>8} {f(r.wf_std_avg_r, '.4f'):>7} "
                 f"{int(r.wf_positive_windows)}/{int(r.wf_negative_windows)} "
                 f"[{f(r.wf_pooled_ci95_low)}, {f(r.wf_pooled_ci95_high)}] {f(r.fdr_adjusted_p, '.3f'):>6}  "
                 f"{r.classification}")
    return L


def build_report(g, main, wf, wf_meta, inputs, hashes, checks, summary, conclusion) -> list[str]:
    L = ["RF M5 conditional-edge research (descriptive diagnostic; no trading rule)", "=" * 74, TEST_STATEMENT,
         "Question: does the existing 30-feature RF strategy show STABLE positive expectancy in any pre-defined",
         "subgroup (side, RSI 14 bucket, ATR% quartile, session, and their pairs) across walk-forward windows?",
         "R = net P&L / SL distance (1.0 x ATR14), after spread floor and $0.05/side costs, as in the backtester.", ""]

    L += ["1. INPUT FILES (read only)"] + [f"   {k:<44} {v}" for k, v in inputs.items()] + [""]

    L += ["2. METHOD",
          "   Main validation trades: existing rf_m5_validation_trades.csv (saved model), verified by regenerating them",
          "   with the unchanged backtest engine. Walk-forward trades: one RF per window, fixed parameters and the same",
          "   30 features, trained on labeled rows whose 12-bar label window ends before the window starts; signals on",
          "   every feature row of the window, traded with the unchanged backtest engine (one position at a time, next-",
          "   bar entry, TP 1.5 ATR / SL 1.0 ATR / 12 bars). The saved model is not used there because it was trained",
          "   on WF1/WF2 data. WF3 overlaps the main validation period (different model, so trades differ).",
          "   Group context comes from the signal-bar feature row. RSI edges <30, 30-40, 40-50, 50-60, 60-70, >=70;",
          f"   ATR% quartile edges from the training split: {checks['atr_edges']}; sessions = existing session_id.",
          "   Bootstrap: 2000 trade resamples (seed 42), 95% percentile interval of mean R; ignores serial correlation.",
          ""]
    L += ["   Walk-forward models and trades:"]
    for m in wf_meta:
        L.append(f"   {m['window']}: train rows {m['train_rows']} (labels through {m['train_end']}), window "
                 f"{m['window_start']} -> {m['window_end']}, feature rows {m['feature_rows']}, signals BUY "
                 f"{m['buy_signals']} / SELL {m['sell_signals']}, trades {m['trades']}, skipped {m['skipped']}")
    L += [f"   Main validation: {len(main)} trades ({main['entry_time'].min()} -> {main['exit_time'].max()}); "
          f"walk-forward: {len(wf)} trades.", ""]

    L += ["3. PRE-DECLARED RULES",
          f"   LOW_SAMPLE: fewer than {MIN_TRADES} trades (not interpreted).",
          f"   WF candidate: >= {MIN_TRADES} walk-forward trades; >= {MIN_WINDOW_TRADES} trades in >= "
          f"{MIN_WINDOWS_POPULATED} windows; avg R > 0 in >= {MIN_POSITIVE_WINDOWS} of 3 windows;",
          f"   mean of window avg R > +{MIN_WF_MEAN_R}R; no window below {WORST_WINDOW_R}R (all 3 windows traded); pooled",
          "   walk-forward bootstrap CI not entirely negative.",
          f"   FDR: one-sided t-test of mean R > 0 on pooled walk-forward trades for every group with >= {MIN_TRADES}",
          f"   walk-forward trades; Benjamini-Hochberg at q = {FDR_Q}. Groups overlap (dependent tests).",
          "   Classification: REPEATED_BEHAVIOUR_CANDIDATE = WF candidate that survives FDR; MULTIPLE_TESTING_ARTIFACT_RISK",
          "   = WF candidate that does not; VALIDATION_PERIOD_NOISE = profitable in the main validation period (>= 100",
          "   trades) but not a WF candidate; LOW_SAMPLE = < 100 walk-forward trades; NO_EDGE = otherwise.",
          "   Conclusion B only if at least one REPEATED_BEHAVIOUR_CANDIDATE exists; otherwise A.", ""]

    L += ["4. MAIN VALIDATION PERIOD - ALL GROUPS (saved model, existing trades)"] + main_table(g) + [""]
    L += ["5. WALK-FORWARD CONDITIONAL ANALYSIS - ALL GROUPS (+/- = positive/negative windows)"] + wf_table(g)
    pooled = g[["dimension", "group", "wf_pooled_total_r", "wf_pooled_median_r", "wf_pooled_win_rate",
                "wf_pooled_profit_factor", "wf_pooled_std_r", "wf_pooled_longest_losing_streak"]]
    L += ["", "   Pooled walk-forward statistics for groups with >= 100 walk-forward trades:",
          f"   {'dimension':<15}{'group':<28}{'totR':>8} {'medR':>8} {'win%':>6} {'PF':>6} {'stdR':>6} {'streak':>6}"]
    for _, r in pooled[g["wf_sufficient"]].iterrows():
        L.append(f"   {r.dimension:<15}{r.group:<28}{f(r.wf_pooled_total_r, '+.2f'):>8} {f(r.wf_pooled_median_r):>8} "
                 f"{r.wf_pooled_win_rate * 100:>6.1f} {f(r.wf_pooled_profit_factor, '.3f'):>6} "
                 f"{f(r.wf_pooled_std_r, '.3f'):>6} {int(r.wf_pooled_longest_losing_streak):>6}")
    L.append("")

    cands = g[g["wf_candidate"]]
    L += ["6. WF CANDIDATES (criteria detail)"]
    if cands.empty:
        L.append("   none")
    for _, r in cands.iterrows():
        L.append(f"   {r.dimension} {r.group}: WF mean {r.wf_mean_avg_r:+.4f}R, windows "
                 + ", ".join(f"{w} {int(r[f'{w}_trades'])} @ {r[f'{w}_avg_r']:+.4f}" for w in WF)
                 + f"; main {int(r.main_trades)} @ {f(r.main_avg_r)}; FDR-adjusted p {f(r.fdr_adjusted_p, '.3f')} -> "
                 f"{r.classification}")
    near = g[g["wf_sufficient"] & ~g["wf_candidate"]].copy()
    near["failed"] = near[[c for c in g.columns if c.startswith("crit_")]].apply(
        lambda s: ", ".join(c.replace("crit_", "") for c, ok in s.items() if not ok), axis=1)
    near = near.sort_values("wf_mean_avg_r", ascending=False).head(5)
    L += ["   Highest walk-forward means among non-candidates (for context, not selection):"]
    L += [f"   {r.dimension} {r.group}: WF mean {f(r.wf_mean_avg_r)}R, failed: {r.failed}" for _, r in near.iterrows()]
    L.append("")

    L += ["7. MULTIPLE-COMPARISONS SUMMARY"] + [f"   {k}: {v}" for k, v in summary.items()]
    L += ["   About 5% of independent null groups would show a CI excluding zero, and many more a positive mean,",
          "   by chance alone; groups here overlap heavily, so counts are not independent evidence.", ""]

    L += ["8. LEAKAGE, INTEGRITY AND TEST-DATA SAFETY CHECKS"] + [f"   {c}" for c in checks["lines"]] + [""]
    L += ["9. FILE HASHES (identical before and after the run)"]
    L += [f"   {k:<40} {hashes[k][0]:<19} {hashes[k][1]}" for k in KEY_FILES]
    L += [f"   ... {len(hashes)} files in src/, src/data/, src/models/ checked in total; all unchanged.", ""]

    L += ["10. LIMITATIONS",
          "   - Three walk-forward windows of about five weeks each; a group needs consistent behaviour in each, so",
          "     weak effects cannot be distinguished from noise.",
          "   - Walk-forward trades come from re-trained models with the same configuration, not the saved model.",
          "   - Trade-level bootstrap and t-tests treat trades as independent; neighbouring trades are correlated.",
          "   - Groups overlap and share trades, so the FDR correction is approximate.",
          "   - Session/hour labels come from the existing feature pipeline unchanged.",
          "   - Nothing here is a trading rule; any subgroup would need data that played no part in this analysis.",
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
    for path in (RAW_PATH, FEATURES_PATH):
        GUARD["safe_nrows"][path.resolve()] = rows_through(path, cutoff_str)
    assert RF_PARAMS == FIXED_RF, "RF parameters differ from the fixed configuration"

    # Baseline integrity: saved model reproduces the existing validation trades exactly.
    model, model_features = load_model(MODEL_PATH)
    assert model_features == RF_FEATURES and model.get_params()["n_estimators"] == FIXED_RF["n_estimators"]
    val, bt_start, bt_end = load_validation_period(VALIDATION_PATH)
    raw_bt, feats_bt, pos_bt, _ = load_market(bt_start, bt_end)
    assert_no_test_rows(raw_bt)
    check_against_validation(feats_bt, val, model_features)
    regenerated, _ = run_backtest(raw_bt, feats_bt, pos_bt, generate_signals(model, feats_bt, model_features))
    existing = pd.read_csv(TRADES_PATH)
    regenerated = normalize_trades(regenerated)
    main_trades = normalize_trades(existing)
    assert len(regenerated) == len(main_trades), "trade count differs from the existing trades file"
    assert (regenerated["signal_time"].to_numpy() == main_trades["signal_time"].to_numpy()).all()
    assert (regenerated["side"].to_numpy() == main_trades["side"].to_numpy()).all()
    assert np.allclose(regenerated["net_pnl_r"], main_trades["net_pnl_r"], atol=1e-9)
    print(f"baseline integrity: saved model reproduces all {len(main_trades)} existing validation trades")

    # Labels, splits and walk-forward windows.
    raw, features, positions = load_research_data(val_end, cutoff)
    for frame in (raw, features):
        assert_no_test_rows(frame)
        assert frame["time"].is_unique and frame["time"].is_monotonic_increasing
    labels = build_labels(raw, features, positions, 1.5, 1.0, HORIZON_BARS)
    keep = ~labels["excluded"].to_numpy()
    full_labeled = features[keep].assign(**{TARGET_COLUMN: labels.loc[keep, TARGET_COLUMN].to_numpy()})
    train_full, val_full = purged_split(full_labeled, HORIZON_BARS, val_start, val_end, inclusive_stop=True)
    _, _, model_full = evaluate_rf_only(train_full, val_full)
    check_current_reproduced(labels, train_full, val_full, model_full)
    print("labels, train/validation splits and saved-model predictions reproduced")

    times = features["time"]
    starts = [times.iloc[int(len(times) * q)] for q in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"
    wf_trades, wf_meta = walk_forward_trades(raw, features, full_labeled, wf_windows)
    assert wf_trades["exit_time"].max() <= cutoff and main_trades["exit_time"].max() <= cutoff
    print("walk-forward trades: " + ", ".join(f"{m['window']} {m['trades']}" for m in wf_meta))

    train_times = pd.to_datetime(pd.read_csv(TRAIN_PATH, usecols=["time"])["time"], format=TIME_FORMAT)
    assert train_times.max() < val_start
    atr_edges, _ = atr_pct_bucket_edges()
    main_ctx = attach_context(main_trades, features, atr_edges)
    wf_ctx = attach_context(wf_trades, features, atr_edges)

    g = analyse_groups(main_ctx, wf_ctx)
    tested = g[g["wf_sufficient"]]
    summary = {
        "groups defined": len(g),
        "groups with >= 1 main-validation trade": int((g["main_trades"] > 0).sum()),
        "groups LOW_SAMPLE in main validation (< 100 trades)": int(g["main_low_sample"].sum()),
        "groups profitable in main validation (avg R > 0, any size)": int(g["main_profitable"].sum()),
        "groups profitable in main validation with >= 100 trades": int((g["main_profitable"] & ~g["main_low_sample"]).sum()),
        "groups tested walk-forward (>= 100 walk-forward trades)": len(tested),
        "groups positive in all 3 windows": int((tested["wf_positive_windows"] == 3).sum()),
        "groups satisfying the WF criteria": int(g["wf_candidate"].sum()),
        f"groups significant after Benjamini-Hochberg (q={FDR_Q}), any sign of WF criteria": int(g["fdr_reject"].sum()),
        "groups satisfying the WF criteria AND surviving FDR": int(g["wf_candidate_after_fdr"].sum()),
        "classification counts": ", ".join(f"{k} {v}" for k, v in g["classification"].value_counts().items()),
    }
    conclusion = ("Potential conditional edge found, but requires independent confirmation."
                  if g["wf_candidate_after_fdr"].any() else "No stable conditional edge found.")

    hashes_after = snapshot(skip, cutoff_str)
    changed = sorted(k for k in set(hashes_before) | set(hashes_after) if hashes_before.get(k) != hashes_after.get(k))
    if changed:
        raise AssertionError(f"existing files changed: {changed}")
    assert GUARD["test_open_attempts"] == 0 and TEST_PATH.resolve() not in GUARD["csv_reads"]
    assert hashes_before["models/rf_m5_baseline.pkl"] == hashes_after["models/rf_m5_baseline.pkl"]

    reads = sorted({p.name for p in GUARD["csv_reads"]})
    inputs = {
        "src/models/rf_m5_baseline.pkl": "saved RF (joblib, read only)",
        "src/data/rf_m5_validation_trades.csv": f"{len(existing)} trades",
        "src/data/xauusd_m5_validation.csv": f"{len(val)} rows",
        "src/data/xauusd_m5_train.csv": f"{len(train_times)} rows (ATR% quartile edges, label/split check)",
        "src/data/xauusd_m5.csv": f"{len(raw)} rows read (through {cutoff_str}; nothing after)",
        "src/data/xauusd_m5_features.csv": f"{GUARD['safe_nrows'][FEATURES_PATH.resolve()]} rows read (through "
                                           f"{cutoff_str}); {len(features)} rows used (through {val_end})",
        "CSV files actually opened by pandas": ", ".join(reads),
    }
    checks = {
        "atr_edges": ", ".join(f"{e:.4%}" for e in atr_edges[1:-1]),
        "lines": [
            f"[PASS] Baseline integrity: the saved model regenerates all {len(main_trades)} existing validation trades "
            "(same signal times, sides and net R) with the unchanged backtest engine.",
            "[PASS] Labels and splits: rebuilt labels, train rows and validation rows match xauusd_m5_train.csv and "
            "xauusd_m5_validation.csv; a model retrained with the fixed parameters predicts identically to the saved model.",
            "[PASS] Saved RF model not modified: SHA-256 identical before and after; only loaded with joblib.",
            "[PASS] Walk-forward models: each trained only on rows whose 12-bar label window ends before the window "
            "start (asserted); windows identical to all earlier experiments.",
            "[PASS] No future information in signals or trades: signals depend only on their own closed bar (prefix "
            "check inside generate_signals); every entry is the next bar's open after the signal; group context is "
            "the signal-bar feature row (ATR cross-checked against each trade).",
            f"[PASS] Bucket edges: RSI edges fixed; ATR% quartiles from the training split only (ends "
            f"{train_times.max()} < validation start {val_start}).",
            f"[PASS] No test-period data: raw/feature reads capped at {cutoff_str}; every frame and trade exit <= cutoff; "
            f"audit hook recorded {GUARD['test_open_attempts']} attempts to open xauusd_m5_test.csv.",
            "[PASS] Integrity hashing read no byte after the cutoff: files containing later rows were hashed only up to "
            "the cutoff row (plus size/mtime); the test CSV and legacy files of unknown range by size/mtime only.",
            f"[PASS] Existing files unchanged: {len(hashes_before)} files compared before and after.",
        ],
    }
    lines = build_report(g, main_ctx, wf_ctx, wf_meta, inputs, hashes_after, checks, summary, conclusion)
    assert lines[-1] in ("No stable conditional edge found.",
                         "Potential conditional edge found, but requires independent confirmation.")

    meta_rows = pd.DataFrame([{"section": "wf_model", **{k: str(v) for k, v in m.items()}} for m in wf_meta])
    summ_rows = pd.DataFrame([{"section": "summary", "dimension": k, "group": str(v)} for k, v in summary.items()]
                             + [{"section": "summary", "dimension": "conclusion", "group": conclusion}])
    pd.concat([g, meta_rows, summ_rows], ignore_index=True).to_csv(RESULTS_PATH, index=False)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    final = snapshot(skip, cutoff_str)
    assert final == hashes_before, "existing files changed while writing outputs"

    base = g[(g.dimension == "SIDE") & (g.group == "ALL")].iloc[0]
    print("\nFINAL SUMMARY")
    print(f"  main validation (saved model): {int(base.main_trades)} trades, avg {base.main_avg_r:+.4f}R")
    print("  walk-forward (retrained, ALL): " + ", ".join(f"{w} {int(base[f'{w}_trades'])} @ {base[f'{w}_avg_r']:+.4f}R"
                                                       for w in WF) + f"; mean {base.wf_mean_avg_r:+.4f}R")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  test data opened: no ({GUARD['test_open_attempts']} attempts); existing files changed: none "
          f"({len(hashes_before)} checked); saved model unchanged")
    print(f"  conclusion: {conclusion}")
    print(f"  outputs: {RESULTS_PATH}\n           {REPORT_PATH}")


if __name__ == "__main__":
    main()
