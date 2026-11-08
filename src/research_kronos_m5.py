"""Isolated research: pretrained Kronos-mini forecasts as an XAUUSD M5 direction signal.

Research only. Nothing is fine-tuned, nothing existing is modified, and no
trading or production recommendation is made.

* Model: official pretrained Kronos-mini (NeoQuasar/Kronos-mini, 4.1M params)
  with its tokenizer NeoQuasar/Kronos-Tokenizer-2k, both pinned to a Hugging Face
  revision, run through the official KronosPredictor from the Kronos repository
  (github.com/shiyu-coder/Kronos, MIT licence). The repository is NOT copied into
  this project; set KRONOS_REPO to a local clone.
* Input: only raw M5 OHLCV bars (tick_volume as volume) and their UTC timestamps,
  exactly the columns the official API expects. No engineered features.
* Context: the last CONTEXT_BARS real bars up to and including the closed signal
  bar t. Market gaps are kept as they are (no filling, no synthetic candles).
  Kronos normalises each context with that context's own mean/std only.
* Forecast: the next FORECAST_BARS bars; their timestamps are the nominal next
  5-minute slots after t, so not even future timestamps are read from the data.
* Signal: pre-declared rules on the forecast close 12 bars ahead (see RULES);
  nothing is tuned on validation data.
* Evaluation: current label (TP 1.5 ATR / SL 1.0 ATR / 12 bars, cost-aware),
  existing train/validation boundary and the same three walk-forward windows as
  research_m5_label_horizon.py / research_m5_feature_families.py. The RF baseline
  is retrained per window with the unchanged 30 features and fixed parameters and
  scored on exactly the same rows. The unchanged backtest engine is used as a
  secondary diagnostic only.

Test safety: raw/feature CSVs are read only up to the last bar of the purge gap
after validation (row count found by scanning to that exact timestamp), every
loaded frame is checked against that boundary, and an audit hook makes any
attempt to open the test CSV raise immediately.
"""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

from backtest_rf_m5 import TRADES_PATH, generate_signals, load_market, load_model, load_validation_period, run_backtest
from features_m5 import BAR_MINUTES
from label_m5 import (
    ATR_COLUMN,
    BUY,
    EXTRA_COST_ROUND_TRIP,
    FEATURES_PATH,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    RAW_PATH,
    SELL,
    TARGET_COLUMN,
    TARGET_NAMES,
    WAIT,
)
from research_m5_feature_families import paired_block_bootstrap
from research_m5_label_horizon import (
    FIXED_RF,
    build_labels,
    check_current_reproduced,
    load_research_data,
    purged_split,
    research_boundary,
)
from research_m5_label_horizon import evaluate as evaluate_rf
from research_rf_m5_model_comparison import trade_metrics
from train_rf_m5 import MODEL_PATH, RF_FEATURES, RF_PARAMS, TRAIN_PATH, VALIDATION_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
MODELS_DIR = SRC_DIR / "models"
TEST_PATH = (DATA_DIR / "xauusd_m5_test.csv").resolve()
OUTPUT_NAMES = ("kronos_m5_predictions.csv", "kronos_m5_research.csv", "kronos_m5_research_report.txt")

KRONOS_REPO = Path(os.environ.get("KRONOS_REPO", Path(os.environ.get("TEMP", ".")) / "kronos_repo"))
MODEL_ID, MODEL_REVISION = "NeoQuasar/Kronos-mini", "f4e68697d9d5aed55cef5c96aabc3376bcad9f81"
TOKENIZER_ID, TOKENIZER_REVISION = "NeoQuasar/Kronos-Tokenizer-2k", "26966d0035065a0cae0ebad7af8ece35bc1fb51c"
CONTEXT_BARS = 2048        # official max context of Kronos-mini (README model zoo)
FORECAST_BARS = 12         # matches the label horizon
SAMPLING = {"T": 1.0, "top_k": 0, "top_p": 0.9, "sample_count": 1}   # README predict() example values
BATCH_SIZE = 16            # largest batch that stays well inside 4 GB VRAM at 2048 context
BASE_SEED = 42
KRONOS_INPUT = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "tick_volume"}

BAR = pd.Timedelta(minutes=BAR_MINUTES)
STEP = np.timedelta64(BAR_MINUTES, "m")
CLASS_ORDER = [BUY, SELL, WAIT]
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
CHANCE = 1 / 3

EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)

# Signal rules, declared before any validation result was computed. They use only
# the forecast and quantities known at the close of bar t.
RULES = {
    "PRIMARY": {
        "description": "BUY if forecast close(t+12) - close(t) > round-trip cost at t; SELL if < -cost; else WAIT. "
                       "cost = max(spread_t, 15 points) * 0.01 + 0.10 (same cost model as the labels, "
                       "using bar t's spread because bar t+1 is not known yet).",
        "threshold": "round_trip_cost",
    },
    "SECONDARY": {
        "description": "Sensitivity only, never used for the verdict: same rule with threshold 0.5 x ATR14(t).",
        "threshold": "atr", "atr_multiple": 0.5,
    },
}
FROZEN_RULES = copy.deepcopy(RULES)

# Verdict rules (fixed before running).
MEANINGFUL_DELTA = 0.01
FORECAST_STEPS_REPORTED = (1, 3, 6, 12)

TEST_STATEMENT = "The untouched TEST dataset was not loaded, opened or used."


# --------------------------------------------------------------------------
# Test-data guards
# --------------------------------------------------------------------------

GUARD = {"cutoff": None, "safe_nrows": {}, "csv_reads": [], "test_open_attempts": 0}
_TEST_NORM = os.path.normcase(str(TEST_PATH))


def _audit_hook(event, args):
    if event != "open" or not args or isinstance(args[0], int):
        return
    try:
        path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
    except (TypeError, ValueError):
        return
    if path == _TEST_NORM:
        GUARD["test_open_attempts"] += 1
        raise RuntimeError("TEST DATASET ACCESS BLOCKED: attempted to open xauusd_m5_test.csv")


_original_read_csv = pd.read_csv


def _guarded_read_csv(path, *args, **kwargs):
    resolved = Path(path).resolve()
    if resolved == TEST_PATH:
        raise RuntimeError("TEST DATASET ACCESS BLOCKED: attempted to read xauusd_m5_test.csv")
    if resolved in GUARD["safe_nrows"]:
        limit = GUARD["safe_nrows"][resolved]
        kwargs["nrows"] = min(kwargs.get("nrows") or limit, limit)
    elif resolved in (RAW_PATH.resolve(), FEATURES_PATH.resolve()):
        raise RuntimeError(f"{resolved.name} read before the safe row limit was established")
    GUARD["csv_reads"].append(resolved)
    df = _original_read_csv(path, *args, **kwargs)
    if GUARD["cutoff"] is not None and "time" in df.columns and len(df):
        latest = str(df["time"].astype(str).max())
        if latest > GUARD["cutoff"]:
            raise RuntimeError(f"TEST-PERIOD ROWS LOADED from {resolved.name}: latest {latest} > {GUARD['cutoff']}")
    return df


def rows_through(path: Path, cutoff: str) -> int:
    """Data rows up to and including the row stamped `cutoff`; nothing after it is read."""
    with open(path, "r", encoding="utf-8") as fh:
        if not fh.readline().startswith("time,"):
            raise RuntimeError(f"{path.name}: unexpected header")
        n = 0
        for line in fh:
            stamp = line[:19]
            if stamp > cutoff:
                raise RuntimeError(f"{path.name}: no row stamped {cutoff}; refusing to read further")
            n += 1
            if stamp == cutoff:
                return n
    raise RuntimeError(f"{path.name}: row stamped {cutoff} not found")


def install_guards() -> None:
    sys.addaudithook(_audit_hook)
    pd.read_csv = _guarded_read_csv


def assert_no_test_rows(df: pd.DataFrame, column: str = "time") -> None:
    if len(df) and str(df[column].max()) > GUARD["cutoff"]:
        raise RuntimeError(f"TEST-PERIOD ROWS PRESENT in memory: {df[column].max()}")


# --------------------------------------------------------------------------
# File integrity
# --------------------------------------------------------------------------

def snapshot_files(skip: set) -> tuple[dict, tuple]:
    """SHA-256 of every existing file in src/, src/data/, src/models/ except the test CSV (stat only)."""
    hashes = {}
    for folder in (SRC_DIR, DATA_DIR, MODELS_DIR):
        for path in sorted(folder.iterdir()):
            resolved = path.resolve()
            if not path.is_file() or resolved in skip or resolved == TEST_PATH:
                continue
            hashes[resolved] = hashlib.sha256(path.read_bytes()).hexdigest()
    st = os.stat(TEST_PATH)
    return hashes, (st.st_size, st.st_mtime_ns)


# --------------------------------------------------------------------------
# Kronos
# --------------------------------------------------------------------------

def load_kronos():
    import torch
    sys.path.insert(0, str(KRONOS_REPO))
    from model import Kronos, KronosPredictor, KronosTokenizer

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID, revision=TOKENIZER_REVISION)
    model = Kronos.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=CONTEXT_BARS)
    # KronosPredictor does not switch to eval mode; Kronos-mini has dropout 0.2.
    predictor.model.eval()
    predictor.tokenizer.eval()
    assert not predictor.model.training and not predictor.tokenizer.training
    try:
        commit = subprocess.run(["git", "-C", str(KRONOS_REPO), "rev-parse", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    info = {
        "device": device,
        "device_name": torch.cuda.get_device_name(0) if device.startswith("cuda") else "CPU",
        "torch": torch.__version__, "kronos_repo_commit": commit,
        "model_params": sum(p.numel() for p in model.parameters()),
        "tokenizer_params": sum(p.numel() for p in tokenizer.parameters()),
    }
    return predictor, torch, info


def market_arrays(raw: pd.DataFrame) -> dict:
    arrays = {k: raw[v].to_numpy(dtype=float) for k, v in KRONOS_INPUT.items()}
    arrays["time"] = raw["time"].to_numpy()
    return arrays


def forecast_batch(predictor, torch, arrays: dict, ends: np.ndarray, seed: int):
    """Forecast from contexts ending at raw positions `ends` (inclusive)."""
    dfs, x_times, y_times = [], [], []
    for p in ends:
        window = slice(p - CONTEXT_BARS + 1, p + 1)
        x_ts = pd.Series(arrays["time"][window])
        y_ts = pd.Series(arrays["time"][p] + STEP * np.arange(1, FORECAST_BARS + 1))
        assert len(x_ts) == CONTEXT_BARS and x_ts.iloc[-1] == arrays["time"][p], "context must end at bar t"
        assert y_ts.iloc[0] > x_ts.iloc[-1], "forecast target overlaps the context"
        dfs.append(pd.DataFrame({k: arrays[k][window] for k in KRONOS_INPUT}))
        x_times.append(x_ts)
        y_times.append(y_ts)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    out = predictor.predict_batch(dfs, x_times, y_times, pred_len=FORECAST_BARS, verbose=False, **SAMPLING)
    close = np.stack([o["close"].to_numpy() for o in out])
    high = np.stack([o["high"].to_numpy() for o in out])
    low = np.stack([o["low"].to_numpy() for o in out])
    return close, high, low


def fingerprint(times: pd.Series) -> str:
    return json.dumps({"model": MODEL_REVISION, "tokenizer": TOKENIZER_REVISION, "context": CONTEXT_BARS,
                       "horizon": FORECAST_BARS, "sampling": SAMPLING, "batch": BATCH_SIZE, "seed": BASE_SEED,
                       "first": str(times.iloc[0]), "last": str(times.iloc[-1]), "n": len(times)}, sort_keys=True)


def run_inference(predictor, torch, arrays, ends, times, checkpoint: Path):
    n = len(ends)
    n_batches = -(-n // BATCH_SIZE)
    fp = fingerprint(times)
    close = np.full((n, FORECAST_BARS), np.nan)
    high_max = np.full(n, np.nan)
    low_min = np.full(n, np.nan)
    done = set()
    if checkpoint.exists():
        cp = pd.read_csv(checkpoint)
        if len(cp) and (cp["fingerprint"] == fp).all():
            for b, grp in cp.groupby("batch"):
                rows = grp["row"].to_numpy()
                close[rows] = grp[[f"fc_close_{h}" for h in range(1, FORECAST_BARS + 1)]].to_numpy()
                high_max[rows], low_min[rows] = grp["fc_high_max"].to_numpy(), grp["fc_low_min"].to_numpy()
                done.add(int(b))
            print(f"resuming: {len(done)}/{n_batches} batches loaded from checkpoint")
        else:
            checkpoint.unlink()

    computed_seconds, pending = 0.0, []
    for b in range(n_batches):
        if b in done:
            continue
        rows = np.arange(b * BATCH_SIZE, min((b + 1) * BATCH_SIZE, n))
        t0 = time.perf_counter()
        c, h, l = forecast_batch(predictor, torch, arrays, ends[rows], BASE_SEED + b)
        computed_seconds += time.perf_counter() - t0
        close[rows], high_max[rows], low_min[rows] = c, h.max(axis=1), l.min(axis=1)
        pending.append(pd.DataFrame({"fingerprint": fp, "batch": b, "row": rows,
                                     **{f"fc_close_{k + 1}": c[:, k] for k in range(FORECAST_BARS)},
                                     "fc_high_max": h.max(axis=1), "fc_low_min": l.min(axis=1)}))
        if len(pending) >= 25 or b == n_batches - 1:
            pd.concat(pending).to_csv(checkpoint, mode="a", header=not checkpoint.exists(), index=False)
            pending = []
            finished = b + 1
            print(f"  batch {finished}/{n_batches}  ({computed_seconds / 60:.1f} min computed this session)",
                  flush=True)
    return close, high_max, low_min, computed_seconds, len(done)


# --------------------------------------------------------------------------
# Signals and metrics
# --------------------------------------------------------------------------

def round_trip_cost(spread_points: np.ndarray) -> np.ndarray:
    return np.maximum(spread_points, MIN_SPREAD_POINTS) * POINT_SIZE + EXTRA_COST_ROUND_TRIP


def to_signal(move: np.ndarray, threshold: np.ndarray) -> np.ndarray:
    return np.where(move > threshold, BUY, np.where(move < -threshold, SELL, WAIT)).astype(np.int64)


def make_signals(forecast_close_12, close_t, spread_t, atr_t) -> dict:
    move = forecast_close_12 - close_t
    return {
        "PRIMARY": to_signal(move, round_trip_cost(spread_t)),
        "SECONDARY": to_signal(move, RULES["SECONDARY"]["atr_multiple"] * atr_t),
    }


def classification(y: np.ndarray, p: np.ndarray) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(y, p, labels=CLASS_ORDER, zero_division=0)
    cm = confusion_matrix(y, p, labels=CLASS_ORDER)
    out = {"rows": len(y), "balanced_accuracy": balanced_accuracy_score(y, p), "accuracy": accuracy_score(y, p),
           "macro_f1": f1_score(y, p, labels=CLASS_ORDER, average="macro", zero_division=0),
           "confusion_matrix": ";".join(",".join(str(v) for v in row) for row in cm)}
    for i, (cls, name) in enumerate(zip(CLASS_ORDER, CLASS_LABELS)):
        k = name.lower()
        out.update({f"{k}_precision": precision[i], f"{k}_recall": recall[i], f"{k}_f1": f1[i],
                    f"{k}_support": int(support[i]), f"{k}_true_share": float((y == cls).mean()),
                    f"{k}_predicted": int((p == cls).sum()), f"{k}_predicted_share": float((p == cls).mean())})
    return out


def forecast_quality(pred: pd.DataFrame, arrays: dict, raw_pos: np.ndarray) -> dict:
    """Threshold-free forecast accuracy against realised closes (evaluation only, never an input)."""
    close_t = pred["close"].to_numpy()
    atr = pred[ATR_COLUMN].to_numpy()
    out = {"rows": len(pred)}
    for h in FORECAST_STEPS_REPORTED:
        actual = arrays["close"][raw_pos + h]
        fc = pred[f"fc_close_{h}"].to_numpy()
        mae = np.mean(np.abs(fc - actual) / atr)
        naive = np.mean(np.abs(close_t - actual) / atr)
        out[f"mae_atr_h{h}"], out[f"naive_mae_atr_h{h}"] = mae, naive
        out[f"skill_vs_naive_h{h}"] = 1 - mae / naive
    actual_move = arrays["close"][raw_pos + FORECAST_BARS] - close_t
    fc_move = pred[f"fc_close_{FORECAST_BARS}"].to_numpy() - close_t
    nonzero = (actual_move != 0) & (fc_move != 0)
    out["direction_hit_rate_h12"] = float((np.sign(actual_move[nonzero]) == np.sign(fc_move[nonzero])).mean())
    out["rank_corr_move_h12"] = float(pd.Series(fc_move).rank().corr(pd.Series(actual_move).rank()))
    out["mean_abs_forecast_move_atr"] = float(np.mean(np.abs(fc_move) / atr))
    out["mean_abs_actual_move_atr"] = float(np.mean(np.abs(actual_move) / atr))
    return out


def verdict(k_wf: list, rf_wf: list) -> str:
    deltas = np.array(k_wf) - np.array(rf_wf)
    above_chance = all(v > CHANCE + MEANINGFUL_DELTA for v in k_wf)
    if (deltas > MEANINGFUL_DELTA).all():
        vs_rf = "better than RF in all 3 windows"
    elif (deltas < -MEANINGFUL_DELTA).sum() >= 2:
        vs_rf = "worse than RF"
    else:
        vs_rf = "no consistent difference vs RF"
    return ("above chance in all 3 windows; " if above_chance else "not consistently above chance; ") + vs_rf


# --------------------------------------------------------------------------
# Leakage tests that need the model
# --------------------------------------------------------------------------

def future_perturbation_test(predictor, torch, arrays, ends) -> dict:
    """Forecasts must not change when every bar after t is altered; a leaky control must change.

    Each probe is forecast on its own so that other rows in a batch cannot affect its sampling.
    """
    identical, changed, deterministic = 0, 0, True
    for p in ends:
        one = np.array([p])
        base, _, _ = forecast_batch(predictor, torch, arrays, one, seed=BASE_SEED)
        repeat, _, _ = forecast_batch(predictor, torch, arrays, one, seed=BASE_SEED)
        deterministic &= bool(np.array_equal(base, repeat))
        perturbed = {k: v.copy() for k, v in arrays.items()}
        for k in ("open", "high", "low", "close"):
            perturbed[k][p + 1:] *= 1.10
        perturbed["volume"][p + 1:] *= 3.0
        after, _, _ = forecast_batch(predictor, torch, perturbed, one, seed=BASE_SEED)
        identical += bool(np.array_equal(after, base))
        leaky, _, _ = forecast_batch(predictor, torch, arrays, one + 1, seed=BASE_SEED)
        changed += bool(not np.allclose(leaky, base))
    return {"rows": len(ends), "deterministic": deterministic,
            "unchanged_after_future_perturbation": identical, "leaky_control_changed": changed}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


def build_report(ctx: dict) -> list[str]:
    s = ctx["setup"]
    L = ["XAUUSD M5 - pretrained Kronos-mini research (isolated, no fine-tuning)", "=" * 78, TEST_STATEMENT,
         "No trading, live or production recommendation is made. Results are research diagnostics only.", ""]

    L += ["A. RUN SETUP",
          f"   Model: {MODEL_ID} @ {MODEL_REVISION} ({s['model_params']:,} params)",
          f"   Tokenizer: {TOKENIZER_ID} @ {TOKENIZER_REVISION} ({s['tokenizer_params']:,} params)",
          f"   Code: official KronosPredictor, Kronos repo commit {s['kronos_repo_commit']}; torch {s['torch']}",
          f"   Device: {s['device']} ({s['device_name']}); eval mode enforced (KronosPredictor does not set it)",
          f"   Context window: {CONTEXT_BARS} real M5 bars ending at the closed signal bar (official Kronos-mini "
          "max context)",
          f"   Forecast horizon: {FORECAST_BARS} bars (t+1 .. t+12), nominal 5-minute target timestamps",
          f"   Sampling: {SAMPLING} (README defaults: one sampled path per forecast); batch {BATCH_SIZE}; "
          f"seed {BASE_SEED} + batch index",
          "   Inputs: open, high, low, close, volume = MT5 tick_volume (amount derived by KronosPredictor as "
          "volume x mean price), timestamps (UTC)",
          f"   Prediction timestamps: {s['n_predictions']:,} feature rows from {s['first']} to {s['last']} "
          "(all walk-forward and main validation rows, including label-excluded rows for the signal file)",
          f"   Skipped rows: {s['skipped']}",
          f"   Inference time: {s['inference_minutes']:.1f} min computed in this session"
          f"{' + ' + str(s['resumed_batches']) + ' batches resumed from checkpoint' if s['resumed_batches'] else ''}"
          f" ({s['ms_per_prediction']:.0f} ms per prediction)",
          f"   Contexts spanning at least one market gap: {s['contexts_with_gaps']:,} of {s['n_predictions']:,} "
          "(gaps kept as-is)", ""]

    L += ["   Pre-declared signal rules (fixed before evaluation):"]
    for name, rule in RULES.items():
        L.append(f"     {name}: {rule['description']}")
    L.append("")

    fq = ctx["forecast_quality"]
    L += ["B. PRETRAINED KRONOS FORECAST PERFORMANCE (threshold-free; labeled rows with 12 contiguous future bars)",
          "   MAE in ATR14 units vs a naive no-change forecast; skill > 0 means better than no-change."]
    cols = [f"skill_vs_naive_h{h}" for h in FORECAST_STEPS_REPORTED] + \
           ["direction_hit_rate_h12", "rank_corr_move_h12", "mean_abs_forecast_move_atr", "mean_abs_actual_move_atr"]
    t = fq.set_index("evaluation")[["rows"] + cols].copy()
    for c in cols:
        t[c] = t[c].map(lambda v, c=c: pct(v) if "hit" in c else f"{v:+.4f}" if ("skill" in c or "corr" in c)
                        else f"{v:.3f}")
    L += [t.to_string(), "   Direction hit rate excludes zero moves; 50% = coin flip.", ""]

    L += ["C. DIRECTIONAL CLASSIFICATION PERFORMANCE (current label; primary metric = walk-forward balanced accuracy)"]
    L += [ctx["comparison_table"], f"   Chance level {CHANCE:.4f}. Verdict rule: better/worse by > {MEANINGFUL_DELTA} "
          "in every window; SECONDARY is a sensitivity row and is not used for any decision.",
          "   Main split validation overlaps WF3, so it is not independent evidence.", ""]
    L += ["   Kronos PRIMARY minus RF balanced accuracy (95% paired block-bootstrap interval, 288-bar blocks):"]
    for ev, (d, lo, hi) in ctx["deltas"].items():
        L.append(f"     {ev}: {d:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    L.append("")

    cl = ctx["classification"]
    for ev in ["main", "WF1", "WF2", "WF3"]:
        sub = cl[cl["evaluation"] == ev].set_index("model")
        cols = ["rows", "balanced_accuracy", "macro_f1", "accuracy", "buy_precision", "buy_recall", "sell_precision",
                "sell_recall", "wait_precision", "wait_recall", "buy_predicted_share", "sell_predicted_share",
                "wait_predicted_share"]
        t = sub[cols].copy()
        for c in cols[1:]:
            t[c] = t[c].map(lambda v, c=c: f"{v:.4f}" if c in ("balanced_accuracy", "macro_f1") else pct(v))
        true_dist = sub.iloc[0]
        L += [f"   {ev}: true class distribution BUY {pct(true_dist['buy_true_share'])}, SELL "
              f"{pct(true_dist['sell_true_share'])}, WAIT {pct(true_dist['wait_true_share'])}", t.to_string()]
        L.append("   Confusion matrices (rows = true BUY/SELL/WAIT, columns = predicted BUY/SELL/WAIT):")
        for model, row in sub.iterrows():
            cm = [r.split(",") for r in row["confusion_matrix"].split(";")]
            L.append(f"     {model:<18} " + " | ".join(" ".join(f"{int(v):5d}" for v in r) for r in cm))
        L.append("")

    L += ["   Signal counts over all predicted rows: " + ctx["signal_counts"], ""]

    L += ["D. TRADING DIAGNOSTIC (secondary; main validation period; unchanged backtest_rf_m5 engine)"]
    if ctx["backtest"] is not None:
        bt = ctx["backtest"].set_index("model")
        t = pd.DataFrame({
            "trades": bt["trades"].astype(int), "net_pnl": bt["net_pnl"].map("{:.2f}".format),
            "avg_r": bt["avg_r"].map("{:+.4f}".format), "profit_factor": bt["profit_factor"].map("{:.3f}".format),
            "max_dd": bt["max_closed_trade_dd"].map("{:.2f}".format), "buy_trades": bt["buy_trades"].astype(int),
            "buy_net": bt["buy_net_pnl"].map("{:.2f}".format), "sell_trades": bt["sell_trades"].astype(int),
            "sell_net": bt["sell_net_pnl"].map("{:.2f}".format)})
        L += [t.to_string(),
              "   $ per ounce; drawdown = closed-trade equity only. The RF row is the saved baseline model and "
              "reproduces the existing validation trades exactly.",
              "   The backtester consumed the Kronos signal array without modification. One validation period;",
              "   these numbers are not evidence of profitability."]
    else:
        L.append("   Skipped (partial smoke run).")
    L.append("")

    L += ["E. LEAKAGE AND SAFETY CHECKS"] + [f"   {c}" for c in ctx["checks"]] + [""]

    L += ["F. LIMITATIONS",
          "   - One sampled forecast path per timestamp (sample_count=1, the documented default): each forecast is a",
          "     single stochastic draw, not an expected path. Averaging more paths was not affordable on a 4 GB",
          "     GTX 1050 (about 4 s per forecast with 4 paths). Results are reproducible through fixed seeds.",
          "   - Kronos-mini is pretrained on many markets; it was not fine-tuned on XAUUSD. The terminal-close rule",
          "     is a simple conversion and does not use the forecast high/low path that the TP/SL label depends on.",
          "   - tick_volume is used as volume; Kronos was trained with exchange volume and amount.",
          "   - Timestamps are treated as UTC as instructed; evidence noted earlier suggests broker server time.",
          "   - Market gaps inside the context are presented to Kronos as consecutive bars with their real",
          "     timestamps; the forecast assumes the next 12 five-minute slots are trading bars.",
          "   - Three walk-forward windows and one main split; WF3 and the main split overlap.", ""]

    L += ["G. INTERPRETATION", f"   {ctx['interpretation']}",
          "   Kronos is not declared successful on the basis of any single window; consistency across WF1-WF3 is",
          "   required. No fine-tuning, ensembling, live trading or production integration was performed.", "",
          TEST_STATEMENT]
    return L


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=1, help="smoke test: predict every Nth row only")
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--checkpoint", type=Path,
                        default=Path(os.environ.get("TEMP", ".")) / "kronos_m5_checkpoint.csv")
    args = parser.parse_args()
    full_run = args.stride == 1
    if full_run and args.out_dir.resolve() != DATA_DIR.resolve():
        raise SystemExit("A full run writes to src/data only.")
    outputs = [args.out_dir / n for n in OUTPUT_NAMES]
    if args.checkpoint.resolve().parent in (SRC_DIR, DATA_DIR, MODELS_DIR):
        raise SystemExit("The checkpoint must live outside the project.")
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    skip = {p.resolve() for p in outputs} | {Path(__file__).resolve()}
    hashes_before, test_stat_before = snapshot_files(skip)
    read_targets = [RAW_PATH, FEATURES_PATH, TRAIN_PATH, VALIDATION_PATH, MODEL_PATH, TRADES_PATH]
    read_hashes_before = {p.resolve(): hashes_before[p.resolve()] for p in read_targets}
    install_guards()
    assert RF_PARAMS == FIXED_RF

    val_start, val_end, cutoff = research_boundary()
    GUARD["cutoff"] = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    for path in (RAW_PATH, FEATURES_PATH):
        GUARD["safe_nrows"][path.resolve()] = rows_through(path, GUARD["cutoff"])
    raw, features, positions = load_research_data(val_end, cutoff)
    assert_no_test_rows(raw)
    assert_no_test_rows(features)
    print(f"data loaded up to {raw['time'].max()} (test split starts after {GUARD['cutoff']})")

    times = features["time"]
    starts = [times.iloc[int(len(times) * f)] for f in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"
    eval_windows = {"main": (val_start, val_end, True)}
    eval_windows.update({f"WF{i}": (a, b, i == 3) for i, (a, b) in enumerate(wf_windows, 1)})

    labels = build_labels(raw, features, positions, 1.5, 1.0, 12)
    keep = ~labels["excluded"].to_numpy()
    labeled = features[keep].assign(**{TARGET_COLUMN: labels.loc[keep, TARGET_COLUMN].to_numpy()})

    # ---- RF baseline per window (unchanged features and parameters) -------------
    rf_val, rf_pred = {}, {}
    for ev, (a, b, inclusive) in eval_windows.items():
        train, val = purged_split(labeled, 12, a, b, inclusive_stop=inclusive)
        _, _, model = evaluate_rf(train, val)
        if ev == "main":
            check_current_reproduced(labels, train, val, model)
        rf_val[ev], rf_pred[ev] = val, model.predict(val[RF_FEATURES])
    print("RF baseline evaluated; existing pipeline reproduced")

    # ---- prediction rows and structural leakage checks ----------------------------
    in_range = ((times >= wf_windows[0][0]) & (times <= val_end)).to_numpy()
    rows_idx = np.flatnonzero(in_range)[::args.stride]
    ends = positions[rows_idx].astype(int)
    arrays = market_arrays(raw)
    raw_times = arrays["time"]
    skipped = {"insufficient_history": int((ends < CONTEXT_BARS - 1).sum())}
    assert skipped["insufficient_history"] == 0, "some prediction rows lack a full context window"
    assert (np.diff(raw_times) > np.timedelta64(0, "s")).all(), "raw bars not strictly increasing"
    assert (raw_times[ends] == times.to_numpy()[rows_idx]).all(), "context end differs from the signal bar"
    assert (raw_times[ends] <= np.datetime64(val_end)).all() and (ends + FORECAST_BARS <= len(raw) - 1).all()
    assert np.isfinite(np.column_stack([arrays[k] for k in KRONOS_INPUT])).all(), "missing raw OHLCV values"
    gap_marker = np.concatenate([[0], (np.diff(raw_times) > STEP).astype(int)]).cumsum()
    context_gaps = gap_marker[ends] - gap_marker[ends - CONTEXT_BARS + 1]
    context_span = raw_times[ends] - raw_times[ends - CONTEXT_BARS + 1]
    assert (context_span >= STEP * (CONTEXT_BARS - 1)).all(), "context shorter than its bar count (duplicate bars)"

    # ---- Kronos -------------------------------------------------------------------
    predictor, torch, setup = load_kronos()
    probe = ends[np.linspace(0, len(ends) - 1, min(BATCH_SIZE, len(ends))).astype(int)]
    perturb = future_perturbation_test(predictor, torch, arrays, probe)
    assert perturb["deterministic"], "Kronos inference is not reproducible with a fixed seed"
    assert perturb["unchanged_after_future_perturbation"] == perturb["rows"], "future bars changed a forecast"
    assert perturb["leaky_control_changed"] > 0, "leakage test has no power"
    print(f"future-perturbation test passed ({perturb})")

    close_fc, high_max, low_min, seconds, resumed = run_inference(
        predictor, torch, arrays, ends, times.iloc[rows_idx].reset_index(drop=True), args.checkpoint)
    assert np.isfinite(close_fc).all(), "Kronos returned non-finite forecasts"

    # ---- predictions file ---------------------------------------------------------
    pred = pd.DataFrame({
        "time": times.iloc[rows_idx].to_numpy(),
        "close": arrays["close"][ends], "spread_points": raw["spread"].to_numpy()[ends],
        ATR_COLUMN: features[ATR_COLUMN].to_numpy()[rows_idx],
        "context_start": raw_times[ends - CONTEXT_BARS + 1], "context_end": raw_times[ends],
        "context_bars": CONTEXT_BARS, "context_gaps": context_gaps,
        "forecast_first_target": raw_times[ends] + STEP, "forecast_last_target": raw_times[ends] + STEP * FORECAST_BARS,
        **{f"fc_close_{h}": close_fc[:, h - 1] for h in range(1, FORECAST_BARS + 1)},
        "fc_high_max": high_max, "fc_low_min": low_min,
    })
    pred["round_trip_cost"] = round_trip_cost(pred["spread_points"].to_numpy())
    pred["forecast_move_12"] = pred[f"fc_close_{FORECAST_BARS}"] - pred["close"]
    signals = make_signals(pred[f"fc_close_{FORECAST_BARS}"].to_numpy(), pred["close"].to_numpy(),
                           pred["spread_points"].to_numpy(), pred[ATR_COLUMN].to_numpy())
    pred["signal_primary"], pred["signal_secondary"] = signals["PRIMARY"], signals["SECONDARY"]
    # Labels are joined only after the signals exist.
    pred["label"] = labels[TARGET_COLUMN].to_numpy()[rows_idx]
    pred["label_excluded"] = labels["excluded"].to_numpy()[rows_idx]
    pred["in_main_validation"] = (pred["time"] >= val_start).to_numpy()
    pred["wf_window"] = np.select([(pred["time"] >= a) & ((pred["time"] <= b) if i == 3 else (pred["time"] < b))
                                   for i, (a, b) in enumerate(wf_windows, 1)], ["WF1", "WF2", "WF3"], "")
    pred["batch"] = np.arange(len(pred)) // BATCH_SIZE
    pred["seed"] = BASE_SEED + pred["batch"]
    assert_no_test_rows(pred)

    # ---- evaluation ---------------------------------------------------------------
    by_time = pred.set_index("time")
    pos_by_time = pd.Series(ends, index=pred["time"])
    class_rows, fq_rows, k_bal, r_bal, s_bal, deltas = [], [], {}, {}, {}, {}
    for ev in eval_windows:
        val = rf_val[ev]
        have = val["time"].isin(by_time.index).to_numpy()
        if full_run:
            assert have.all(), f"{ev}: Kronos predictions missing for validation rows"
        val_t = val["time"][have]
        y = val[TARGET_COLUMN].to_numpy()[have]
        p_rf = rf_pred[ev][have]
        p_k = by_time.loc[val_t, "signal_primary"].to_numpy()
        p_s = by_time.loc[val_t, "signal_secondary"].to_numpy()
        for model, p in (("RF baseline", p_rf), ("Kronos PRIMARY", p_k), ("Kronos SECONDARY", p_s)):
            class_rows.append({"section": "classification", "model": model, "evaluation": ev, **classification(y, p)})
        k_bal[ev], r_bal[ev], s_bal[ev] = (balanced_accuracy_score(y, p_k), balanced_accuracy_score(y, p_rf),
                                           balanced_accuracy_score(y, p_s))
        lo, hi = paired_block_bootstrap(y, p_k, p_rf) if len(y) > 300 else (np.nan, np.nan)
        deltas[ev] = (k_bal[ev] - r_bal[ev], lo, hi)
        fq_rows.append({"section": "forecast_quality", "evaluation": ev,
                        **forecast_quality(by_time.loc[val_t].reset_index(), arrays,
                                           pos_by_time.loc[val_t].to_numpy())})
    classification_df = pd.DataFrame(class_rows)
    fq_df = pd.DataFrame(fq_rows)

    wf = ["WF1", "WF2", "WF3"]
    table = []
    for model, bal in (("RF baseline (30 features)", r_bal), ("Kronos-mini PRIMARY", k_bal),
                       ("Kronos-mini SECONDARY", s_bal)):
        vals = [bal[w] for w in wf]
        verdict_text = "reference" if model.startswith("RF") else (
            "sensitivity only (not used)" if "SECONDARY" in model else verdict(vals, [r_bal[w] for w in wf]))
        table.append({"Model": model, **{w: f"{bal[w]:.4f}" for w in wf}, "WF Mean": f"{np.mean(vals):.4f}",
                      "WF Std": f"{np.std(vals, ddof=1):.4f}", "Main Split": f"{bal['main']:.4f}",
                      "Verdict": verdict_text})
    comparison_table = pd.DataFrame(table).to_string(index=False)
    kronos_verdict = table[1]["Verdict"]

    # ---- secondary trading diagnostic ---------------------------------------------
    backtest_df = None
    if full_run:
        val_bt, bt_start, bt_end = load_validation_period(VALIDATION_PATH)
        raw_bt, feats_bt, pos_bt, _ = load_market(bt_start, bt_end)
        assert_no_test_rows(raw_bt)
        rf_model, rf_features = load_model(MODEL_PATH)
        rf_signals = generate_signals(rf_model, feats_bt, rf_features)
        rf_trades, _ = run_backtest(raw_bt, feats_bt, pos_bt, rf_signals)
        existing = pd.read_csv(TRADES_PATH)
        assert len(existing) == len(rf_trades) and np.allclose(existing["net_pnl"], rf_trades["net_pnl"]), \
            "saved RF baseline no longer reproduces the existing validation trades"
        k_signals = by_time["signal_primary"].reindex(feats_bt["time"]).to_numpy()
        assert not pd.isna(k_signals).any(), "Kronos signal missing for a backtest row"
        k_trades, _ = run_backtest(raw_bt, feats_bt, pos_bt, k_signals.astype(np.int64))
        bt_rows = []
        for model, trades in (("RF baseline (saved)", rf_trades), ("Kronos-mini PRIMARY", k_trades)):
            m = trade_metrics(trades)
            for side in ("BUY", "SELL"):
                m.update(trade_metrics(trades[trades["side"] == side], prefix=f"{side.lower()}_"))
            bt_rows.append({"section": "backtest", "model": model, "evaluation": "main_validation", **m})
        backtest_df = pd.DataFrame(bt_rows)

    # ---- rule integrity and file integrity ----------------------------------------
    assert RULES == FROZEN_RULES, "signal rules changed during the run"
    recomputed = make_signals(pred[f"fc_close_{FORECAST_BARS}"].to_numpy(), pred["close"].to_numpy(),
                              pred["spread_points"].to_numpy(), pred[ATR_COLUMN].to_numpy())
    assert all((recomputed[k] == pred[f"signal_{k.lower()}"].to_numpy()).all() for k in RULES)

    hashes_after, test_stat_after = snapshot_files(skip)
    changed = sorted(str(p) for p in set(hashes_before) | set(hashes_after) if hashes_before.get(p) != hashes_after.get(p))
    if changed:
        raise AssertionError(f"existing files changed: {changed}")
    assert all(hashes_after[p] == h for p, h in read_hashes_before.items())
    assert test_stat_after == test_stat_before, "test CSV metadata changed"
    assert GUARD["test_open_attempts"] == 0 and TEST_PATH not in GUARD["csv_reads"]

    counts = {name: pd.Series(pred[f"signal_{name.lower()}"]).map(TARGET_NAMES).value_counts() for name in RULES}
    signal_counts = "; ".join(f"{name}: " + ", ".join(f"{c} {int(counts[name].get(c, 0))}" for c in CLASS_LABELS)
                              for name in RULES)
    reads = ", ".join(sorted({p.name for p in GUARD["csv_reads"]}))
    checks = [
        f"[PASS] 1. No future OHLCV as input: every context is the {CONTEXT_BARS} raw bars ending exactly at the "
        f"signal bar (asserted for all {len(pred):,} rows); altering every bar after t left all "
        f"{perturb['unchanged_after_future_perturbation']}/{perturb['rows']} probe forecasts bit-identical.",
        f"[PASS] 1b. Test has power: a leaky control whose context includes bar t+1 changed "
        f"{perturb['leaky_control_changed']}/{perturb['rows']} probe forecasts; fixed-seed inference is deterministic.",
        f"[PASS] 2. No test data loaded: raw/feature CSVs read with nrows ending at {GUARD['cutoff']} (rows "
        f"{GUARD['safe_nrows'][RAW_PATH.resolve()]:,} / {GUARD['safe_nrows'][FEATURES_PATH.resolve()]:,}); every "
        f"loaded frame checked against that boundary; CSVs read: {reads}.",
        f"[PASS] 3. No context/target overlap: first forecast target = t + 5 min > last context bar = t for every row "
        "(asserted per batch); realised future closes are used only after inference, for scoring.",
        "[PASS] 4. Context contains only real, closed bars <= t: strictly increasing raw timestamps, no NaN, no "
        "synthetic rows (context span >= 2047 x 5 min for every row).",
        f"[PASS] 5. Gaps preserved: {int((context_gaps > 0).sum()):,} contexts span market closures and are passed "
        "unfilled with real timestamps; rows whose 12-bar label window crosses a gap remain excluded from scoring "
        "(existing label rule).",
        "[PASS] 6. No preprocessing lookahead: no global scaling is done here; KronosPredictor normalises each "
        "context by its own mean/std (confirmed by the future-perturbation test).",
        "[PASS] 7. No validation-based threshold tuning: both rules are module constants declared before "
        "evaluation, unchanged at the end, use only forecast + bar-t data, and were recomputed identically from "
        "the saved predictions; labels were joined only after signals were generated.",
        f"[PASS] 8. Existing files unchanged: SHA-256 of {len(hashes_before)} files in src/, src/data/, src/models/ "
        f"identical before and after (including the {len(read_targets)} data/model files read); the test CSV was "
        "never opened (audit hook: 0 attempts; size and modification time unchanged; it was deliberately not "
        "hashed because hashing would open it).",
        "[PASS] Existing pipeline reproduced: labels, train/validation rows and the retrained RF match the existing "
        "CSVs and saved model; walk-forward windows identical to the earlier experiments.",
    ]

    consistent_above = all(k_bal[w] > CHANCE + MEANINGFUL_DELTA for w in wf)
    interpretation = (
        f"Kronos-mini PRIMARY walk-forward balanced accuracy {k_bal['WF1']:.4f} / {k_bal['WF2']:.4f} / "
        f"{k_bal['WF3']:.4f} (mean {np.mean([k_bal[w] for w in wf]):.4f}) vs RF {r_bal['WF1']:.4f} / "
        f"{r_bal['WF2']:.4f} / {r_bal['WF3']:.4f} (mean {np.mean([r_bal[w] for w in wf]):.4f}). Verdict: "
        f"{kronos_verdict}. " + ("The pretrained forecast carries a small directional signal in every window."
                                 if consistent_above else
                                 "The pretrained forecast does not provide a consistent directional signal for this "
                                 "label across the three windows."))

    setup.update({
        "n_predictions": len(pred), "first": str(pred["time"].iloc[0]), "last": str(pred["time"].iloc[-1]),
        "skipped": "none (every prediction row had a full 2048-bar context; no non-finite forecasts)"
                   if full_run else f"smoke run: every {args.stride}th row only",
        "inference_minutes": seconds / 60, "resumed_batches": resumed,
        "ms_per_prediction": 1000 * seconds / max(1, len(pred) - resumed * BATCH_SIZE),
        "contexts_with_gaps": int((context_gaps > 0).sum()),
    })
    report_ctx = {"setup": setup, "forecast_quality": fq_df, "comparison_table": comparison_table, "deltas": deltas,
                  "classification": classification_df, "signal_counts": signal_counts, "backtest": backtest_df,
                  "checks": checks, "interpretation": interpretation}
    lines = build_report(report_ctx)

    run_info = pd.DataFrame([{"section": "run_info", "model": MODEL_ID, "evaluation": "-",
                              "model_revision": MODEL_REVISION, "tokenizer": TOKENIZER_ID,
                              "tokenizer_revision": TOKENIZER_REVISION, "context_bars": CONTEXT_BARS,
                              "forecast_bars": FORECAST_BARS, "sampling": json.dumps(SAMPLING),
                              "batch_size": BATCH_SIZE, "seed": BASE_SEED, "device": setup["device_name"],
                              "predictions": len(pred), "inference_minutes": setup["inference_minutes"],
                              "rules": json.dumps(RULES)}])
    research = pd.concat([classification_df, fq_df] + ([backtest_df] if backtest_df is not None else []) + [run_info],
                         ignore_index=True)

    predictions_path, research_path, report_path = outputs
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    pred.to_csv(predictions_path, index=False)
    research.to_csv(research_path, index=False)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert snapshot_files(skip)[0] == hashes_before, "existing files changed while writing outputs"

    print("\n".join(lines))
    print("\n" + "=" * 78 + "\nSUMMARY")
    print("Files created: " + ", ".join(str(p) for p in outputs) + f" (script: {Path(__file__).resolve()})")
    print(f"Model: {MODEL_ID} @ {MODEL_REVISION} + {TOKENIZER_ID} @ {TOKENIZER_REVISION} on {setup['device_name']}")
    print(f"Context length: {CONTEXT_BARS} bars; forecast horizon: {FORECAST_BARS} bars; predictions: {len(pred):,}")
    print("Kronos PRIMARY balanced accuracy: " + ", ".join(f"{w} {k_bal[w]:.4f}" for w in wf) +
          f"; WF mean {np.mean([k_bal[w] for w in wf]):.4f}; main {k_bal['main']:.4f}")
    print("RF baseline balanced accuracy:    " + ", ".join(f"{w} {r_bal[w]:.4f}" for w in wf) +
          f"; WF mean {np.mean([r_bal[w] for w in wf]):.4f}; main {r_bal['main']:.4f}")
    print(f"Verdict: {kronos_verdict}")
    print("Leakage checks: all 8 passed (see section E)")
    print(f"Test-data safety: {TEST_STATEMENT}")
    print("Existing files unchanged: yes (hash-verified)")
    if args.checkpoint.exists() and full_run:
        print(f"Checkpoint (outside the project, safe to delete): {args.checkpoint}")


if __name__ == "__main__":
    main()
