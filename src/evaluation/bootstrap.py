"""Bootstrap confidence intervals.

Two estimators are provided and must not be mixed when comparing to saved results:

1. iid_trade_bootstrap_mean  — resample trades independently (E12 / conditional-edge).
   This IGNORES serial correlation. Used only to reproduce existing E12 figures.

2. day_cluster_bootstrap_mean — resample trading-day clusters with replacement.
   This is the G2 estimator in ACCEPTANCE_CRITERIA.md ("block = one trading day
   of trades"). Neighbouring trades on the same day stay together.

3. moving_block_bootstrap_mean — overlapping contiguous blocks of `block_len`
   observations in chronological order (the 288-bar method used in E8–E11).
   Documented for series (bars), not for the G2 trade-day rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from evaluation.constants import DAY_BLOCK_BOOT_SAMPLES, DAY_BLOCK_BOOT_SEED, IID_TRADE_BOOT_SAMPLES, IID_TRADE_BOOT_SEED


def iid_trade_bootstrap_mean(r: np.ndarray, n_samples: int = IID_TRADE_BOOT_SAMPLES,
                             seed: int = IID_TRADE_BOOT_SEED) -> dict:
    """Percentile CI of the mean, resampling trades i.i.d. (E12)."""
    r = np.asarray(r, dtype=float)
    if len(r) < 2:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_mean_le_0": float("nan"), "n_samples": n_samples, "seed": seed, "method": "iid_trade"}
    rng = np.random.default_rng(seed)
    means = r[rng.integers(0, len(r), size=(n_samples, len(r)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(r.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "p_mean_le_0": float((means <= 0).mean()),
        "n_samples": n_samples, "seed": seed, "method": "iid_trade",
    }


def day_cluster_bootstrap_mean(trades: pd.DataFrame, value_col: str = "net_pnl_r",
                               time_col: str = "signal_time",
                               n_samples: int = DAY_BLOCK_BOOT_SAMPLES,
                               seed: int = DAY_BLOCK_BOOT_SEED) -> dict:
    """Resample calendar days of trades with replacement (G2).

    Each day-block is the vector of trade R on that signal-time calendar date
    (server date). Days are drawn with replacement and concatenated; the mean
    of the concatenated series is one bootstrap replicate. Empty days do not
    appear. This preserves intra-day dependence and is the pre-registered G2 CI.
    """
    t = trades.copy()
    t[time_col] = pd.to_datetime(t[time_col])
    t["day"] = t[time_col].dt.strftime("%Y-%m-%d")
    days = t["day"].unique()
    groups = [t.loc[t["day"] == d, value_col].to_numpy(float) for d in days]
    n_days = len(groups)
    values = t[value_col].to_numpy(float)
    if n_days < 2 or len(values) < 2:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_mean_le_0": float("nan"), "n_samples": n_samples, "seed": seed,
                "method": "day_cluster", "n_days": n_days}
    rng = np.random.default_rng(seed)
    means = np.empty(n_samples)
    for i in range(n_samples):
        pick = rng.integers(0, n_days, size=n_days)
        concat = np.concatenate([groups[j] for j in pick])
        means[i] = concat.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(values.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "p_mean_le_0": float((means <= 0).mean()),
        "n_samples": n_samples, "seed": seed, "method": "day_cluster", "n_days": n_days,
    }


def moving_block_bootstrap_mean(values: np.ndarray, block_len: int, n_samples: int = 1000,
                                seed: int = 42) -> dict:
    """Overlapping moving-block bootstrap of a chronological series (E8–E11 style)."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < block_len + 1:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_mean_le_0": float("nan"), "n_samples": n_samples, "seed": seed,
                "method": "moving_block", "block_len": block_len}
    rng = np.random.default_rng(seed)
    n_blocks = -(-n // block_len)
    starts = rng.integers(0, n - block_len + 1, size=(n_samples, n_blocks))
    idx = (starts[:, :, None] + np.arange(block_len)).reshape(n_samples, -1)[:, :n]
    means = values[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(values.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "p_mean_le_0": float((means <= 0).mean()),
        "n_samples": n_samples, "seed": seed, "method": "moving_block", "block_len": block_len,
    }
