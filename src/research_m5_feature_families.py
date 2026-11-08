"""Research: do pre-defined, information-rich feature families improve out-of-sample
classification of the current XAUUSD M5 label (TP 1.5 ATR / SL 1.0 ATR / 12 bars)?

Diagnostic only. Nothing is tuned and no production strategy is produced.

* Label: the current label, rebuilt with research_m5_label_horizon.build_labels
  (verified to reproduce the existing train/validation labels and saved model).
* Baseline: the existing 30 RF_FEATURES. Each configuration adds one or two of
  four pre-defined families computed here from raw M5 bars; features_m5.py and
  every existing file are untouched.
* Model: the fixed train_rf_m5.RF_PARAMS for every configuration.
* Evaluation: the existing train/validation boundary plus the same three
  walk-forward windows as the label-horizon experiment. The primary metric is
  out-of-sample balanced accuracy across the walk-forward windows.
* All configurations use the same rows: rows whose new features are still in
  their warm-up period are dropped for every configuration, baseline included.
* Higher-timeframe features use only the most recently COMPLETED candle: an
  M15/M30/H1 candle starting at s becomes usable at the M5 bar s + period - 5 min,
  whose close completes it.
* A cost-aware backtest with the unchanged backtest_rf_m5 engine is run after
  classification as a secondary diagnostic and is never used to select features.

Data boundary: bars up to the last validation bar + 12 bars (inside the purge gap
before the test split). Test-period rows in the shared raw/feature files are
discarded immediately after reading; the test CSV is never opened (enforced).
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, precision_recall_fscore_support

from backtest_rf_m5 import WARNINGS as BACKTEST_WARNINGS
from backtest_rf_m5 import (
    check_against_validation,
    generate_signals,
    load_market,
    load_validation_period,
    run_backtest,
)
from features_m5 import BAR_MINUTES, SESSIONS, add_atr, add_rsi
from label_m5 import ATR_COLUMN, BUY, SELL, TARGET_COLUMN, TARGET_NAMES, WAIT
from research_m5_label_horizon import (
    FIXED_RF,
    build_labels,
    check_current_reproduced,
    load_research_data,
    purged_split,
    research_boundary,
)
from research_m5_label_horizon import evaluate as evaluate_baseline_only
from research_rf_m5_model_comparison import trade_metrics
from train_rf_m5 import FORBIDDEN_INPUTS, RF_FEATURES, RF_PARAMS, VALIDATION_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
MODELS_DIR = SRC_DIR / "models"
TEST_PATH = DATA_DIR / "xauusd_m5_test.csv"
RESULTS_PATH = DATA_DIR / "m5_feature_family_research.csv"
REPORT_PATH = DATA_DIR / "m5_feature_family_research_report.txt"

BAR = pd.Timedelta(minutes=BAR_MINUTES)
TP_MULT, SL_MULT, HORIZON = 1.5, 1.0, 12

CLASS_ORDER = [BUY, SELL, WAIT]
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
CHANCE = 1 / len(CLASS_ORDER)

# Same windows as research_m5_label_horizon (fractions 0.55/0.70/0.85 of the
# pre-test feature rows); recomputed and asserted equal.
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]

HTF_MINUTES = {"m15": 15, "m30": 30, "h1": 60}
REGIME_HISTORY_BARS = 1440   # about one trading week of M5 bars

CONFIGS = {
    "BASELINE": [],
    "A": ["A"],
    "B": ["B"],
    "C": ["C"],
    "D": ["D"],
    "E": ["A", "B"],
    "F": ["A", "C"],
    "G": ["B", "C"],
}
FAMILY_NAMES = {
    "A": "FAMILY_A_HIGHER_TF_TREND",
    "B": "FAMILY_B_MARKET_REGIME",
    "C": "FAMILY_C_PRICE_STRUCTURE",
    "D": "FAMILY_D_SESSION_CONTEXT",
}

# Decision and warning rules, fixed before any result is seen.
MEANINGFUL_DELTA = 0.01          # balanced-accuracy change treated as more than noise
GAP_ABSOLUTE_WARNING = 0.10      # train - validation balanced accuracy
GAP_INCREASE_WARNING = 0.03      # gap above the baseline gap
NEAR_DUPLICATE_CORR = 0.95       # |corr| with a baseline feature on training rows
BOOT_SAMPLES, BOOT_BLOCK, BOOT_SEED = 1000, 288, 42   # paired block bootstrap (288 bars ~ 1 day)
LEAKAGE_CHECK_POINTS = 12

TEST_STATEMENT = "The untouched TEST dataset was not loaded or used."


# --------------------------------------------------------------------------
# Safety: file hashes and CSV read tracking
# --------------------------------------------------------------------------

def snapshot_existing_files() -> dict:
    skip = {RESULTS_PATH, REPORT_PATH, Path(__file__).resolve()}
    hashes = {}
    for folder in (SRC_DIR, DATA_DIR, MODELS_DIR):
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.resolve() not in skip:
                hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


CSV_READS: list[Path] = []
_original_read_csv = pd.read_csv


def _tracked_read_csv(path, *args, **kwargs):
    resolved = Path(path).resolve()
    if resolved == TEST_PATH.resolve():
        raise RuntimeError("Attempted to read the TEST dataset.")
    CSV_READS.append(resolved)
    return _original_read_csv(path, *args, **kwargs)


# --------------------------------------------------------------------------
# Feature families (causal: every value on M5 row t uses bars <= t only)
# --------------------------------------------------------------------------

FEATURE_DESCRIPTIONS: dict[str, str] = {}


def describe(family: str, name: str, text: str) -> str:
    FEATURE_DESCRIPTIONS[name] = f"{family}: {text}"
    return name


def m5_frame(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[["time", "open", "high", "low", "close"]].copy().reset_index(drop=True)
    add_atr(df)
    return df


def build_htf(raw: pd.DataFrame, tag: str, minutes: int) -> pd.DataFrame:
    rule = f"{minutes}min"
    bars = raw.set_index("time")[["open", "high", "low", "close"]]
    htf = bars.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    htf["m5_bars"] = bars["close"].resample(rule, label="left", closed="left").count()
    htf = htf[htf["m5_bars"] > 0].rename_axis("htf_start").reset_index()

    add_atr(htf)
    add_rsi(htf)
    close = htf["close"]
    ema = {s: close.ewm(span=s, min_periods=s, adjust=False).mean() for s in (9, 20, 50)}
    trend = np.select([(ema[9] > ema[20]) & (ema[20] > ema[50]), (ema[9] < ema[20]) & (ema[20] < ema[50])],
                      [1.0, -1.0], 0.0)
    cols = {
        describe("A", f"{tag}_close_to_ema_9", f"{tag.upper()} close / EMA9 - 1"): close / ema[9] - 1,
        describe("A", f"{tag}_close_to_ema_20", f"{tag.upper()} close / EMA20 - 1"): close / ema[20] - 1,
        describe("A", f"{tag}_ema_9_20_atr", f"{tag.upper()} (EMA9 - EMA20) / {tag.upper()} ATR14"):
            (ema[9] - ema[20]) / htf["atr_14"],
        describe("A", f"{tag}_ema_20_50_atr", f"{tag.upper()} (EMA20 - EMA50) / {tag.upper()} ATR14"):
            (ema[20] - ema[50]) / htf["atr_14"],
        describe("A", f"{tag}_rsi_14", f"{tag.upper()} RSI14"): htf["rsi_14"],
        describe("A", f"{tag}_atr_pct", f"{tag.upper()} ATR14 / close"): htf["atr_14_pct"],
        describe("A", f"{tag}_return_4", f"{tag.upper()} 4-candle return"): close.pct_change(4, fill_method=None),
        describe("A", f"{tag}_trend_dir", f"{tag.upper()} +1 if EMA9>EMA20>EMA50, -1 if reversed, else 0"):
            pd.Series(trend, index=htf.index).where(ema[50].notna()),
    }
    htf = pd.concat([htf, pd.DataFrame(cols)], axis=1)
    # A candle is complete once its last M5 slot (start + period - 5 min) has closed.
    htf["available_at"] = htf["htf_start"] + pd.Timedelta(minutes=minutes) - BAR
    htf["htf_idx"] = np.arange(len(htf))
    return htf


def map_htf(times: pd.Series, htf: pd.DataFrame, leaky: bool = False) -> pd.DataFrame:
    """Most recent HTF candle usable at each M5 row (leaky=True maps the still-forming candle; control only)."""
    key = "htf_start" if leaky else "available_at"
    left = pd.DataFrame({"time": times.to_numpy()})
    return pd.merge_asof(left, htf, left_on="time", right_on=key, direction="backward")


def family_a(raw: pd.DataFrame, leaky: bool = False):
    times = raw["time"].reset_index(drop=True)
    parts, mappings = [], {}
    for tag, minutes in HTF_MINUTES.items():
        htf = build_htf(raw, tag, minutes)
        mapped = map_htf(times, htf, leaky)
        cols = [c for c in htf.columns if c.startswith(f"{tag}_")]
        parts.append(mapped[cols])
        mappings[tag] = (mapped, htf)
    return pd.concat(parts, axis=1), mappings


def family_b(df: pd.DataFrame) -> pd.DataFrame:
    high, low, close, atr = df["high"], df["low"], df["close"], df[ATR_COLUMN]
    ret = np.log(close).diff()
    hl2 = np.log(high / low) ** 2
    range_12 = high.rolling(12).max() - low.rolling(12).min()
    n = REGIME_HISTORY_BARS
    return pd.DataFrame({
        describe("B", "regime_parkinson_vol_ratio_12_48",
                 "high-low (Parkinson) volatility 12 / 48 bars; range-based, unlike the baseline close-to-close ratio"):
            np.sqrt(hl2.rolling(12).mean()) / np.sqrt(hl2.rolling(48).mean()),
        describe("B", f"regime_atr_pctile_{n}", f"percentile of ATR14 within the last {n} bars"):
            atr.rolling(n).rank(pct=True),
        describe("B", f"regime_range12_pctile_{n}", f"percentile of the 12-bar high-low range within the last {n} bars"):
            range_12.rolling(n).rank(pct=True),
        describe("B", "regime_efficiency_24", "trend strength: |24-bar net move| / sum of absolute 1-bar moves"):
            (close - close.shift(24)).abs() / close.diff().abs().rolling(24).sum(),
        describe("B", "regime_dir_persistence_24", "mean sign of the last 24 one-bar returns"):
            np.sign(ret).rolling(24).mean(),
        describe("B", "regime_autocorr_48", "48-bar rolling correlation of 1-bar return with the previous return"):
            ret.rolling(48).corr(ret.shift(1)),
        describe("B", "regime_atr_expansion_288", "ATR14 / its 288-bar mean (>1 expansion, <1 contraction)"):
            atr / atr.rolling(288).mean(),
    })


def family_c(df: pd.DataFrame) -> pd.DataFrame:
    high, low, close, atr = df["high"], df["low"], df["close"], df[ATR_COLUMN]
    out = {}
    for n in (12, 24, 48):
        out[describe("C", f"struct_dist_high_{n}", f"(highest high of last {n} bars - close) / ATR14")] = \
            (high.rolling(n).max() - close) / atr
        out[describe("C", f"struct_dist_low_{n}", f"(close - lowest low of last {n} bars) / ATR14")] = \
            (close - low.rolling(n).min()) / atr

    high_24, low_24 = high.rolling(24).max(), low.rolling(24).min()
    out[describe("C", "struct_range_pos_24", "position of close inside the 24-bar range (0 = low, 1 = high)")] = \
        (close - low_24) / (high_24 - low_24)

    prior_high, prior_low = high.shift(1).rolling(24).max(), low.shift(1).rolling(24).min()
    breakout = np.where(close > prior_high, (close - prior_high) / atr,
                        np.where(close < prior_low, (close - prior_low) / atr, 0.0))
    out[describe("C", "struct_breakout_24", "close beyond the previous 24-bar high (+) or low (-), in ATR; 0 inside")] = \
        pd.Series(breakout, index=df.index).where(prior_high.notna())

    w, n_rows = 24, len(df)
    since_high = np.full(n_rows, np.nan)
    since_low = np.full(n_rows, np.nan)
    if n_rows >= w:
        since_high[w - 1:] = np.argmax(sliding_window_view(high.to_numpy(), w)[:, ::-1], axis=1)
        since_low[w - 1:] = np.argmin(sliding_window_view(low.to_numpy(), w)[:, ::-1], axis=1)
    extreme = np.where(since_high <= since_low, high_24, low_24)
    out[describe("C", "struct_pullback_24",
                 "(close - most recent 24-bar extreme) / ATR14; negative after a high, positive after a low")] = \
        pd.Series((close.to_numpy() - extreme) / atr.to_numpy(), index=df.index).where(~np.isnan(since_high))

    step = np.sign(close.diff()).fillna(0.0)
    out[describe("C", "struct_streak", "signed count of consecutive up (+) / down (-) closes")] = \
        step.groupby((step != step.shift()).cumsum()).cumsum()
    out[describe("C", "struct_return_6_atr", "6-bar close change / ATR14")] = (close - close.shift(6)) / atr
    out[describe("C", "struct_range6_atr", "6-bar high-low range / ATR14 (recent range expansion)")] = \
        (high.rolling(6).max() - low.rolling(6).min()) / atr
    return pd.DataFrame(out)


def family_d(times: pd.Series) -> pd.DataFrame:
    utc = times.dt.tz_localize("UTC")
    weekday = times.dt.day_of_week
    local = {}
    for name in ("london", "new_york"):
        tz, start, end = SESSIONS[name]
        t = utc.dt.tz_convert(tz)
        minute = t.dt.hour * 60 + t.dt.minute
        local[name] = {
            "since_open": (minute - start * 60) % 1440,
            "until_close": (end * 60 - minute) % 1440,
            "in_session": (minute >= start * 60) & (minute < end * 60),
        }
    lo, ny = local["london"], local["new_york"]
    overlap = lo["in_session"] & ny["in_session"]
    return pd.DataFrame({
        describe("D", "sess_min_since_london_open", "minutes since the latest London 08:00 local open (DST-aware)"):
            lo["since_open"],
        describe("D", "sess_min_since_ny_open", "minutes since the latest New York 08:00 local open"): ny["since_open"],
        describe("D", "sess_min_until_london_close", "minutes until the next London 17:00 local close"):
            lo["until_close"],
        describe("D", "sess_min_until_ny_close", "minutes until the next New York 17:00 local close"):
            ny["until_close"],
        describe("D", "sess_overlap_age", "minutes since the London/NY overlap began; -1 outside the overlap"):
            np.where(overlap, np.minimum(lo["since_open"], ny["since_open"]), -1),
        describe("D", "sess_london_open_hour", "flag: first hour of London"): (lo["since_open"] < 60).astype(int),
        describe("D", "sess_ny_open_hour", "flag: first hour of New York"): (ny["since_open"] < 60).astype(int),
        describe("D", "sess_london_close_hour", "flag: last hour of London"):
            (lo["in_session"] & (lo["until_close"] <= 60)).astype(int),
        describe("D", "sess_ny_close_hour", "flag: last hour of New York"):
            (ny["in_session"] & (ny["until_close"] <= 60)).astype(int),
        describe("D", "sess_monday_london", "flag: Monday (UTC) during London hours"):
            ((weekday == 0) & lo["in_session"]).astype(int),
        describe("D", "sess_friday_ny", "flag: Friday (UTC) during New York hours"):
            ((weekday == 4) & ny["in_session"]).astype(int),
    })


def build_new_features(raw: pd.DataFrame):
    raw = raw.reset_index(drop=True)
    df = m5_frame(raw)
    a, mappings = family_a(raw)
    parts = {"A": a, "B": family_b(df), "C": family_c(df), "D": family_d(df["time"])}
    out = pd.concat([df[["time", ATR_COLUMN]]] + list(parts.values()), axis=1)
    out = out.replace([np.inf, -np.inf], np.nan)
    families = {k: list(v.columns) for k, v in parts.items()}
    return out, families, mappings


def config_features(name: str, families: dict) -> list[str]:
    cols = RF_FEATURES + [c for fam in CONFIGS[name] for c in families[fam]]
    assert len(cols) == len(set(cols)), f"{name} has duplicate feature names"
    assert not FORBIDDEN_INPUTS & set(cols), f"{name} includes time/price/target columns"
    return cols


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------

def check_prefix_invariance(raw: pd.DataFrame, full: pd.DataFrame, cols: list[str], check_times) -> dict:
    """Recompute every feature from bars <= t only; all rows <= t must equal the full-history values."""
    compared = 0
    for t in check_times:
        prefix_raw = raw[raw["time"] <= t]
        prefix, _, _ = build_new_features(prefix_raw)
        assert prefix["time"].iloc[-1] == t
        a = prefix[cols].to_numpy(float)
        b = full.iloc[:len(prefix)][cols].to_numpy(float)
        bad = ~np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True)
        if bad.any():
            worst = [cols[j] for j in np.unique(np.nonzero(bad)[1])][:5]
            raise AssertionError(f"future information detected at {t}: {worst}")
        compared += a.size
    return {"check_points": len(check_times), "values_compared": compared}


def leaky_control(raw: pd.DataFrame, check_times) -> int:
    """Map the still-forming H1 candle on purpose; the prefix test must detect it."""
    col = "h1_close_to_ema_9"
    full = map_htf(raw["time"], build_htf(raw, "h1", 60), leaky=True)[col].to_numpy()
    detected = 0
    for t in check_times:
        prefix_raw = raw[raw["time"] <= t]
        prefix = map_htf(prefix_raw["time"], build_htf(prefix_raw, "h1", 60), leaky=True)[col].to_numpy()
        if not np.isclose(prefix[-1], full[len(prefix) - 1], rtol=1e-9, atol=1e-12, equal_nan=True):
            detected += 1
    return detected


def check_htf_completed(mappings: dict, raw_times: pd.Series, row_mask: np.ndarray) -> dict:
    out = {}
    times = raw_times.reset_index(drop=True)
    for tag, (mapped, htf) in mappings.items():
        period = pd.Timedelta(minutes=HTF_MINUTES[tag])
        valid = mapped["htf_idx"].notna().to_numpy() & row_mask
        start = mapped["htf_start"][valid]
        t = times[valid]
        closed_by_t = (start + period <= t + BAR).all()
        nxt = htf["available_at"].reindex(mapped["htf_idx"][valid].astype(int) + 1).to_numpy()
        most_recent = bool(((nxt > t.to_numpy()) | pd.isna(nxt)).all())
        forming = (t.dt.floor(f"{HTF_MINUTES[tag]}min") + period > t + BAR)
        partial = (mapped["m5_bars"][valid] < HTF_MINUTES[tag] // BAR_MINUTES)
        if not (closed_by_t and most_recent):
            raise AssertionError(f"{tag}: an incomplete or stale higher-timeframe candle was used")
        out[tag] = {"rows": int(valid.sum()), "rows_with_forming_candle_excluded": int(forming.sum()),
                    "rows_using_candle_with_missing_m5_bars": int(partial.sum())}
    return out


def near_duplicates(train: pd.DataFrame, families: dict) -> dict:
    base = train[RF_FEATURES]
    out = {}
    for fam, cols in families.items():
        corr = pd.concat([train[cols], base], axis=1).corr().loc[cols, RF_FEATURES].abs()
        best = corr.max(axis=1)
        out[fam] = {c: (corr.loc[c].idxmax(), float(best[c])) for c in cols if best[c] > NEAR_DUPLICATE_CORR}
    return out


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def evaluate(train: pd.DataFrame, val: pd.DataFrame, cols: list[str]):
    model = RandomForestClassifier(**FIXED_RF).fit(train[cols], train[TARGET_COLUMN])
    y_tr, y_val = train[TARGET_COLUMN].to_numpy(), val[TARGET_COLUMN].to_numpy()
    p_tr, p_val = model.predict(train[cols]), model.predict(val[cols])
    precision, recall, _, support = precision_recall_fscore_support(y_val, p_val, labels=CLASS_ORDER, zero_division=0)
    cm = confusion_matrix(y_val, p_val, labels=CLASS_ORDER)
    train_bal, val_bal = balanced_accuracy_score(y_tr, p_tr), balanced_accuracy_score(y_val, p_val)
    out = {
        "feature_count": len(cols), "train_rows": len(train), "val_rows": len(val),
        "train_start": train["time"].iloc[0], "train_end": train["time"].iloc[-1],
        "val_start": val["time"].iloc[0], "val_end": val["time"].iloc[-1],
        "train_balanced_accuracy": train_bal, "val_balanced_accuracy": val_bal,
        "train_val_gap": train_bal - val_bal,
        "confusion_matrix": ";".join(",".join(str(v) for v in row) for row in cm),
    }
    for i, (cls, name) in enumerate(zip(CLASS_ORDER, CLASS_LABELS)):
        key = name.lower()
        out.update({f"{key}_precision": precision[i], f"{key}_recall": recall[i], f"{key}_support": int(support[i]),
                    f"{key}_val_share": float((y_val == cls).mean())})
    return out, cm, model, y_val, p_val


def balanced_accuracy_rows(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    recalls = [((y == c) & (p == c)).sum(axis=1) / (y == c).sum(axis=1) for c in CLASS_ORDER]
    return np.mean(recalls, axis=0)


def paired_block_bootstrap(y, p_cfg, p_base) -> tuple[float, float]:
    """95% interval of (config - baseline) balanced accuracy, resampling contiguous ~1-day blocks."""
    rng = np.random.default_rng(BOOT_SEED)
    n = len(y)
    n_blocks = -(-n // BOOT_BLOCK)
    starts = rng.integers(0, n - BOOT_BLOCK + 1, size=(BOOT_SAMPLES, n_blocks))
    idx = (starts[:, :, None] + np.arange(BOOT_BLOCK)).reshape(BOOT_SAMPLES, -1)[:, :n]
    yy = y.astype(np.int8)[idx]
    delta = balanced_accuracy_rows(yy, p_cfg.astype(np.int8)[idx]) - balanced_accuracy_rows(yy, p_base.astype(np.int8)[idx])
    lo, hi = np.percentile(delta, [2.5, 97.5])
    return float(lo), float(hi)


def summarize(ev: pd.DataFrame, boot: dict, dupes: dict) -> pd.DataFrame:
    bal = ev.pivot(index="config", columns="evaluation", values="val_balanced_accuracy").reindex(list(CONFIGS))
    gap = ev.pivot(index="config", columns="evaluation", values="train_val_gap").reindex(list(CONFIGS))
    wf = [c for c in bal.columns if c.startswith("WF")]
    base = bal.loc["BASELINE"]
    base_std = bal.loc["BASELINE", wf].std(ddof=1)
    rows = []
    for name in CONFIGS:
        delta = bal.loc[name] - base
        better = int((delta[wf] > MEANINGFUL_DELTA).sum())
        worse = int((delta[wf] < -MEANINGFUL_DELTA).sum())
        wf_std = bal.loc[name, wf].std(ddof=1)
        row = {
            "section": "summary", "config": name,
            "families": "+".join(CONFIGS[name]) or "-",
            "feature_count": int(ev[(ev.config == name)]["feature_count"].iloc[0]),
            "main_val_balanced_accuracy": bal.loc[name, "main"],
            **{f"{w}_val_balanced_accuracy": bal.loc[name, w] for w in wf},
            "wf_mean_balanced_accuracy": bal.loc[name, wf].mean(),
            "wf_std_balanced_accuracy": wf_std,
            "main_gap": gap.loc[name, "main"], "wf_mean_gap": gap.loc[name, wf].mean(),
            "delta_main": delta["main"], **{f"delta_{w}": delta[w] for w in wf},
            "delta_wf_mean": delta[wf].mean(),
            "wf_windows_better": better, "wf_windows_worse": worse,
        }
        for ev_name in ["main"] + wf:
            lo, hi = boot.get((name, ev_name), (np.nan, np.nan))
            row[f"delta_{ev_name}_ci_low"], row[f"delta_{ev_name}_ci_high"] = lo, hi

        warnings = []
        if name != "BASELINE":
            if better == len(wf):
                verdict = "CONSISTENT IMPROVEMENT"
            elif better >= 2 and worse == 0:
                verdict = "PARTIAL IMPROVEMENT"
            elif worse >= 2:
                verdict = "WORSE"
            else:
                verdict = "NO CONSISTENT IMPROVEMENT"
            if row["main_gap"] > gap.loc["BASELINE", "main"] + GAP_INCREASE_WARNING:
                warnings.append(f"main gap exceeds baseline gap by > {GAP_INCREASE_WARNING}")
            if row["wf_mean_gap"] > gap.loc["BASELINE", wf].mean() + GAP_INCREASE_WARNING:
                warnings.append(f"walk-forward gap exceeds baseline by > {GAP_INCREASE_WARNING}")
            if delta["main"] > MEANINGFUL_DELTA and delta[wf].mean() <= MEANINGFUL_DELTA:
                warnings.append("main-split gain not confirmed by walk-forward mean")
            if wf_std > max(2 * base_std, MEANINGFUL_DELTA):
                warnings.append(f"walk-forward std {wf_std:.4f} > 2x baseline std {base_std:.4f}")
            n_dupe = sum(len(dupes[f]) for f in CONFIGS[name])
            if n_dupe:
                warnings.append(f"{n_dupe} near-duplicate feature(s) of baseline (|r| > {NEAR_DUPLICATE_CORR})")
        else:
            verdict = "-"
        if row["main_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"main gap {row['main_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        if row["wf_mean_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"walk-forward mean gap {row['wf_mean_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        row["verdict"] = verdict
        row["warnings"] = "; ".join(warnings) if warnings else "none"
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Secondary diagnostic: unchanged backtest engine on the main validation period
# --------------------------------------------------------------------------

def backtest_configs(models: dict, cols_by_config: dict, new_features: pd.DataFrame, new_cols: list[str]) -> pd.DataFrame:
    val_bt, start, end = load_validation_period(VALIDATION_PATH)
    raw_bt, feats_bt, positions_bt, _ = load_market(start, end)
    check_against_validation(feats_bt, val_bt, RF_FEATURES)
    feats_bt = feats_bt.merge(new_features[["time"] + new_cols], on="time", how="left", validate="one_to_one")
    assert np.isfinite(feats_bt[new_cols].to_numpy(float)).all(), "new features missing in the validation period"

    rows = []
    for name, model in models.items():
        signals = generate_signals(model, feats_bt, cols_by_config[name])
        trades, _ = run_backtest(raw_bt, feats_bt, positions_bt, signals)
        m = trade_metrics(trades)
        for side in ("BUY", "SELL"):
            m.update(trade_metrics(trades[trades["side"] == side], prefix=f"{side.lower()}_"))
        rows.append({"section": "backtest", "config": name, "evaluation": "main_validation_backtest", **m})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


def eval_table(ev: pd.DataFrame, evaluation: str) -> str:
    sub = ev[ev["evaluation"] == evaluation].set_index("config").reindex(list(CONFIGS))
    cols = ["feature_count", "train_rows", "val_rows", "train_balanced_accuracy", "val_balanced_accuracy",
            "train_val_gap", "buy_precision", "buy_recall", "sell_precision", "sell_recall",
            "wait_precision", "wait_recall"]
    t = sub[cols].copy()
    for c in cols[3:]:
        t[c] = t[c].map(lambda v, c=c: f"{v:+.4f}" if c == "train_val_gap" else pct(v))
    t[cols[:3]] = t[cols[:3]].astype(int)
    return t.to_string()


def build_report(ev, summary, backtest, families, wf_windows, boundary, checks, confusions) -> list[str]:
    val_start, val_end, cutoff = boundary
    wf = [f"WF{i}" for i in range(1, len(wf_windows) + 1)]
    s = summary.set_index("config")
    L = ["XAUUSD M5 feature-family research (classification diagnostic only)", "=" * 78, TEST_STATEMENT,
         f"Label: current triple-barrier label (TP {TP_MULT} ATR, SL {SL_MULT} ATR, {HORIZON} bars), unchanged.",
         f"Research data: bars up to {cutoff}; feature rows up to {val_end} (test starts after the purge gap).",
         "Fixed RF for every configuration: " + ", ".join(f"{k}={v}" for k, v in RF_PARAMS.items()),
         f"Rows: {checks['research_rows']} labeled research rows used by every configuration; "
         f"{checks['warmup_rows_dropped']} early rows dropped for new-feature warm-up "
         f"(main-split baseline training rows {checks['baseline_train_rows_full']} -> "
         f"{checks['baseline_train_rows_common']}); {checks['interior_nan_rows']} later rows with undefined new features.",
         "Primary metric: out-of-sample balanced accuracy across the walk-forward windows. "
         "Backtest P&L is secondary and not used for selection.", ""]

    L += ["1. FEATURE-FAMILY DEFINITIONS (all causal; ATR = M5 ATR14 unless stated)"]
    for fam, cols in families.items():
        L.append(f"   {FAMILY_NAMES[fam]} ({len(cols)} features)")
        for c in cols:
            L.append(f"     {c:<36} {FEATURE_DESCRIPTIONS[c].split(': ', 1)[1]}")
    L.append("   FAMILY_A uses only the most recently COMPLETED M15/M30/H1 candle (usable from the M5 bar that "
             "completes it).")
    L.append("")

    L += ["2. FEATURE COUNTS"]
    for name in CONFIGS:
        fams = " + ".join(FAMILY_NAMES[f] for f in CONFIGS[name]) or "existing 30 RF_FEATURES"
        L.append(f"   {name:<9} {int(s.loc[name, 'feature_count']):3d}  "
                 f"{'BASELINE + ' if CONFIGS[name] else ''}{fams}")
    L.append("")

    L += [f"3. MAIN SPLIT (existing boundary; validation {val_start} -> {val_end})", eval_table(ev, "main"), "",
          "   Confusion matrices (rows = true BUY/SELL/WAIT, columns = predicted BUY/SELL/WAIT):"]
    for name, cm in confusions.items():
        L.append(f"   {name:<9} " + " | ".join(" ".join(f"{v:5d}" for v in row) for row in cm))
    L.append("")

    L += ["4. WALK-FORWARD RESULTS (expanding train, 12-bar purge before each validation block)"]
    for i, (start, stop) in enumerate(wf_windows, 1):
        L.append(f"   WF{i}: train = research rows before {start}; validation = {start} -> {stop}")
    for w in wf:
        L += [f"\n   {w}", eval_table(ev, w)]
    dist = ev[ev["evaluation"].isin(wf)].pivot(index="config", columns="evaluation",
                                               values=["buy_val_share", "sell_val_share", "wait_val_share"])
    L += ["", "   Validation class distribution by window (identical rows for every configuration):",
          dist.reindex(list(CONFIGS)).apply(lambda col: col.map(pct)).to_string(), ""]

    t = s[["feature_count", "main_val_balanced_accuracy"] + [f"{w}_val_balanced_accuracy" for w in wf]
          + ["wf_mean_balanced_accuracy", "wf_std_balanced_accuracy"]].copy()
    t.columns = ["features", "main", *wf, "wf_mean", "wf_std"]
    for c in t.columns[1:]:
        t[c] = t[c].map(lambda v: f"{v:.4f}")
    L += ["5. AVERAGE WALK-FORWARD BALANCED ACCURACY  and  6. STANDARD DEVIATION ACROSS WINDOWS (sample std, n=3)",
          t.to_string(), f"   Chance level: {CHANCE:.4f}.", ""]

    L += ["7. BASELINE COMPARISON (config - baseline balanced accuracy; 95% paired block-bootstrap interval)",
          "   Note: the main validation period overlaps WF3, so main and WF3 are not independent evidence."]
    for name in CONFIGS:
        if name == "BASELINE":
            continue
        r = s.loc[name]
        parts = [f"{e} {r[f'delta_{e}']:+.4f} [{r[f'delta_{e}_ci_low']:+.4f}, {r[f'delta_{e}_ci_high']:+.4f}]"
                 for e in ["main"] + wf]
        L.append(f"   {name}: " + "; ".join(parts))
        L.append(f"      walk-forward mean delta {r['delta_wf_mean']:+.4f}; better by > {MEANINGFUL_DELTA} in "
                 f"{int(r['wf_windows_better'])}/3 windows, worse in {int(r['wf_windows_worse'])}/3")
    L.append("")

    L += ["8. GENERALIZATION / OVERFITTING WARNINGS (rules fixed before running)",
          f"   rules: gap > {GAP_ABSOLUTE_WARNING}; gap > baseline gap + {GAP_INCREASE_WARNING}; main gain not "
          f"confirmed by walk-forward; walk-forward std > 2x baseline; near-duplicates (|r| > {NEAR_DUPLICATE_CORR})"]
    for name in CONFIGS:
        r = s.loc[name]
        L.append(f"   {name:<9} gap main {r['main_gap']:+.4f}, walk-forward mean {r['wf_mean_gap']:+.4f}: {r['warnings']}")
    for fam, d in checks["near_duplicates"].items():
        if d:
            L.append(f"   {FAMILY_NAMES[fam]} near-duplicates: " +
                     ", ".join(f"{c} ~ {b} ({v:.3f})" for c, (b, v) in d.items()))
    L.append("")

    p = checks["prefix"]
    L += ["9. LEAKAGE CHECKS",
          f"   [PASS] No future timestamps: every new feature was recomputed from bars <= t only at "
          f"{p['check_points']} check points; all {p['values_compared']:,} values for rows <= t matched the "
          "full-history computation exactly.",
          f"   [PASS] Check has power: a deliberately leaky control (mapping the still-forming H1 candle) was "
          f"detected at {checks['leaky_detected']}/{p['check_points']} check points."]
    for tag, h in checks["htf"].items():
        L.append(f"   [PASS] {tag.upper()}: every row uses a candle closed by the M5 signal bar's close and it is the "
                 f"most recent such candle ({h['rows']} rows; a still-forming candle was skipped on "
                 f"{h['rows_with_forming_candle_excluded']}; {h['rows_using_candle_with_missing_m5_bars']} rows use a "
                 "closed candle with missing M5 bars due to market gaps).")
    L += [f"   [PASS] M5 ATR14 recomputed from raw bars equals atr_14 in the existing features file.",
          f"   [PASS] Feature rows end at {val_end}; raw bars end at {cutoff}; labels for row t use bars t+1..t+12 "
          "and training rows are purged before every validation block.",
          f"   [PASS] Test data was not loaded: CSV files read = {', '.join(sorted({p.name for p in CSV_READS}))}; "
          f"{TEST_PATH.name} was never opened (reads of it raise an error).",
          f"   [PASS] Existing files were not modified: SHA-256 of {checks['files_hashed']} files in src/, src/data/ "
          "and src/models/ identical before and after the run (new output files excluded).",
          "   [PASS] Existing pipeline reproduced: rebuilt labels, train/validation rows and the retrained 30-feature "
          "model match the existing CSVs and the saved model exactly.",
          f"   [PASS] Walk-forward windows identical to the label-horizon experiment.", ""]

    L += ["10. DOES ANY FEATURE FAMILY IMPROVE CONSISTENTLY ACROSS MULTIPLE WINDOWS?",
          f"   Rule: CONSISTENT = better by > {MEANINGFUL_DELTA} in all 3 walk-forward windows; PARTIAL = better in "
          f"2/3 with none worse by > {MEANINGFUL_DELTA}; WORSE = worse in >= 2/3."]
    for name in CONFIGS:
        if name != "BASELINE":
            L.append(f"   {name:<9} {s.loc[name, 'verdict']}")
    consistent = [n for n in CONFIGS if s.loc[n, "verdict"] == "CONSISTENT IMPROVEMENT"]
    partial = [n for n in CONFIGS if s.loc[n, "verdict"] == "PARTIAL IMPROVEMENT"]
    L.append("   Answer: " + (f"yes - {', '.join(consistent)}." if consistent else
                              f"partially - {', '.join(partial)} (not all windows)." if partial else
                              "no feature family improved consistently across the walk-forward windows."))
    L.append("   Seven configurations were compared on the same windows; the best-looking delta is optimistically "
             "biased and is not a final estimate.")
    L.append("")

    L += ["11. RECOMMENDED NEXT RESEARCH STEP"]
    if consistent or partial:
        names = ", ".join(consistent or partial)
        L += [f"   Treat {names} as a hypothesis, not a result. Confirm it on more walk-forward folds (e.g. 6 smaller",
              "   expanding windows defined in advance) and check that the feature importances of the added family are",
              "   stable across folds. Only then run the existing cost-aware backtest across all folds. Keep the test",
              "   set untouched."]
    else:
        L += ["   More OHLC-derived context (higher-timeframe trend, regime, structure, session clock) does not add",
              "   usable out-of-sample information for this label. Price/tick-volume features from the same M5 series",
              "   appear saturated. Next: test genuinely new information sources (e.g. cross-asset data such as DXY or",
              "   US yields, economic-calendar event flags) or reformulate the target (e.g. cost-aware directional",
              "   classification only on bars with predefined volatility conditions), using this same fixed",
              "   walk-forward protocol. Keep the test set untouched."]
    L.append("")

    bt = backtest.set_index("config").reindex(list(CONFIGS))
    L += ["APPENDIX - SECONDARY BACKTEST DIAGNOSTIC (main validation period only; NOT used for selection)",
          "   Unchanged backtest_rf_m5 engine and assumptions; models from the main split above. $ per ounce;",
          "   drawdown = closed-trade equity only. The baseline here is trained on the warm-up-trimmed rows, so it",
          "   differs slightly from the existing baseline backtest."]
    t = pd.DataFrame({
        "trades": bt["trades"].astype(int), "net_pnl": bt["net_pnl"].map("{:.2f}".format),
        "avg_r": bt["avg_r"].map("{:+.4f}".format), "profit_factor": bt["profit_factor"].map("{:.3f}".format),
        "max_dd": bt["max_closed_trade_dd"].map("{:.2f}".format),
        "buy_trades": bt["buy_trades"].astype(int), "buy_net": bt["buy_net_pnl"].map("{:.2f}".format),
        "buy_avg_r": bt["buy_avg_r"].map("{:+.4f}".format),
        "sell_trades": bt["sell_trades"].astype(int), "sell_net": bt["sell_net_pnl"].map("{:.2f}".format),
        "sell_avg_r": bt["sell_avg_r"].map("{:+.4f}".format),
    })
    L += [t.to_string(), "   One validation period; P&L differences between configurations are not evidence of edge."]
    L += [f"   - {w}" for w in BACKTEST_WARNINGS]
    L += ["", "No production strategy is recommended. All results are research diagnostics.", TEST_STATEMENT]
    return L


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    hashes_before = snapshot_existing_files()
    pd.read_csv = _tracked_read_csv
    assert RF_PARAMS == FIXED_RF, "train_rf_m5.RF_PARAMS differs from the fixed research configuration"

    boundary = research_boundary()
    val_start, val_end, cutoff = boundary
    raw, features, positions = load_research_data(val_end, cutoff)
    assert features["time"].max() <= val_end and raw["time"].max() <= cutoff

    new_raw, families, mappings = build_new_features(raw)
    new_cols = [c for cols in families.values() for c in cols]
    assert not set(new_cols) & set(features.columns), "new feature names collide with existing features"

    merged = features.merge(new_raw, on="time", how="left", validate="one_to_one", suffixes=("", "_recomputed"))
    assert np.allclose(merged[ATR_COLUMN], merged[f"{ATR_COLUMN}_recomputed"]), "recomputed ATR differs"
    merged = merged.drop(columns=f"{ATR_COLUMN}_recomputed")

    labels = build_labels(raw, features, positions, TP_MULT, SL_MULT, HORIZON)
    keep = ~labels["excluded"].to_numpy()
    full_labeled = features[keep].assign(**{TARGET_COLUMN: labels.loc[keep, TARGET_COLUMN].to_numpy()})
    train_full, val_full = purged_split(full_labeled, HORIZON, val_start, val_end, inclusive_stop=True)
    _, _, model_full = evaluate_baseline_only(train_full, val_full)
    check_current_reproduced(labels, train_full, val_full, model_full)
    print("existing pipeline reproduced (labels, splits, saved model)")

    complete = np.isfinite(merged[new_cols].to_numpy(float)).all(axis=1)
    first_complete = int(np.argmax(complete))
    warmup_rows = first_complete
    interior_nan = int((~complete[first_complete:]).sum())
    research = merged[keep & complete].assign(**{TARGET_COLUMN: labels.loc[keep & complete, TARGET_COLUMN].to_numpy()})
    research = research.reset_index(drop=True)

    times = features["time"]
    starts = [times.iloc[int(len(times) * f)] for f in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"

    check_times = [research["time"].iloc[int(f * (len(research) - 1))]
                   for f in np.linspace(0.05, 1.0, LEAKAGE_CHECK_POINTS)]
    prefix = check_prefix_invariance(raw, new_raw, new_cols, check_times)
    leaky_detected = leaky_control(raw, check_times)
    assert leaky_detected > 0, "leakage check has no power: leaky control was not detected"
    research_mask = raw["time"].isin(research["time"]).to_numpy()
    htf_checks = check_htf_completed(mappings, raw["time"], research_mask)
    print(f"leakage checks passed ({prefix['values_compared']:,} values; leaky control detected "
          f"{leaky_detected}/{len(check_times)})")

    cols_by_config = {name: config_features(name, families) for name in CONFIGS}
    rows, confusions, preds, main_models = [], {}, {}, {}
    splits = {"main": purged_split(research, HORIZON, val_start, val_end, inclusive_stop=True)}
    for i, (start, stop) in enumerate(wf_windows, 1):
        splits[f"WF{i}"] = purged_split(research, HORIZON, start, stop, inclusive_stop=i == len(wf_windows))
    assert splits["main"][1]["time"].tolist() == val_full["time"].tolist(), "validation rows differ from existing split"

    for name in CONFIGS:
        for ev_name, (train, val) in splits.items():
            out, cm, model, y_val, p_val = evaluate(train, val, cols_by_config[name])
            rows.append({"section": "evaluation", "config": name, "evaluation": ev_name,
                         "families": "+".join(CONFIGS[name]) or "-", **out})
            preds[(name, ev_name)] = (y_val, p_val)
            if ev_name == "main":
                confusions[name] = cm
                main_models[name] = model
        main_bal = rows[-len(splits)]["val_balanced_accuracy"]
        wf_bal = [r["val_balanced_accuracy"] for r in rows[-len(splits) + 1:]]
        print(f"finished {name:<9} features {len(cols_by_config[name]):3d}  main {main_bal:.4f}  "
              f"walk-forward mean {np.mean(wf_bal):.4f}")
    ev = pd.DataFrame(rows)

    boot = {}
    for name in CONFIGS:
        if name == "BASELINE":
            continue
        for ev_name in splits:
            y, p_cfg = preds[(name, ev_name)]
            _, p_base = preds[("BASELINE", ev_name)]
            boot[(name, ev_name)] = paired_block_bootstrap(y, p_cfg, p_base)

    dupes = near_duplicates(splits["main"][0], families)
    summary = summarize(ev, boot, dupes)

    backtest = backtest_configs(main_models, cols_by_config, new_raw, new_cols)
    print("secondary backtest diagnostic finished")

    hashes_after = snapshot_existing_files()
    changed = [str(p) for p in hashes_before if hashes_before[p] != hashes_after.get(p)]
    if changed or set(hashes_before) != set(hashes_after):
        raise AssertionError(f"existing files changed: {changed}")
    assert TEST_PATH.resolve() not in CSV_READS

    checks = {
        "research_rows": len(research), "warmup_rows_dropped": warmup_rows, "interior_nan_rows": interior_nan,
        "baseline_train_rows_full": len(train_full), "baseline_train_rows_common": len(splits["main"][0]),
        "prefix": prefix, "leaky_detected": leaky_detected, "htf": htf_checks,
        "near_duplicates": dupes, "files_hashed": len(hashes_before),
    }
    definitions = pd.DataFrame([{"section": "feature_definition", "config": FAMILY_NAMES[fam], "feature": c,
                                 "description": FEATURE_DESCRIPTIONS[c].split(": ", 1)[1]}
                                for fam, cols in families.items() for c in cols])
    results = pd.concat([summary, ev, backtest, definitions], ignore_index=True)
    results.to_csv(RESULTS_PATH, index=False)

    lines = build_report(ev, summary, backtest, families, wf_windows, boundary, checks, confusions)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    final_hashes = snapshot_existing_files()
    assert final_hashes == hashes_before, "existing files changed while writing outputs"
    print()
    print("\n".join(lines))
    print(f"\nSaved results: {RESULTS_PATH}")
    print(f"Saved report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()
