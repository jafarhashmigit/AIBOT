"""Frozen candidate signal generation (no parameter changes)."""

from __future__ import annotations

from phase25.strategies.mean_reversion import decide_mean_reversion
from phase35.strategies_runner import decide_h13c
from phase41.constants import H13C_FROZEN_CUTS
from phase41.features import bars_lookback, h1_ctx_at


def decide_h13c_frozen(feat_bundle: dict, decision_time: str) -> tuple[str, str]:
    feat = feat_bundle["features"].get(decision_time)
    if feat is None:
        return "WAIT", "missing_m5_features"
    if feat.get("close_to_ema_20") is None or feat.get("ema_9_20_spread") is None:
        return "WAIT", "ema_warmup_incomplete"
    h1 = h1_ctx_at(feat_bundle, decision_time)
    return decide_h13c(feat, h1, H13C_FROZEN_CUTS)


def decide_mr_frozen(feat_bundle: dict, decision_time: str) -> tuple[str, str]:
    feat = feat_bundle["features"].get(decision_time)
    bars = bars_lookback(feat_bundle, decision_time)
    if feat is None or bars is None:
        return "WAIT", "missing_features"
    if feat.get("atr_14_pct") is None:
        return "WAIT", "atr_warmup_incomplete"
    return decide_mean_reversion({"feat": feat, "bars": bars, "h1_ctx": {}})
