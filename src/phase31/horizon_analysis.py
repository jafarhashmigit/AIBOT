"""Horizon diagnostic H1/H2/H3/H6/H12 via Phase18 barrier on a controlled sample."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from features_m5 import load_and_validate
from label_m5 import ATR_COLUMN, FEATURES_PATH, RAW_PATH, align_features_to_raw, load_features, window_status
from phase18.barrier import BUY, SELL, simulate_trade_horizon
from phase31.constants import EVAL_SEED, HOLDOUT_NAME, HORIZON_SAMPLE_N, HORIZONS, RESEARCH_CUTOFF_UTC


def _perf(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean_r": None, "median_r": None, "win_rate": None, "profit_factor": None}
    a = np.asarray(xs, dtype=float)
    gains = a[a > 0].sum()
    losses = -a[a < 0].sum()
    pf = float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else None)
    return {
        "n": int(len(a)),
        "mean_r": float(a.mean()),
        "median_r": float(np.median(a)),
        "win_rate": float((a > 0).mean()),
        "profit_factor": pf if pf != float("inf") else "inf",
    }


def run_horizon_analysis(*, sample_n: int = HORIZON_SAMPLE_N) -> dict[str, Any]:
    if HOLDOUT_NAME in str(RAW_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    raw = load_and_validate(RAW_PATH)
    features = load_features(FEATURES_PATH)
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    features = features[features["time"] <= cutoff].reset_index(drop=True)
    positions = align_features_to_raw(features, raw)
    incomplete, crosses_gap = window_status(raw, positions)
    eligible = np.where(~(incomplete | crosses_gap))[0]
    rng = np.random.default_rng(EVAL_SEED)
    take = min(sample_n, len(eligible))
    idxs = np.sort(rng.choice(eligible, size=take, replace=False))

    from label_m5 import MIN_SPREAD_POINTS, POINT_SIZE

    m = {
        "time": raw["time"].to_numpy().astype("datetime64[s]"),
        "open": raw["open"].to_numpy(dtype=float),
        "high": raw["high"].to_numpy(dtype=float),
        "low": raw["low"].to_numpy(dtype=float),
        "close": raw["close"].to_numpy(dtype=float),
        "spread": np.maximum(raw["spread"].to_numpy(dtype=float), MIN_SPREAD_POINTS) * POINT_SIZE,
    }
    atr = features[ATR_COLUMN].to_numpy(dtype=float)

    by_h: dict[str, dict[str, Any]] = {}
    for hid, hb in HORIZONS.items():
        buy_r, sell_r = [], []
        buy_bars_tp, buy_bars_sl = [], []
        sell_bars_tp, sell_bars_sl = [], []
        timeout = 0
        matured = 0
        for i in idxs:
            pos = int(positions[i])
            for side, sink, tp_list, sl_list in (
                (BUY, buy_r, buy_bars_tp, buy_bars_sl),
                (SELL, sell_r, sell_bars_tp, sell_bars_sl),
            ):
                try:
                    tr = simulate_trade_horizon(m, side, pos, float(atr[i]), horizon_bars=hb)
                except Exception:
                    continue
                matured += 1
                sink.append(float(tr["net_pnl_r"]))
                if tr["exit_reason"] == "TIME":
                    timeout += 1
                elif tr["exit_reason"] == "TP":
                    tp_list.append(int(tr["bars_held"]))
                elif tr["exit_reason"] == "SL":
                    sl_list.append(int(tr["bars_held"]))
        combined = buy_r + sell_r
        by_h[hid] = {
            "horizon_bars": hb,
            "n_matured_side_outcomes": matured,
            "BUY": _perf(buy_r),
            "SELL": _perf(sell_r),
            "combined": _perf(combined),
            "timeout_rate": (timeout / matured) if matured else None,
            "mean_bars_to_tp_buy": float(np.mean(buy_bars_tp)) if buy_bars_tp else None,
            "mean_bars_to_sl_buy": float(np.mean(buy_bars_sl)) if buy_bars_sl else None,
            "mean_bars_to_tp_sell": float(np.mean(sell_bars_tp)) if sell_bars_tp else None,
            "mean_bars_to_sl_sell": float(np.mean(sell_bars_sl)) if sell_bars_sl else None,
            "note": "MFE/MAE path statistics require tick paths; not available from OHLC barriers alone.",
        }

    # Least-poor horizon by combined mean_r
    ranked = sorted(
        ((hid, by_h[hid]["combined"]["mean_r"]) for hid in by_h if by_h[hid]["combined"]["mean_r"] is not None),
        key=lambda x: x[1],
        reverse=True,
    )
    return {
        "holdout_opened": False,
        "sample_n_decision_rows": int(take),
        "by_horizon": by_h,
        "least_poor_horizon": ranked[0][0] if ranked else None,
        "diagnostic_only": True,
        "not_a_trading_policy": True,
        "overlap_note": "Adjacent decisions share overlapping evaluation windows; horizons are not independent samples.",
    }
