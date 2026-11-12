"""Frozen candidate signal generation (no parameter changes)."""

from __future__ import annotations

from typing import Any

from phase25.strategies.mean_reversion import decide_mean_reversion
from phase35.strategies_runner import decide_h13c
from phase39.constants import H13C_FROZEN_CUTS
from phase39.features import bars_lookback, h1_ctx_at


def decide_h13c_frozen(feat_bundle: dict, decision_time: str) -> tuple[str, str]:
    feat = feat_bundle["features"].get(decision_time)
    h1 = h1_ctx_at(feat_bundle, decision_time)
    return decide_h13c(feat, h1, H13C_FROZEN_CUTS)


def decide_mr_frozen(feat_bundle: dict, decision_time: str) -> tuple[str, str]:
    feat = feat_bundle["features"].get(decision_time)
    bars = bars_lookback(feat_bundle, decision_time)
    if feat is None or bars is None:
        return "WAIT", "missing_features"
    return decide_mean_reversion({"feat": feat, "bars": bars, "h1_ctx": {}})
