"""Predeclared Phase 30 strategy registry (10 candidates)."""

from __future__ import annotations

from phase30.strategies.body_persistence import decide as decide_body_persistence
from phase30.strategies.compression_expansion import decide as decide_compression_expansion
from phase30.strategies.london_open_imbalance import decide as decide_london_open_imbalance
from phase30.strategies.m15_trend_m5_trigger import decide as decide_m15_trend_m5_trigger
from phase30.strategies.momentum_structure_ensemble import decide as decide_momentum_structure_ensemble
from phase30.strategies.regime_cond_momentum import decide as decide_regime_cond_momentum
from phase30.strategies.regression_residual_mr import decide as decide_regression_residual_mr
from phase30.strategies.robust_mad_reversion import decide as decide_robust_mad_reversion
from phase30.strategies.vol_norm_momentum import decide as decide_vol_norm_momentum
from phase30.strategies.wick_exhaustion import decide as decide_wick_exhaustion

STRATEGIES = {
    "vol_norm_momentum": decide_vol_norm_momentum,
    "compression_expansion": decide_compression_expansion,
    "robust_mad_reversion": decide_robust_mad_reversion,
    "regression_residual_mr": decide_regression_residual_mr,
    "wick_exhaustion": decide_wick_exhaustion,
    "regime_cond_momentum": decide_regime_cond_momentum,
    "london_open_imbalance": decide_london_open_imbalance,
    "m15_trend_m5_trigger": decide_m15_trend_m5_trigger,
    "body_persistence": decide_body_persistence,
    "momentum_structure_ensemble": decide_momentum_structure_ensemble,
}

__all__ = ["STRATEGIES"]
