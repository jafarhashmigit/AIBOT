"""Independent sample reconstruction of cost-aware triple-barrier outcomes."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backtest_rf_m5 import simulate_trade
from features_m5 import load_and_validate
from label_m5 import (
    ATR_COLUMN,
    BUY,
    HORIZON_BARS,
    RAW_PATH,
    SELL,
    align_features_to_raw,
    check_point_size,
    load_features,
    window_status,
)
from phase31.constants import (
    EVAL_SEED,
    FEATURES_UTC_PATH,
    HOLDOUT_NAME,
    LABEL_SAMPLE_N,
    OUTCOMES_PATH,
    RESEARCH_CUTOFF_UTC,
)


def _market_arrays(raw: pd.DataFrame) -> dict:
    from label_m5 import EXTRA_COST_PER_SIDE, MIN_SPREAD_POINTS, POINT_SIZE

    return {
        "time": raw["time"].to_numpy(),
        "open": raw["open"].to_numpy(),
        "high": raw["high"].to_numpy(),
        "low": raw["low"].to_numpy(),
        "close": raw["close"].to_numpy(),
        "spread": np.maximum(raw["spread"].to_numpy(), MIN_SPREAD_POINTS) * POINT_SIZE,
    }


def _unit_synthetic_cases() -> dict[str, Any]:
    """Contract checks on tiny synthetic series (SL-before-TP same candle, etc.)."""
    from phase18.barrier import EXTRA_COST_PER_SIDE, simulate_trade_horizon

    # Contiguous 20 bars
    times = np.arange("2026-01-01T00:00", "2026-01-01T01:40", dtype="datetime64[m]")[::5]
    n = len(times)
    open_ = np.full(n, 2000.0)
    high = np.full(n, 2001.0)
    low = np.full(n, 1999.0)
    close = np.full(n, 2000.0)
    spread = np.full(n, 0.15)
    # Bar 2 (entry): both sides touch — SL should win for BUY
    high[2] = 2010.0
    low[2] = 1980.0
    m = {"time": times, "open": open_, "high": high, "low": low, "close": close, "spread": spread}
    atr = 2.0
    buy = simulate_trade_horizon(m, 1, signal_pos=0, atr=atr, horizon_bars=12)
    sell = simulate_trade_horizon(m, -1, signal_pos=0, atr=atr, horizon_bars=12)
    # Incomplete window
    incomplete_ok = False
    try:
        simulate_trade_horizon(m, 1, signal_pos=n - 3, atr=atr, horizon_bars=12)
    except ValueError:
        incomplete_ok = True
    return {
        "same_candle_buy_sl_priority": buy["exit_reason"] == "SL",
        "same_candle_sell_sl_priority": sell["exit_reason"] == "SL",
        "entry_is_next_open": str(buy["entry_time"])[:19] == str(times[1])[:19],
        "incomplete_horizon_raises": incomplete_ok,
        "extra_cost_per_side": EXTRA_COST_PER_SIDE,
        "horizon_bars_contract": HORIZON_BARS,
    }


def run_label_reconstruction_audit(*, sample_n: int = LABEL_SAMPLE_N) -> dict[str, Any]:
    if HOLDOUT_NAME in str(OUTCOMES_PATH) or HOLDOUT_NAME in str(FEATURES_UTC_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")

    unit = _unit_synthetic_cases()

    # Prefer UTC-corrected features for ATR/time; fall back alignment via raw.
    # Outcomes were built from original feature store timestamps aligned to raw.
    raw = load_and_validate(RAW_PATH)
    # Use original features path used by label builder when available
    from label_m5 import FEATURES_PATH

    features = load_features(FEATURES_PATH)
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    features = features[features["time"] <= cutoff].reset_index(drop=True)
    check_point_size(raw)
    positions = align_features_to_raw(features, raw)
    incomplete, crosses_gap = window_status(raw, positions)
    eligible_idx = np.where(~(incomplete | crosses_gap))[0]

    rng = np.random.default_rng(EVAL_SEED)
    take = min(sample_n, len(eligible_idx))
    sample_idx = np.sort(rng.choice(eligible_idx, size=take, replace=False))

    outcomes = pd.read_csv(OUTCOMES_PATH)
    outcomes["decision_time"] = pd.to_datetime(outcomes["decision_time"])
    # Index eligible stored outcomes
    elig = outcomes[outcomes["eligible"] == True].copy()  # noqa: E712

    m = _market_arrays(raw)
    atr = features[ATR_COLUMN].to_numpy()
    times = features["time"].to_numpy()

    match = 0
    mismatch = 0
    categories: dict[str, int] = {}
    examples: list[dict] = []

    for i in sample_idx:
        for side in (BUY, SELL):
            tr = simulate_trade(m, side, int(positions[i]), float(atr[i]))
            dt = pd.Timestamp(times[i])
            side_name = "BUY" if side == BUY else "SELL"
            row = elig[(elig["decision_time"] == dt) & (elig["side"] == side_name)]
            if row.empty:
                mismatch += 1
                categories["missing_in_stored"] = categories.get("missing_in_stored", 0) + 1
                if len(examples) < 8:
                    examples.append({"decision_time": str(dt), "side": side_name, "issue": "missing_in_stored"})
                continue
            r = row.iloc[0]
            ok = (
                str(r["exit_reason"]) == str(tr["exit_reason"])
                and np.isclose(float(r["net_r"]), float(tr["net_pnl_r"]), atol=1e-8, equal_nan=True)
                and np.isclose(float(r["entry_fill"]), float(tr["entry_fill"]), atol=1e-8)
            )
            if ok:
                match += 1
            else:
                mismatch += 1
                cat = "exit_reason" if str(r["exit_reason"]) != str(tr["exit_reason"]) else "numeric"
                categories[cat] = categories.get(cat, 0) + 1
                if len(examples) < 8:
                    examples.append(
                        {
                            "decision_time": str(dt),
                            "side": side_name,
                            "stored_exit": r["exit_reason"],
                            "recon_exit": tr["exit_reason"],
                            "stored_net_r": float(r["net_r"]),
                            "recon_net_r": float(tr["net_pnl_r"]),
                        }
                    )

    total = match + mismatch
    return {
        "holdout_opened": False,
        "contract": {
            "decision_at": "feature/candle t (close)",
            "entry": "t+1 open + costs",
            "horizon": f"t+1 .. t+{HORIZON_BARS}",
            "tp": "1.5 * ATR14[t]",
            "sl": "1.0 * ATR14[t]",
            "same_candle_priority": "SL before TP",
        },
        "unit_synthetic": unit,
        "sample_n_decision_rows": int(take),
        "comparisons": int(total),
        "exact_match_count": int(match),
        "mismatch_count": int(mismatch),
        "mismatch_pct": (mismatch / total) if total else None,
        "mismatch_categories": categories,
        "representative_mismatches": examples,
        "reconstruction_agrees": mismatch == 0 and unit["same_candle_buy_sl_priority"] and unit["same_candle_sell_sl_priority"],
        "note": "Sampled eligible rows reconstructed via backtest_rf_m5.simulate_trade; Phase2 artifacts not modified.",
    }
