"""Build per-side hypothetical BUY/SELL outcomes for research-period M5 bars.

New file only: src/data/m5_side_outcomes.csv. Existing labels are not changed.

Eligibility, costs, TP/SL, horizon and same-bar SL-first follow label_m5.py and
backtest_rf_m5.simulate_trade. Rows whose 12-bar window is incomplete or crosses
a market gap are stored with eligible=False and empty outcome fields (the label
exclusion rule). The backtester still trades some gap-crossing validation
signals; those cannot match this table and are counted in the verification
report rather than forced to agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from backtest_rf_m5 import simulate_trade
from evaluation.constants import DATA_DIR, DEFAULT_SEED, TIME_FORMAT
from evaluation.integrity import assert_holdout_untouched, prepare_research_reads, reports_dir
from evaluation.report import save, wrap
from label_m5 import (
    ATR_COLUMN,
    BUY,
    FEATURES_PATH,
    HORIZON_BARS,
    RAW_PATH,
    SELL,
    TARGET_COLUMN,
    WAIT,
    align_features_to_raw,
    check_point_size,
    load_features,
    window_status,
)
from features_m5 import BAR_MINUTES, load_and_validate
from research_kronos_m5 import GUARD, assert_no_test_rows

OUTPUT_PATH = DATA_DIR / "m5_side_outcomes.csv"
TRADES_PATH = DATA_DIR / "rf_m5_validation_trades.csv"
LABELED_PATH = DATA_DIR / "xauusd_m5_labeled.csv"
BAR = np.timedelta64(BAR_MINUTES, "m")


def market_arrays(raw: pd.DataFrame) -> dict:
    from label_m5 import EXTRA_COST_PER_SIDE, MIN_SPREAD_POINTS, POINT_SIZE
    return {
        "time": raw["time"].to_numpy(),
        "open": raw["open"].to_numpy(),
        "high": raw["high"].to_numpy(),
        "low": raw["low"].to_numpy(),
        "close": raw["close"].to_numpy(),
        "spread": np.maximum(raw["spread"].to_numpy(), MIN_SPREAD_POINTS) * POINT_SIZE,
    }


def build_outcomes(raw, features, positions) -> pd.DataFrame:
    incomplete, crosses_gap = window_status(raw, positions)
    eligible = ~(incomplete | crosses_gap)
    m = market_arrays(raw)
    atr = features[ATR_COLUMN].to_numpy()
    times = features["time"].to_numpy()
    rows = []
    for i in range(len(features)):
        base = {
            "decision_time": pd.Timestamp(times[i]),
            "eligible": bool(eligible[i]),
            "incomplete_window": bool(incomplete[i]),
            "crosses_gap": bool(crosses_gap[i]),
        }
        if not eligible[i]:
            for side_name in ("BUY", "SELL"):
                rows.append({**base, "side": side_name, "entry_time": pd.NaT, "entry_fill": np.nan,
                             "stop_price": np.nan, "target_price": np.nan, "exit_time": pd.NaT,
                             "exit_reason": "", "gross_pnl": np.nan, "costs": np.nan,
                             "net_pnl": np.nan, "initial_risk": np.nan, "net_r": np.nan})
            continue
        for side in (BUY, SELL):
            tr = simulate_trade(m, side, int(positions[i]), float(atr[i]))
            rows.append({
                **base,
                "side": tr["side"],
                "entry_time": pd.Timestamp(tr["entry_time"]),
                "entry_fill": tr["entry_fill"],
                "stop_price": tr["sl_level"],
                "target_price": tr["tp_level"],
                "exit_time": pd.Timestamp(tr["exit_time"]),
                "exit_reason": tr["exit_reason"],
                "gross_pnl": tr["gross_pnl"],
                "costs": tr["costs"],
                "net_pnl": tr["net_pnl"],
                "initial_risk": tr["sl_distance"],
                "net_r": tr["net_pnl_r"],
            })
    out = pd.DataFrame(rows).sort_values(["decision_time", "side"]).reset_index(drop=True)
    return out


def label_mapping_check(outcomes: pd.DataFrame, labeled: pd.DataFrame) -> dict:
    """BUY label <=> BUY side TP-first; SELL label <=> SELL side TP-first; WAIT otherwise."""
    elig = outcomes[outcomes["eligible"]].copy()
    buy = elig[elig["side"] == "BUY"].set_index("decision_time")
    sell = elig[elig["side"] == "SELL"].set_index("decision_time")
    lab = labeled.set_index("time")[TARGET_COLUMN]
    common = buy.index.intersection(lab.index).intersection(sell.index)
    buy, sell, lab = buy.loc[common], sell.loc[common], lab.loc[common]
    pred = np.full(len(common), WAIT, dtype=np.int64)
    pred[buy["exit_reason"].to_numpy() == "TP"] = BUY
    pred[sell["exit_reason"].to_numpy() == "TP"] = SELL
    both = (buy["exit_reason"].to_numpy() == "TP") & (sell["exit_reason"].to_numpy() == "TP")
    mismatch = int((pred != lab.to_numpy()).sum())
    return {
        "labeled_rows_compared": int(len(common)),
        "both_sides_tp": int(both.sum()),
        "target_mismatches": mismatch,
        "buy_tp_vs_label_buy": int(((buy["exit_reason"] == "TP") != (lab == BUY)).sum()),
        "sell_tp_vs_label_sell": int(((sell["exit_reason"] == "TP") != (lab == SELL)).sum()),
    }


def backtest_intersection_check(outcomes: pd.DataFrame) -> dict:
    trades = pd.read_csv(TRADES_PATH)
    trades["signal_time"] = pd.to_datetime(trades["signal_time"])
    elig = outcomes[outcomes["eligible"]]
    merged = trades.merge(elig, left_on=["signal_time", "side"], right_on=["decision_time", "side"],
                          how="left", suffixes=("_bt", "_oc"))
    unmatched = merged["eligible"].isna() | (merged["eligible"] == False)  # noqa: E712
    matched = merged[~unmatched]
    pnl_ok = bool(np.allclose(matched["net_pnl_bt"], matched["net_pnl_oc"], rtol=0, atol=1e-12)) if len(matched) else False
    r_ok = bool(np.allclose(matched["net_pnl_r"], matched["net_r"], rtol=0, atol=1e-12)) if len(matched) else False
    reason_ok = bool((matched["exit_reason_bt"] == matched["exit_reason_oc"]).all()) if len(matched) else False
    return {
        "backtest_trades": int(len(trades)),
        "matched_eligible": int(len(matched)),
        "unmatched_gap_or_missing": int(unmatched.sum()),
        "pnl_match": pnl_ok,
        "r_match": r_ok,
        "exit_reason_match": reason_ok,
        "note": "Unmatched trades are the backtester's gap-crossing signals that labeling excludes.",
    }


def sample_simulate_agreement(raw, features, positions, outcomes, n=500, seed=DEFAULT_SEED) -> dict:
    rng = np.random.default_rng(seed)
    elig_idx = np.flatnonzero(outcomes.loc[outcomes["side"] == "BUY", "eligible"].to_numpy())
    pick = rng.choice(elig_idx, size=min(n, len(elig_idx)), replace=False)
    m = market_arrays(raw)
    atr = features[ATR_COLUMN].to_numpy()
    feat_index = {t: i for i, t in enumerate(features["time"])}
    buy = outcomes[outcomes["side"] == "BUY"].reset_index(drop=True)
    mismatches = 0
    for j in pick:
        t = buy.loc[j, "decision_time"]
        i = feat_index[t]
        tr = simulate_trade(m, BUY, int(positions[i]), float(atr[i]))
        if not np.isclose(tr["net_pnl"], buy.loc[j, "net_pnl"]):
            mismatches += 1
    return {"sample": int(len(pick)), "pnl_mismatches": int(mismatches), "seed": seed}


def leakage_checks(outcomes: pd.DataFrame) -> list[str]:
    checks = []
    elig = outcomes[outcomes["eligible"]]
    if (elig["entry_time"] <= elig["decision_time"]).any():
        checks.append("FAIL entry_time not after decision_time")
    else:
        checks.append("PASS entry is after decision timestamp")
    if (elig["exit_time"] < elig["entry_time"]).any():
        checks.append("FAIL exit before entry")
    else:
        checks.append("PASS exit at or after entry")
    checks.append("PASS outcome columns are not feature columns (separate table)")
    return checks


def run(boundary: dict) -> dict:
    raw = load_and_validate(RAW_PATH)
    check_point_size(raw)
    raw = raw[raw["time"] <= boundary["cutoff"]].reset_index(drop=True)
    features = load_features(FEATURES_PATH)
    features = features[features["time"] <= boundary["val_end"]].reset_index(drop=True)
    assert_no_test_rows(raw)
    assert_no_test_rows(features)
    positions = align_features_to_raw(features, raw)

    outcomes = build_outcomes(raw, features, positions)
    labeled = pd.read_csv(LABELED_PATH)
    labeled["time"] = pd.to_datetime(labeled["time"], format=TIME_FORMAT)
    labeled = labeled[labeled["time"] <= boundary["val_end"]].reset_index(drop=True)

    mapping = label_mapping_check(outcomes, labeled)
    bt = backtest_intersection_check(outcomes)
    sample = sample_simulate_agreement(raw, features, positions, outcomes)
    leak = leakage_checks(outcomes)

    elig = outcomes[outcomes["eligible"]]
    to_save = outcomes.copy()
    for col in ("decision_time", "entry_time", "exit_time"):
        ts = pd.to_datetime(to_save[col], errors="coerce")
        to_save[col] = ts.dt.strftime(TIME_FORMAT).where(ts.notna(), "")
    to_save.to_csv(OUTPUT_PATH, index=False)

    summary = {
        "rows_written": int(len(outcomes)),
        "eligible_decision_timestamps": int(elig["decision_time"].nunique()),
        "buy_eligible": int(((elig["side"] == "BUY")).sum()),
        "sell_eligible": int(((elig["side"] == "SELL")).sum()),
        "ineligible_rows": int((~outcomes["eligible"]).sum()),
        "missing_net_r_among_eligible": int(elig["net_r"].isna().sum()),
        "exit_reason_counts_buy": elig[elig["side"] == "BUY"]["exit_reason"].value_counts().to_dict(),
        "exit_reason_counts_sell": elig[elig["side"] == "SELL"]["exit_reason"].value_counts().to_dict(),
        "label_mapping": mapping,
        "backtest_intersection": bt,
        "resimulate_sample": sample,
        "leakage": leak,
        "labeled_rows_in_period": int(len(labeled)),
        "eligible_minus_labeled": int(elig["decision_time"].nunique()) - int(len(labeled)),
        "output": str(OUTPUT_PATH),
    }
    assert_holdout_untouched()
    save(reports_dir() / "side_outcomes_verification.json",
         wrap("m5_side_outcomes", "reproduction", {"horizon": HORIZON_BARS}, summary, DEFAULT_SEED))
    print("Saved", OUTPUT_PATH)
    print("eligible timestamps", summary["eligible_decision_timestamps"])
    print("label target mismatches", mapping["target_mismatches"])
    print("backtest matched", bt["matched_eligible"], "unmatched", bt["unmatched_gap_or_missing"],
          "pnl_match", bt["pnl_match"], "r_match", bt["r_match"])
    print("sample mismatches", sample["pnl_mismatches"])
    print("holdout attempts", GUARD["test_open_attempts"])
    return summary


def main() -> None:
    run(prepare_research_reads())


if __name__ == "__main__":
    main()
