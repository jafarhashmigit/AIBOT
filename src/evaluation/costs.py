"""Cost-sensitivity helpers.

The production backtester (backtest_rf_m5.py) is not modified. A spread
multiplier is applied to a *copy* of the floored spread used at fill time,
leaving the $0.05/side allowance unchanged (the E15/E16 convention).

This is a documented evaluation utility, not a change to historical results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_rf_m5 import run_backtest
from label_m5 import EXTRA_COST_PER_SIDE, MIN_SPREAD_POINTS, POINT_SIZE


def apply_spread_multiplier(raw: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """Return a copy whose `spread` column is scaled after the 15-point floor.

    run_backtest floors again with max(spread, 15)*0.01, so we encode the
    already-floored, multiplied spread *in points* by writing
    multiplier * max(original, 15) into the copy. The second floor then
    keeps that value for multiplier >= 1.
    """
    if multiplier < 1:
        raise ValueError("spread multiplier must be >= 1 (stress, not a discount)")
    out = raw.copy()
    floored = np.maximum(out["spread"].to_numpy(float), MIN_SPREAD_POINTS)
    out["spread"] = floored * multiplier
    return out


def cost_in_r(costs, sl_distance) -> np.ndarray:
    sl = np.asarray(sl_distance, dtype=float)
    return np.asarray(costs, dtype=float) / sl
