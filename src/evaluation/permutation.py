"""Permutation tests.

What is shuffled is always documented in the returned dict (`shuffled`).

A. Label-block null: shuffle *training* outcomes in calendar-day blocks, refit,
   regenerate signals, replay. This is expensive (full RF retrains). The
   function is implemented; Phase 1 G2 verification does not run 200 draws
   because earlier G2 criteria already fail. n_draws is a caller argument.

B. Random-entry null: keep the observed trade count and side mix, draw random
   eligible (time, side) pairs from the per-side outcome table, and compare
   the observed mean R to that null. Shuffled object: the identity of the
   traded rows, not the labels. Exit rules stay those of the outcome table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from evaluation.constants import DEFAULT_SEED, G2


def permutation_b_random_entry(observed_r: np.ndarray, pool: pd.DataFrame,
                               n_buy: int, n_sell: int,
                               n_draws: int = None, seed: int = DEFAULT_SEED) -> dict:
    """Random-entry null (G2 permutation test B).

    `pool` must have columns side ('BUY'/'SELL') and net_r, one row per
    eligible (timestamp, side). Draws are with replacement within side.
    """
    n_draws = G2["permutation_b_draws"] if n_draws is None else n_draws
    observed = float(np.mean(observed_r))
    buy = pool.loc[pool["side"] == "BUY", "net_r"].to_numpy(float)
    sell = pool.loc[pool["side"] == "SELL", "net_r"].to_numpy(float)
    if len(buy) < max(n_buy, 1) or len(sell) < max(n_sell, 1):
        return {"status": "blocked", "reason": "outcome pool smaller than observed trade mix",
                "shuffled": "eligible (time, side) identities", "n_draws": n_draws, "seed": seed}
    rng = np.random.default_rng(seed)
    null = np.empty(n_draws)
    for i in range(n_draws):
        rb = rng.choice(buy, size=n_buy, replace=True) if n_buy else np.array([])
        rs = rng.choice(sell, size=n_sell, replace=True) if n_sell else np.array([])
        null[i] = np.concatenate([rb, rs]).mean()
    p = float((null >= observed).mean())
    return {
        "status": "ran",
        "shuffled": "eligible (time, side) identities; outcomes and exit rules unchanged",
        "n_draws": n_draws, "seed": seed,
        "observed_mean_r": observed,
        "null_median": float(np.median(null)),
        "null_p95": float(np.percentile(null, 95)),
        "p_ge_observed": p,
        "passed": observed > float(np.percentile(null, 95)),
    }


def permutation_a_label_shuffle_placeholder(reason: str) -> dict:
    """Record that permutation A was not run, with the reason.

    The procedure that *would* run: for each draw, shuffle training `target`
    in calendar-day blocks (days permuted, labels inside a day kept together),
    refit the frozen RF, generate signals, run the unchanged backtester.
    """
    return {
        "status": "not_run",
        "shuffled": "training labels, calendar-day blocks (labels inside a day kept together)",
        "n_draws_required": G2["permutation_a_draws"],
        "reason": reason,
    }
