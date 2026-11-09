"""Pre-registered Phase 13 decision rules. No unrestricted search."""

from __future__ import annotations

import numpy as np

from phase13.constants import (
    BREAKOUT_LOOKBACK,
    BREAKOUT_LOOKBACK_SENSITIVITY,
    FOLDS,
    GAP_MIN,
    HYPOTHESIS_IDS,
)
from phase13.data_loader import fold_of, train_times_for_fold
from phase13.h1_context import build_h1_lookup, h1_context_at


def _f(row: dict, key: str) -> float:
    return float(row[key])


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=float), q))


def train_atr_cuts(bundle: dict, fold_id: str) -> dict:
    # Expanding train uses feature history before the purged eval start — not only OOS rows.
    times = train_times_for_fold(bundle["feature_times"], fold_id)
    atrs = []
    discounts = []
    for t in times:
        feat = bundle["features"].get(t)
        if feat is None:
            continue
        atrs.append(_f(feat, "atr_14_pct"))
        discounts.append(_f(feat, "close_to_ema_20"))
    return {
        "atr_p33": _percentile(atrs, 33),
        "atr_p67": _percentile(atrs, 67),
        "close_ema_p25": _percentile(discounts, 25),
        "close_ema_p75": _percentile(discounts, 75),
        "n_train_rows": len(atrs),
    }


def _range_prior(bundle: dict, t: str, lookback: int) -> tuple[float, float] | None:
    idx = bundle["feature_index"].get(t)
    if idx is None or idx < lookback:
        return None
    times = bundle["feature_times"]
    highs = []
    lows = []
    for j in range(idx - lookback, idx):
        feat = bundle["features"][times[j]]
        highs.append(_f(feat, "high"))
        lows.append(_f(feat, "low"))
    return max(highs), min(lows)


def signal_breakout_failure(bundle: dict, t: str, cuts: dict, lookback: int) -> str:
    feat = bundle["features"].get(t)
    if feat is None:
        return "WAIT"
    if not (cuts["atr_p33"] == cuts["atr_p33"]):  # NaN
        return "WAIT"
    if _f(feat, "atr_14_pct") > cuts["atr_p33"]:
        return "WAIT"
    rng = _range_prior(bundle, t, lookback)
    if rng is None:
        return "WAIT"
    range_high, range_low = rng
    high = _f(feat, "high")
    low = _f(feat, "low")
    close = _f(feat, "close")
    sell = high > range_high and close < range_high
    buy = low < range_low and close > range_low
    if buy and sell:
        return "WAIT"
    if sell:
        return "SELL"
    if buy:
        return "BUY"
    return "WAIT"


def signal_vol_expansion_trend(bundle: dict, t: str, cuts: dict) -> str:
    feat = bundle["features"].get(t)
    if feat is None or cuts["atr_p67"] != cuts["atr_p67"]:
        return "WAIT"
    if _f(feat, "atr_14_pct") < cuts["atr_p67"]:
        return "WAIT"
    s1 = _f(feat, "ema_9_20_spread")
    s2 = _f(feat, "ema_20_50_spread")
    if s1 > 0 and s2 > 0:
        return "BUY"
    if s1 < 0 and s2 < 0:
        return "SELL"
    return "WAIT"


def signal_h1_pullback(bundle: dict, t: str, cuts: dict, h1_lookup: list) -> str:
    feat = bundle["features"].get(t)
    ctx = h1_context_at(h1_lookup, t)
    if feat is None or ctx is None:
        return "WAIT"
    c2e = _f(feat, "close_to_ema_20")
    s1 = _f(feat, "ema_9_20_spread")
    if ctx["h1_trend"] == "up" and c2e <= cuts["close_ema_p25"] and s1 > 0:
        return "BUY"
    if ctx["h1_trend"] == "down" and c2e >= cuts["close_ema_p75"] and s1 < 0:
        return "SELL"
    return "WAIT"


def signal_pred_gap_midvol(bundle: dict, t: str, cuts: dict) -> str:
    feat = bundle["features"].get(t)
    oos = bundle["oos"].get(t)
    if feat is None or oos is None:
        return "WAIT"
    atr = _f(feat, "atr_14_pct")
    if not (cuts["atr_p33"] <= atr <= cuts["atr_p67"]):
        return "WAIT"
    buy_r = float(oos["pred_r_rf"].get("BUY", float("nan")))
    sell_r = float(oos["pred_r_rf"].get("SELL", float("nan")))
    if buy_r != buy_r or sell_r != sell_r:
        return "WAIT"
    if abs(buy_r - sell_r) < GAP_MIN:
        return "WAIT"
    if buy_r > sell_r and buy_r > 0:
        return "BUY"
    if sell_r > buy_r and sell_r > 0:
        return "SELL"
    return "WAIT"


def signal_e1(bundle: dict, t: str) -> str:
    oos = bundle["oos"].get(t)
    if oos is None:
        return "WAIT"
    buy_r = float(oos["pred_r_rf"].get("BUY", float("nan")))
    sell_r = float(oos["pred_r_rf"].get("SELL", float("nan")))
    if buy_r != buy_r or sell_r != sell_r:
        return "WAIT"
    if buy_r > sell_r and buy_r > 0:
        return "BUY"
    if sell_r > buy_r and sell_r > 0:
        return "SELL"
    return "WAIT"


def hypothesis_registry() -> list[dict]:
    return [
        {
            "hypothesis_id": "H13_A_BREAKOUT_FAILURE",
            "family": "volatility_contraction_structure",
            "lookback_primary": BREAKOUT_LOOKBACK,
            "lookback_sensitivity": BREAKOUT_LOOKBACK_SENSITIVITY,
            "status_before_scoring": "PRE_REGISTERED",
        },
        {
            "hypothesis_id": "H13_B_VOL_EXPANSION_TREND",
            "family": "volatility_expansion_trend",
            "status_before_scoring": "PRE_REGISTERED",
        },
        {
            "hypothesis_id": "H13_C_H1_PULLBACK",
            "family": "multi_timeframe_pullback",
            "status_before_scoring": "PRE_REGISTERED",
        },
        {
            "hypothesis_id": "H13_D_PRED_GAP_MIDVOL",
            "family": "prediction_conviction_filter",
            "gap_min": GAP_MIN,
            "status_before_scoring": "PRE_REGISTERED",
        },
    ]


def generate_decisions(bundle: dict) -> dict:
    """Produce decisions for all hypotheses and baselines on OOS timestamps."""
    h1_lookup = build_h1_lookup(bundle["h1_rows"])
    cuts_by_fold = {fid: train_atr_cuts(bundle, fid) for fid in FOLDS}
    out = {hid: {} for hid in HYPOTHESIS_IDS}
    out["H13_A_SENS_L8"] = {}
    out["B_WAIT"] = {}
    out["B_E1"] = {}
    h1_hits = 0
    for t in bundle["timestamps"]:
        fold_id = fold_of(t)
        cuts = cuts_by_fold[fold_id]
        out["H13_A_BREAKOUT_FAILURE"][t] = signal_breakout_failure(
            bundle, t, cuts, BREAKOUT_LOOKBACK
        )
        out["H13_A_SENS_L8"][t] = signal_breakout_failure(
            bundle, t, cuts, BREAKOUT_LOOKBACK_SENSITIVITY
        )
        out["H13_B_VOL_EXPANSION_TREND"][t] = signal_vol_expansion_trend(bundle, t, cuts)
        out["H13_C_H1_PULLBACK"][t] = signal_h1_pullback(bundle, t, cuts, h1_lookup)
        if h1_context_at(h1_lookup, t) is not None:
            h1_hits += 1
        out["H13_D_PRED_GAP_MIDVOL"][t] = signal_pred_gap_midvol(bundle, t, cuts)
        out["B_WAIT"][t] = "WAIT"
        out["B_E1"][t] = signal_e1(bundle, t)
    coverage = h1_hits / max(len(bundle["timestamps"]), 1)
    return {
        "decisions": out,
        "cuts_by_fold": cuts_by_fold,
        "h1_coverage": coverage,
        "n_timestamps": len(bundle["timestamps"]),
    }
