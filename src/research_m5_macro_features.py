"""Research: does external macro information (US dollar index, US Treasury yields)
improve out-of-sample classification of the current XAUUSD M5 label?

Diagnostic only. Nothing is tuned and no production strategy is produced.

* Label: current label (TP 1.5 ATR / SL 1.0 ATR / 12 bars), rebuilt with the
  verified research_m5_label_horizon.build_labels.
* Baseline: the existing 30 RF_FEATURES; each configuration adds one or both of
  two pre-defined macro families. RF parameters are the fixed train_rf_m5.RF_PARAMS.
* Evaluation: existing train/validation boundary plus the same three walk-forward
  windows as the earlier experiments; primary metric = walk-forward balanced
  accuracy. A backtest with the unchanged engine is a secondary diagnostic only.
* External data comes from fetch_m5_macro_data.py (new files):
    - DXY: rebuilt from the six ICE component pairs (M5, same MT5 server and clock
      as xauusd_m5.csv). A DXY bar exists only where all six pairs have a bar; DXY
      bar tau is usable at XAUUSD row t iff tau <= t (both close at the same instant)
      and t - tau <= DXY_MAX_STALENESS.
    - Yields: FRED daily DGS2/DGS10. The value for observation date D is treated as
      known only from D + YIELD_AVAILABLE_AFTER (00:00 on D+2 in the XAUUSD clock),
      a conservative lag covering publication delay and the broker-clock offset.

Test safety: the guards of research_kronos_m5 are reused (raw/feature CSVs are read
only up to the last purge-gap bar; any attempt to open the test CSV raises).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from backtest_rf_m5 import WARNINGS as BACKTEST_WARNINGS
from backtest_rf_m5 import check_against_validation, generate_signals, load_market, load_validation_period, run_backtest
from features_m5 import BAR_MINUTES
from fetch_m5_macro_data import DXY_BASKET_PATH, DXY_PAIRS, TREASURY_PATH
from label_m5 import FEATURES_PATH, RAW_PATH, TARGET_COLUMN, TARGET_NAMES
from research_kronos_m5 import GUARD, assert_no_test_rows, install_guards, rows_through, snapshot_files
from research_m5_feature_families import evaluate, near_duplicates, paired_block_bootstrap
from research_m5_label_horizon import (
    FIXED_RF,
    build_labels,
    check_current_reproduced,
    load_research_data,
    purged_split,
    research_boundary,
)
from research_m5_label_horizon import evaluate as evaluate_rf_only
from research_rf_m5_model_comparison import trade_metrics
from train_rf_m5 import FORBIDDEN_INPUTS, MODEL_PATH, RF_FEATURES, RF_PARAMS, TRAIN_PATH, VALIDATION_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
RESULTS_PATH = DATA_DIR / "m5_macro_feature_research.csv"
REPORT_PATH = DATA_DIR / "m5_macro_feature_research_report.txt"

BAR = pd.Timedelta(minutes=BAR_MINUTES)
CLASS_ORDER = [1, -1, 0]
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
CHANCE = 1 / 3

# ICE US Dollar Index formula (constant and component weights).
DXY_CONSTANT = 50.14348112
DXY_WEIGHTS = {"EURUSD": -0.576, "USDJPY": 0.136, "GBPUSD": -0.119, "USDCAD": 0.091, "USDSEK": 0.042, "USDCHF": 0.036}
DXY_MAX_STALENESS = pd.Timedelta(minutes=15)
YIELD_AVAILABLE_AFTER = pd.Timedelta(days=2)
YIELD_MAX_STALENESS = pd.Timedelta(days=7)

WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]

CONFIGS = {"BASELINE": [], "DXY": ["DXY"], "YIELDS": ["YIELDS"], "DXY_YIELDS": ["DXY", "YIELDS"]}
FAMILY_NAMES = {"DXY": "FAMILY_DXY (US Dollar Index, M5)", "YIELDS": "FAMILY_YIELDS (US 2Y/10Y, daily)"}

# Decision and warning rules, fixed before any result is seen (same as earlier experiments).
MEANINGFUL_DELTA = 0.01
GAP_ABSOLUTE_WARNING = 0.10
GAP_INCREASE_WARNING = 0.03
LEAKAGE_CHECK_POINTS = 12

TEST_STATEMENT = "The untouched TEST dataset was not loaded, opened or used."

DESCRIPTIONS = {
    "dxy_ret_1": "DXY log return over 1 M5 bar", "dxy_ret_3": "DXY log return over 3 bars",
    "dxy_ret_6": "DXY log return over 6 bars", "dxy_ret_12": "DXY log return over 12 bars",
    "dxy_mom_48": "DXY momentum: log return over 48 bars (4 hours)",
    "dxy_vol_12": "std of DXY 1-bar log returns, 12 bars", "dxy_vol_48": "std of DXY 1-bar log returns, 48 bars",
    "dxy_trend_dir": "DXY direction: +1 if EMA9>EMA20>EMA50, -1 if reversed, else 0",
    "dxy_dist_ema_20": "DXY / EMA20 - 1", "dxy_dist_ema_50": "DXY / EMA50 - 1",
    "us2y_chg_1d": "US 2Y yield change vs previous published day (bp)",
    "us2y_chg_5d": "US 2Y yield change over 5 published days (bp)",
    "us10y_chg_1d": "US 10Y yield change vs previous published day (bp)",
    "us10y_chg_5d": "US 10Y yield change over 5 published days (bp)",
    "curve_10y_2y": "10Y - 2Y yield spread (percentage points)",
    "curve_chg_5d": "change of the 10Y - 2Y spread over 5 published days (bp)",
}
FAMILIES = {"DXY": [c for c in DESCRIPTIONS if c.startswith("dxy_")],
            "YIELDS": [c for c in DESCRIPTIONS if not c.startswith("dxy_")]}


# --------------------------------------------------------------------------
# External data
# --------------------------------------------------------------------------

def load_external(cutoff: pd.Timestamp):
    basket = pd.read_csv(DXY_BASKET_PATH)
    basket["time"] = pd.to_datetime(basket["time"], format="%Y-%m-%d %H:%M:%S")
    treasury = pd.read_csv(TREASURY_PATH)
    treasury["observation_date"] = pd.to_datetime(treasury["observation_date"], format="%Y-%m-%d")
    assert basket["time"].is_monotonic_increasing and basket["time"].is_unique
    assert basket["time"].max() <= cutoff, "external FX data extends past the research boundary"
    assert treasury["observation_date"].max() <= cutoff.normalize()
    return basket, treasury


def dxy_series(basket: pd.DataFrame) -> pd.DataFrame:
    closes = basket[[f"{p}_close" for p in DXY_PAIRS]]
    complete = closes.notna().all(axis=1).to_numpy() & (closes > 0).all(axis=1).to_numpy()
    b = basket[complete]
    log_dxy = np.log(DXY_CONSTANT) + sum(w * np.log(b[f"{p}_close"]) for p, w in DXY_WEIGHTS.items())
    return pd.DataFrame({"dxy_time": b["time"].to_numpy(), "dxy": np.exp(log_dxy).to_numpy()})


def dxy_features(dxy: pd.DataFrame) -> pd.DataFrame:
    level = dxy["dxy"]
    log_level = np.log(level)
    r1 = log_level.diff()
    ema = {s: level.ewm(span=s, min_periods=s, adjust=False).mean() for s in (9, 20, 50)}
    trend = np.select([(ema[9] > ema[20]) & (ema[20] > ema[50]), (ema[9] < ema[20]) & (ema[20] < ema[50])],
                      [1.0, -1.0], 0.0)
    out = dxy[["dxy_time"]].copy()
    for k in (1, 3, 6, 12):
        out[f"dxy_ret_{k}"] = log_level.diff(k)
    out["dxy_mom_48"] = log_level.diff(48)
    out["dxy_vol_12"] = r1.rolling(12).std()
    out["dxy_vol_48"] = r1.rolling(48).std()
    out["dxy_trend_dir"] = pd.Series(trend, index=dxy.index).where(ema[50].notna())
    out["dxy_dist_ema_20"] = level / ema[20] - 1
    out["dxy_dist_ema_50"] = level / ema[50] - 1
    return out


def yield_features(treasury: pd.DataFrame) -> pd.DataFrame:
    t = treasury.dropna(subset=["DGS2", "DGS10"]).sort_values("observation_date").reset_index(drop=True)
    curve = t["DGS10"] - t["DGS2"]
    return pd.DataFrame({
        "observation_date": t["observation_date"],
        "available_at": t["observation_date"] + YIELD_AVAILABLE_AFTER,
        "us2y_chg_1d": t["DGS2"].diff() * 100, "us2y_chg_5d": t["DGS2"].diff(5) * 100,
        "us10y_chg_1d": t["DGS10"].diff() * 100, "us10y_chg_5d": t["DGS10"].diff(5) * 100,
        "curve_10y_2y": curve, "curve_chg_5d": curve.diff(5) * 100,
    })


def build_macro(basket, treasury, times: pd.Series, leaky_dxy=False, leaky_yields=False) -> pd.DataFrame:
    """Macro features for XAUUSD rows `times` using only information known at each row."""
    left = pd.DataFrame({"time": times.to_numpy()})
    dxy = dxy_features(dxy_series(basket))
    if leaky_dxy:   # control only: the first DXY bar AFTER t
        m_dxy = pd.merge_asof(left, dxy, left_on="time", right_on="dxy_time", direction="forward",
                              allow_exact_matches=False)
    else:
        m_dxy = pd.merge_asof(left, dxy, left_on="time", right_on="dxy_time", direction="backward",
                              tolerance=DXY_MAX_STALENESS)
    y = yield_features(treasury)
    key = "observation_date" if leaky_yields else "available_at"   # leaky: value used on its own date
    m_y = pd.merge_asof(left, y.sort_values(key), left_on="time", right_on=key, direction="backward",
                        tolerance=YIELD_MAX_STALENESS)
    out = pd.concat([left, m_dxy.drop(columns="time"), m_y.drop(columns="time")], axis=1)
    return out.replace([np.inf, -np.inf], np.nan)


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------

def known_at(basket, treasury, t):
    """External rows that exist by time t (true availability)."""
    return (basket[basket["time"] <= t],
            treasury[treasury["observation_date"] + YIELD_AVAILABLE_AFTER <= t])


def prefix_invariance(basket, treasury, times, full, cols, check_times, **leaky) -> tuple[int, int]:
    detected, compared = 0, 0
    for t in check_times:
        b, tr = known_at(basket, treasury, t)
        sub_times = times[times <= t].reset_index(drop=True)
        prefix = build_macro(b, tr, sub_times, **leaky)
        a = prefix[cols].to_numpy(float)
        ref = full.iloc[:len(prefix)][cols].to_numpy(float)
        bad = ~np.isclose(a, ref, rtol=1e-9, atol=1e-15, equal_nan=True)
        compared += a.size
        detected += bool(bad.any())
    return detected, compared


def alignment_checks(full: pd.DataFrame, basket, treasury) -> dict:
    t = full["time"]
    dxy_times = dxy_series(basket)["dxy_time"]
    ok = full["dxy_time"].notna()
    src = full.loc[ok, "dxy_time"]
    assert (src <= t[ok]).all(), "a DXY bar after the prediction timestamp was used"
    assert ((t[ok] - src) <= DXY_MAX_STALENESS).all()
    nxt_idx = np.searchsorted(dxy_times.to_numpy(), src.to_numpy(), side="right")
    nxt = pd.Series(np.append(dxy_times.to_numpy(), np.datetime64("NaT"))[nxt_idx], index=src.index)
    assert ((nxt > t[ok]) | nxt.isna()).all(), "a more recent DXY bar was available but not used"

    oky = full["available_at"].notna()
    assert (full.loc[oky, "available_at"] <= t[oky]).all(), "a yield value was used before it was published"
    assert (full.loc[oky, "observation_date"] + YIELD_AVAILABLE_AFTER <= t[oky]).all()
    avail = yield_features(treasury)["available_at"].to_numpy()
    nxt_y = np.append(avail, np.datetime64("NaT"))[np.searchsorted(avail, full.loc[oky, "available_at"].to_numpy(),
                                                                   side="right")]
    assert ((nxt_y > t[oky].to_numpy()) | pd.isna(nxt_y)).all(), "a newer published yield was not used"
    lag = (t[oky] - full.loc[oky, "observation_date"]).dt.total_seconds() / 86400
    return {"dxy_rows": int(ok.sum()), "dxy_max_staleness_min": float((t[ok] - src).max().total_seconds() / 60),
            "dxy_exact_same_bar": int((t[ok] == src).sum()), "yield_rows": int(oky.sum()),
            "yield_min_lag_days": float(lag.min()), "yield_max_lag_days": float(lag.max())}


# --------------------------------------------------------------------------
# Summary and report
# --------------------------------------------------------------------------

def summarize(ev: pd.DataFrame, boot: dict) -> pd.DataFrame:
    bal = ev.pivot(index="config", columns="evaluation", values="val_balanced_accuracy").reindex(list(CONFIGS))
    gap = ev.pivot(index="config", columns="evaluation", values="train_val_gap").reindex(list(CONFIGS))
    wf = ["WF1", "WF2", "WF3"]
    base = bal.loc["BASELINE"]
    rows = []
    for name in CONFIGS:
        delta = bal.loc[name] - base
        better, worse = int((delta[wf] > MEANINGFUL_DELTA).sum()), int((delta[wf] < -MEANINGFUL_DELTA).sum())
        row = {"section": "summary", "config": name, "families": "+".join(CONFIGS[name]) or "-",
               "feature_count": int(ev[ev.config == name]["feature_count"].iloc[0]),
               "main_val_balanced_accuracy": bal.loc[name, "main"],
               **{f"{w}_val_balanced_accuracy": bal.loc[name, w] for w in wf},
               "wf_mean_balanced_accuracy": bal.loc[name, wf].mean(),
               "wf_std_balanced_accuracy": bal.loc[name, wf].std(ddof=1),
               "main_gap": gap.loc[name, "main"], "wf_mean_gap": gap.loc[name, wf].mean(),
               "delta_main": delta["main"], **{f"delta_{w}": delta[w] for w in wf}, "delta_wf_mean": delta[wf].mean(),
               "wf_windows_better": better, "wf_windows_worse": worse}
        for e in ["main"] + wf:
            row[f"delta_{e}_ci_low"], row[f"delta_{e}_ci_high"] = boot.get((name, e), (np.nan, np.nan))
        warnings = []
        if name == "BASELINE":
            verdict = "-"
        else:
            verdict = ("CONSISTENT IMPROVEMENT" if better == 3 else "PARTIAL IMPROVEMENT" if better >= 2 and worse == 0
                       else "WORSE" if worse >= 2 else "NO CONSISTENT IMPROVEMENT")
            if row["main_gap"] > gap.loc["BASELINE", "main"] + GAP_INCREASE_WARNING:
                warnings.append(f"main gap exceeds baseline gap by > {GAP_INCREASE_WARNING}")
            if row["wf_mean_gap"] > gap.loc["BASELINE", wf].mean() + GAP_INCREASE_WARNING:
                warnings.append(f"walk-forward gap exceeds baseline by > {GAP_INCREASE_WARNING}")
            if delta["main"] > MEANINGFUL_DELTA and delta[wf].mean() <= MEANINGFUL_DELTA:
                warnings.append("main-split gain not confirmed by walk-forward mean")
        if row["main_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"main gap {row['main_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        if row["wf_mean_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"walk-forward mean gap {row['wf_mean_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        row["verdict"], row["warnings"] = verdict, "; ".join(warnings) or "none"
        rows.append(row)
    return pd.DataFrame(rows)


def pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


def eval_table(ev: pd.DataFrame, evaluation: str) -> str:
    sub = ev[ev["evaluation"] == evaluation].set_index("config").reindex(list(CONFIGS))
    cols = ["feature_count", "train_rows", "val_rows", "train_balanced_accuracy", "val_balanced_accuracy",
            "train_val_gap", "buy_precision", "buy_recall", "sell_precision", "sell_recall", "wait_precision",
            "wait_recall"]
    t = sub[cols].copy()
    for c in cols[3:]:
        t[c] = t[c].map(lambda v, c=c: f"{v:+.4f}" if c == "train_val_gap" else pct(v))
    t[cols[:3]] = t[cols[:3]].astype(int)
    return t.to_string()


def build_report(ev, summary, backtest, wf_windows, boundary, checks, confusions, sources) -> list[str]:
    val_start, val_end, cutoff = boundary
    s = summary.set_index("config")
    wf = ["WF1", "WF2", "WF3"]
    L = ["XAUUSD M5 external macro-feature research (classification diagnostic only)", "=" * 78, TEST_STATEMENT,
         "Label: current triple-barrier label (TP 1.5 ATR, SL 1.0 ATR, 12 bars), unchanged.",
         "Fixed RF for every configuration: " + ", ".join(f"{k}={v}" for k, v in RF_PARAMS.items()),
         f"Rows: {checks['research_rows']} labeled research rows used by every configuration "
         f"({checks['dropped_no_macro']} labeled rows dropped because a macro value was unavailable).",
         "Primary metric: out-of-sample balanced accuracy across the walk-forward windows. Backtest P&L is "
         "secondary and not used for selection.", ""]

    L += ["1. DATA SOURCES, ALIGNMENT AND VINTAGE",
          f"   DXY: rebuilt with the ICE formula {DXY_CONSTANT} x EURUSD^-0.576 x USDJPY^0.136 x GBPUSD^-0.119 x "
          "USDCAD^0.091 x USDSEK^0.042 x USDCHF^0.036",
          f"        from {sources['fx_source']} closes ({sources['fx_rows']:,} timestamps, {sources['dxy_rows']:,} with "
          "all six pairs; incomplete timestamps are dropped, never filled).",
          "        The XAUUSD file was verified bar-for-bar against the same MT5 server (identical OHLC/tick volume), "
          "so FX and XAUUSD share one clock.",
          f"        DXY bar tau is used at XAUUSD row t only if tau <= t and t - tau <= {DXY_MAX_STALENESS} "
          "(both bars close at the same instant).",
          f"   Yields: {sources['treasury_source']}, retrieved {sources['retrieved']} ({sources['treasury_dates']} "
          f"published days {sources['first_date']} -> {sources['last_date']}; holidays skipped, never filled).",
          f"        The value for date D is used only from D + {YIELD_AVAILABLE_AFTER.days} days 00:00 (XAUUSD clock): "
          "Treasury publishes D's curve on the evening of D (US time), FRED by the next business day, and the extra",
          "        margin absorbs the broker-clock offset. Yield features are therefore a 2-to-5-day-old daily backdrop.",
          "   Vintage limitation: FRED serves only the latest vintage. Treasury constant-maturity yields are market",
          "        quotes that are practically never revised, so the look-ahead risk from revisions is negligible but not",
          "        formally excluded (ALFRED vintages were not used).",
          "   Clock note: the XAUUSD feed opens at 01:00 while FX opens at 00:00, consistent with an EET-based broker",
          "        server clock (UTC+2/+3) rather than true UTC. This does not affect DXY alignment (same clock) and is",
          "        covered by the conservative yield lag.", "   The broker also lists a USDX symbol; it was not used.", ""]

    L += ["2. FEATURE DEFINITIONS (all causal)"]
    for fam, cols in FAMILIES.items():
        L.append(f"   {FAMILY_NAMES[fam]} ({len(cols)} features)")
        L += [f"     {c:<18} {DESCRIPTIONS[c]}" for c in cols]
    L.append("")

    L += ["3. FEATURE COUNTS"] + [f"   {n:<11} {int(s.loc[n, 'feature_count']):3d}  "
                                  + ("BASELINE + " + " + ".join(FAMILY_NAMES[f] for f in CONFIGS[n]) if CONFIGS[n]
                                     else "existing 30 RF_FEATURES") for n in CONFIGS] + [""]

    L += [f"4. MAIN SPLIT (existing boundary; validation {val_start} -> {val_end})", eval_table(ev, "main"), "",
          "   Confusion matrices (rows = true BUY/SELL/WAIT, columns = predicted BUY/SELL/WAIT):"]
    L += [f"   {n:<11} " + " | ".join(" ".join(f"{v:5d}" for v in row) for row in cm) for n, cm in confusions.items()]
    L.append("")

    L += ["5. WALK-FORWARD RESULTS (expanding train, 12-bar purge; same windows as earlier experiments)"]
    L += [f"   WF{i}: validation {a} -> {b}" for i, (a, b) in enumerate(wf_windows, 1)]
    for w in wf:
        L += [f"\n   {w}", eval_table(ev, w)]
    dist = ev[ev["evaluation"].isin(wf)].pivot(index="config", columns="evaluation",
                                               values=["buy_val_share", "sell_val_share", "wait_val_share"])
    L += ["", "   Validation class distribution (identical rows for every configuration):",
          dist.reindex(list(CONFIGS)).iloc[:1].apply(lambda c: c.map(pct)).to_string(), ""]

    t = s[["feature_count", "main_val_balanced_accuracy"] + [f"{w}_val_balanced_accuracy" for w in wf]
          + ["wf_mean_balanced_accuracy", "wf_std_balanced_accuracy"]].copy()
    t.columns = ["features", "main", *wf, "wf_mean", "wf_std"]
    for c in t.columns[1:]:
        t[c] = t[c].map(lambda v: f"{v:.4f}")
    L += ["6. AVERAGE WALK-FORWARD BALANCED ACCURACY AND STANDARD DEVIATION (sample std, n=3)", t.to_string(),
          f"   Chance level {CHANCE:.4f}.", ""]

    L += ["7. BASELINE COMPARISON (config - baseline; 95% paired block-bootstrap interval, 288-bar blocks)",
          "   The main validation period overlaps WF3, so main and WF3 are not independent evidence."]
    for n in list(CONFIGS)[1:]:
        r = s.loc[n]
        L.append(f"   {n}: " + "; ".join(f"{e} {r[f'delta_{e}']:+.4f} [{r[f'delta_{e}_ci_low']:+.4f}, "
                                         f"{r[f'delta_{e}_ci_high']:+.4f}]" for e in ["main"] + wf))
        L.append(f"      walk-forward mean delta {r['delta_wf_mean']:+.4f}; better by > {MEANINGFUL_DELTA} in "
                 f"{int(r['wf_windows_better'])}/3 windows, worse in {int(r['wf_windows_worse'])}/3")
    L.append("")

    L += ["8. GENERALIZATION / OVERFITTING WARNINGS (rules fixed before running)"]
    L += [f"   {n:<11} gap main {s.loc[n, 'main_gap']:+.4f}, walk-forward mean {s.loc[n, 'wf_mean_gap']:+.4f}: "
          f"{s.loc[n, 'warnings']}" for n in CONFIGS]
    for fam, d in checks["near_duplicates"].items():
        L.append(f"   {FAMILY_NAMES[fam]} near-duplicates of baseline features (|r| > 0.95): " +
                 (", ".join(f"{c} ~ {b} ({v:.3f})" for c, (b, v) in d.items()) or "none"))
    L.append("")

    L += ["9. LEAKAGE AND SAFETY CHECKS"] + [f"   {c}" for c in checks["lines"]] + [""]

    L += ["10. DOES EXTERNAL MACRO INFORMATION IMPROVE CONSISTENTLY?",
          f"   Rule: CONSISTENT = better by > {MEANINGFUL_DELTA} in all 3 walk-forward windows; PARTIAL = 2/3 with "
          f"none worse by > {MEANINGFUL_DELTA}; WORSE = worse in >= 2/3."]
    L += [f"   {n:<11} {s.loc[n, 'verdict']}" for n in list(CONFIGS)[1:]]
    consistent = [n for n in list(CONFIGS)[1:] if s.loc[n, "verdict"] == "CONSISTENT IMPROVEMENT"]
    partial = [n for n in list(CONFIGS)[1:] if s.loc[n, "verdict"] == "PARTIAL IMPROVEMENT"]
    L.append("   Answer: " + (f"yes - {', '.join(consistent)}." if consistent else
                              f"partially - {', '.join(partial)}." if partial else
                              "no; adding DXY and/or yield information did not improve walk-forward balanced "
                              "accuracy consistently."))
    L += ["   Three configurations were compared on the same windows; the best-looking delta is optimistically biased.",
          ""]

    L += ["11. RECOMMENDED NEXT RESEARCH STEP"]
    if consistent or partial:
        L += [f"   Treat {', '.join(consistent or partial)} as a hypothesis: confirm on more pre-defined walk-forward",
              "   folds and check stability of the macro features' importance before any cost-aware backtest across",
              "   folds. Keep the test set untouched."]
    else:
        L += ["   Dollar-index and daily-yield context did not add usable information for this 12-bar label, in line",
              "   with the earlier feature-family results. Remaining untested information is event-driven: a",
              "   scheduled US economic-calendar family (minutes to/from CPI, NFP, FOMC releases, with release times",
              "   fixed in advance) is the last cheap external test. If it also fails, the evidence points to the",
              "   label/horizon itself (e.g. a longer-horizon or volatility-conditioned target) rather than missing",
              "   inputs. Keep the test set untouched."]
    L.append("")

    bt = backtest.set_index("config").reindex(list(CONFIGS))
    L += ["APPENDIX - SECONDARY BACKTEST DIAGNOSTIC (main validation period; NOT used for selection)",
          "   Unchanged backtest_rf_m5 engine; models from the main split. $ per ounce; drawdown = closed-trade equity."]
    t = pd.DataFrame({
        "trades": bt["trades"].astype(int), "net_pnl": bt["net_pnl"].map("{:.2f}".format),
        "avg_r": bt["avg_r"].map("{:+.4f}".format), "profit_factor": bt["profit_factor"].map("{:.3f}".format),
        "max_dd": bt["max_closed_trade_dd"].map("{:.2f}".format), "buy_trades": bt["buy_trades"].astype(int),
        "buy_net": bt["buy_net_pnl"].map("{:.2f}".format), "buy_avg_r": bt["buy_avg_r"].map("{:+.4f}".format),
        "sell_trades": bt["sell_trades"].astype(int), "sell_net": bt["sell_net_pnl"].map("{:.2f}".format),
        "sell_avg_r": bt["sell_avg_r"].map("{:+.4f}".format)})
    L += [t.to_string(), "   One validation period; P&L differences between configurations are not evidence of edge."]
    L += [f"   - {w}" for w in BACKTEST_WARNINGS]
    L += ["", "No production strategy is recommended. All results are research diagnostics.", TEST_STATEMENT]
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
    hashes_before, test_stat_before = snapshot_files(skip)
    install_guards()
    assert RF_PARAMS == FIXED_RF, "train_rf_m5.RF_PARAMS differs from the fixed research configuration"

    boundary = research_boundary()
    val_start, val_end, cutoff = boundary
    GUARD["cutoff"] = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    for path in (RAW_PATH, FEATURES_PATH):
        GUARD["safe_nrows"][path.resolve()] = rows_through(path, GUARD["cutoff"])
    raw, features, positions = load_research_data(val_end, cutoff)
    assert_no_test_rows(raw)
    assert_no_test_rows(features)
    basket, treasury = load_external(cutoff)

    times = features["time"]
    starts = [times.iloc[int(len(times) * f)] for f in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"

    macro = build_macro(basket, treasury, times)
    macro_cols = [c for cols in FAMILIES.values() for c in cols]
    assert not set(macro_cols) & set(features.columns)
    align = alignment_checks(macro, basket, treasury)

    labels = build_labels(raw, features, positions, 1.5, 1.0, 12)
    keep = ~labels["excluded"].to_numpy()
    full_labeled = features[keep].assign(**{TARGET_COLUMN: labels.loc[keep, TARGET_COLUMN].to_numpy()})
    train_full, val_full = purged_split(full_labeled, 12, val_start, val_end, inclusive_stop=True)
    _, _, model_full = evaluate_rf_only(train_full, val_full)
    check_current_reproduced(labels, train_full, val_full, model_full)
    print("existing pipeline reproduced (labels, splits, saved model)")

    merged = pd.concat([features.reset_index(drop=True), macro[macro_cols]], axis=1)
    complete = np.isfinite(merged[macro_cols].to_numpy(float)).all(axis=1)
    research = merged[keep & complete].assign(
        **{TARGET_COLUMN: labels.loc[keep & complete, TARGET_COLUMN].to_numpy()}).reset_index(drop=True)
    dropped_no_macro = int((keep & ~complete).sum())

    check_times = [research["time"].iloc[int(f * (len(research) - 1))]
                   for f in np.linspace(0.05, 1.0, LEAKAGE_CHECK_POINTS)]
    detected, compared = prefix_invariance(basket, treasury, times, macro, macro_cols, check_times)
    assert detected == 0, "future external information detected"
    leaky_dxy, _ = prefix_invariance(basket, treasury, times, build_macro(basket, treasury, times, leaky_dxy=True),
                                     FAMILIES["DXY"], check_times, leaky_dxy=True)
    leaky_y, _ = prefix_invariance(basket, treasury, times, build_macro(basket, treasury, times, leaky_yields=True),
                                   FAMILIES["YIELDS"], check_times, leaky_yields=True)
    assert leaky_dxy > 0 and leaky_y > 0, "leakage test has no power"
    print(f"leakage checks passed ({compared:,} values; leaky controls detected DXY {leaky_dxy}, yields {leaky_y})")

    cols_by_config = {n: RF_FEATURES + [c for f in fams for c in FAMILIES[f]] for n, fams in CONFIGS.items()}
    for n, cols in cols_by_config.items():
        assert len(cols) == len(set(cols)) and not FORBIDDEN_INPUTS & set(cols), n
    splits = {"main": purged_split(research, 12, val_start, val_end, inclusive_stop=True)}
    for i, (a, b) in enumerate(wf_windows, 1):
        splits[f"WF{i}"] = purged_split(research, 12, a, b, inclusive_stop=i == 3)

    rows, confusions, preds, main_models = [], {}, {}, {}
    for name in CONFIGS:
        for ev_name, (train, val) in splits.items():
            out, cm, model, y_val, p_val = evaluate(train, val, cols_by_config[name])
            rows.append({"section": "evaluation", "config": name, "evaluation": ev_name,
                         "families": "+".join(CONFIGS[name]) or "-", **out})
            preds[(name, ev_name)] = (y_val, p_val)
            if ev_name == "main":
                confusions[name], main_models[name] = cm, model
        print(f"finished {name:<11} features {len(cols_by_config[name])}  main {rows[-4]['val_balanced_accuracy']:.4f}  "
              f"walk-forward mean {np.mean([r['val_balanced_accuracy'] for r in rows[-3:]]):.4f}")
    ev = pd.DataFrame(rows)

    boot = {}
    for name in list(CONFIGS)[1:]:
        for e in splits:
            y, p = preds[(name, e)]
            boot[(name, e)] = paired_block_bootstrap(y, p, preds[("BASELINE", e)][1])
    summary = summarize(ev, boot)
    dupes = near_duplicates(splits["main"][0], FAMILIES)

    # Secondary backtest diagnostic with the unchanged engine.
    val_bt, bt_start, bt_end = load_validation_period(VALIDATION_PATH)
    raw_bt, feats_bt, pos_bt, _ = load_market(bt_start, bt_end)
    assert_no_test_rows(raw_bt)
    check_against_validation(feats_bt, val_bt, RF_FEATURES)
    feats_bt = pd.concat([feats_bt.reset_index(drop=True),
                          build_macro(basket, treasury, feats_bt["time"])[macro_cols]], axis=1)
    assert np.isfinite(feats_bt[macro_cols].to_numpy(float)).all(), "macro value missing in the validation period"
    bt_rows = []
    for name, model in main_models.items():
        trades, _ = run_backtest(raw_bt, feats_bt, pos_bt, generate_signals(model, feats_bt, cols_by_config[name]))
        m = trade_metrics(trades)
        for side in ("BUY", "SELL"):
            m.update(trade_metrics(trades[trades["side"] == side], prefix=f"{side.lower()}_"))
        bt_rows.append({"section": "backtest", "config": name, "evaluation": "main_validation_backtest", **m})
    backtest = pd.DataFrame(bt_rows)

    hashes_after, test_stat_after = snapshot_files(skip)
    changed = sorted(str(p) for p in set(hashes_before) | set(hashes_after) if hashes_before.get(p) != hashes_after.get(p))
    if changed:
        raise AssertionError(f"existing files changed: {changed}")
    assert test_stat_after == test_stat_before and GUARD["test_open_attempts"] == 0

    reads = ", ".join(sorted({p.name for p in GUARD["csv_reads"]}))
    base_main = summary.set_index("config").loc["BASELINE"]
    checks = {
        "research_rows": len(research), "dropped_no_macro": dropped_no_macro, "near_duplicates": dupes,
        "lines": [
            f"[PASS] No future external values: every macro feature was recomputed from only the FX bars and yield "
            f"publications known at t, at {len(check_times)} check points; all {compared:,} values for rows <= t matched.",
            f"[PASS] Check has power: a DXY control using the next bar after t was detected at {leaky_dxy}/"
            f"{len(check_times)} check points; a yield control using a value on its own date at {leaky_y}/"
            f"{len(check_times)}.",
            f"[PASS] DXY alignment: on all {align['dxy_rows']:,} rows the DXY bar used is at or before t and is the most "
            f"recent one ({align['dxy_exact_same_bar']:,} use the bar with the same timestamp; max staleness "
            f"{align['dxy_max_staleness_min']:.0f} min).",
            f"[PASS] Yield alignment: on all {align['yield_rows']:,} rows the value used was published by the "
            f"conservative rule and is the newest such value (age {align['yield_min_lag_days']:.1f}-"
            f"{align['yield_max_lag_days']:.1f} days after its observation date).",
            "[PASS] No filling: incomplete FX timestamps were dropped and holidays skipped; only the last published "
            "value is carried until a newer one exists, within fixed staleness limits.",
            f"[PASS] Test data not accessed: XAUUSD CSVs read only up to {GUARD['cutoff']}; external data ends at "
            f"{basket['time'].max()} / {treasury['observation_date'].max().date()}; CSVs read: {reads}; audit hook "
            "recorded 0 attempts to open the test CSV.",
            f"[PASS] Existing files unchanged: SHA-256 of {len(hashes_before)} files in src/, src/data/, src/models/ "
            "identical before and after (test CSV checked by size/modification time only, never opened).",
            "[PASS] Existing pipeline reproduced: labels, train/validation rows and the retrained RF match the "
            "existing CSVs and the saved model; walk-forward windows identical to the earlier experiments.",
            f"[INFO] BASELINE on the common rows: main {base_main['main_val_balanced_accuracy']:.4f}, walk-forward "
            f"{base_main['WF1_val_balanced_accuracy']:.4f} / {base_main['WF2_val_balanced_accuracy']:.4f} / "
            f"{base_main['WF3_val_balanced_accuracy']:.4f}.",
        ],
    }
    sources = {"fx_source": basket["source"].iloc[0], "fx_rows": len(basket), "dxy_rows": len(dxy_series(basket)),
               "treasury_source": treasury["source"].iloc[0], "retrieved": treasury["retrieved_utc"].iloc[0] + " UTC",
               "treasury_dates": int(treasury[["DGS2", "DGS10"]].notna().all(axis=1).sum()),
               "first_date": treasury["observation_date"].min().date(),
               "last_date": treasury["observation_date"].max().date()}

    definitions = pd.DataFrame([{"section": "feature_definition", "config": FAMILY_NAMES[f], "feature": c,
                                 "description": DESCRIPTIONS[c]} for f, cols in FAMILIES.items() for c in cols])
    pd.concat([summary, ev, backtest, definitions], ignore_index=True).to_csv(RESULTS_PATH, index=False)
    lines = build_report(ev, summary, backtest, wf_windows, boundary, checks, confusions, sources)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert snapshot_files(skip)[0] == hashes_before, "existing files changed while writing outputs"
    print()
    print("\n".join(lines))
    print(f"\nSaved results: {RESULTS_PATH}")
    print(f"Saved report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()
