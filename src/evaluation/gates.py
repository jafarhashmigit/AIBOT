"""Pre-registered acceptance gates.

G2 thresholds are read from evaluation.constants.G2 / ACCEPTANCE_CRITERIA.md.
A criterion that was not run is recorded as status='not_run' and does not
count as a pass. The gate passes only if every required criterion that applies
to the candidate has status='pass'.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from evaluation.bootstrap import day_cluster_bootstrap_mean
from evaluation.constants import G2
from evaluation.metrics import closed_trade_metrics, profit_factor
from evaluation.permutation import permutation_a_label_shuffle_placeholder, permutation_b_random_entry
from research_rf_m5_model_comparison import profit_factor as pf


def _crit(name, passed, **info) -> dict:
    return {"name": name, "status": "pass" if passed else "fail", "passed": bool(passed), **info}


def evaluate_g2(trades: pd.DataFrame, *, window_col: str = "window",
                outcome_pool: pd.DataFrame | None = None,
                family_size: int = 1,
                run_permutation_a: bool = False,
                permutation_a_reason: str = "") -> dict:
    """Walk-forward economic gate G2.

    `trades` must contain net_pnl, net_pnl_r, side, signal_time, and `window_col`.
    Meta-model and neighbourhood criteria are marked not_applicable for a
    primary-only RF policy.
    """
    criteria = []
    windows = sorted(trades[window_col].unique())
    per = {w: closed_trade_metrics(trades[trades[window_col] == w]) for w in windows}
    pooled = closed_trade_metrics(trades)
    n_blocks = len(windows)

    # Minimum trade count
    per_ok = all(per[w]["trades"] >= G2["min_trades_per_block"] for w in windows)
    criteria.append(_crit("min_trade_count",
                          pooled["trades"] >= G2["min_pooled_trades"] and per_ok,
                          pooled_trades=int(pooled["trades"]),
                          per_block={w: int(per[w]["trades"]) for w in windows},
                          threshold_pooled=G2["min_pooled_trades"],
                          threshold_block=G2["min_trades_per_block"]))

    # Mean R
    mean_r = float(pooled["avg_r"])
    criteria.append(_crit("walk_forward_expected_r", mean_r >= G2["min_mean_r"],
                          value=mean_r, threshold=G2["min_mean_r"]))

    # Block consistency
    block_means = {w: float(per[w]["avg_r"]) for w in windows}
    n_pos = sum(v > 0 for v in block_means.values())
    need = G2["min_positive_blocks_3"] if n_blocks == 3 else int(np.ceil(G2["min_positive_blocks_frac"] * n_blocks))
    worst = min(block_means.values()) if block_means else float("nan")
    criteria.append(_crit("block_consistency",
                          n_pos >= need and worst >= G2["worst_block_r"],
                          block_mean_r=block_means, n_positive=n_pos, required_positive=need,
                          worst=worst, worst_threshold=G2["worst_block_r"]))

    # Profit factor (R units = using net_pnl_r as the P&L series, AND USD PF)
    pf_usd = float(pooled["profit_factor"])
    pf_r = float(pf(trades["net_pnl_r"])) if len(trades) else float("nan")
    block_pf = {w: float(per[w]["profit_factor"]) for w in windows}
    criteria.append(_crit("profit_factor",
                          pf_r >= G2["min_profit_factor"] and all(v >= G2["min_block_profit_factor"] or not np.isfinite(v)
                                                                   for v in block_pf.values()),
                          pooled_pf_r=pf_r, pooled_pf_usd=pf_usd, per_block_usd=block_pf,
                          threshold=G2["min_profit_factor"], block_floor=G2["min_block_profit_factor"],
                          note="G2 uses profit factor of net R; USD PF is reported alongside."))

    # Day-clustered bootstrap CI
    boot = day_cluster_bootstrap_mean(trades, n_samples=G2["bootstrap_samples"], seed=G2["bootstrap_seed"])
    criteria.append(_crit("confidence_interval",
                          boot["ci_low"] > G2["ci_lower_must_exceed"],
                          **boot, threshold=G2["ci_lower_must_exceed"]))
    criteria.append(_crit("bootstrap_tail",
                          boot["p_mean_le_0"] < G2["bootstrap_p_mean_le_0"],
                          p_mean_le_0=boot["p_mean_le_0"], threshold=G2["bootstrap_p_mean_le_0"]))

    # Permutation A
    if run_permutation_a:
        criteria.append({"name": "permutation_a_label_null", "status": "not_run",
                         "passed": False, "reason": "caller requested run but no retraining hook was supplied"})
    else:
        criteria.append({"name": "permutation_a_label_null",
                         **permutation_a_label_shuffle_placeholder(
                             permutation_a_reason or "not required once earlier G2 criteria fail; 200 RF retrains")})

    # Permutation B
    if outcome_pool is not None and len(trades):
        pb = permutation_b_random_entry(
            trades["net_pnl_r"].to_numpy(float), outcome_pool,
            n_buy=int((trades["side"] == "BUY").sum()),
            n_sell=int((trades["side"] == "SELL").sum()),
            n_draws=G2["permutation_b_draws"], seed=G2["bootstrap_seed"],
        )
        criteria.append({"name": "permutation_b_random_entry", **pb,
                         "passed": pb.get("passed", False),
                         "status": pb.get("status", "ran")})
    else:
        criteria.append({"name": "permutation_b_random_entry", "status": "not_run",
                         "passed": False, "reason": "no per-side outcome pool supplied"})

    # Multiple testing
    criteria.append(_crit("multiple_testing_fdr", family_size == 1,
                          family_size=family_size, q=G2["fdr_q"],
                          note="family_size=1: a single pre-registered baseline reproduction; BH-FDR is a no-op."))

    # Drawdown
    dd = float(pooled["max_drawdown_r"])
    total_r = float(pooled["total_r"])
    ratio = (total_r / dd) if dd > 0 else float("nan")
    criteria.append(_crit("drawdown",
                          dd <= G2["max_drawdown_r"] and (ratio >= G2["min_total_r_over_dd"] if np.isfinite(ratio) else False),
                          max_drawdown_r=dd, total_r=total_r, total_over_dd=ratio,
                          max_dd_threshold=G2["max_drawdown_r"], min_ratio=G2["min_total_r_over_dd"]))

    # Loss streak: reported, compared to a binomial reference only as a diagnostic.
    criteria.append({"name": "loss_streak", "status": "reported",
                     "passed": True, "longest_losing_streak": int(pooled["longest_losing_streak"]),
                     "note": "Full 99th-percentile simulation is a future diagnostic; Phase 1 records the streak."})

    # Meta-model N/A
    criteria.append({"name": "meta_model_value", "status": "not_applicable",
                     "passed": True, "reason": "RF baseline has no meta-model; WAIT is the argmax WAIT class."})

    # Concentration
    block_totals = {w: float(per[w]["total_r"]) for w in windows}
    abs_total = sum(abs(v) for v in block_totals.values()) or 1.0
    shares = {w: abs(block_totals[w]) / abs_total for w in windows}
    criteria.append(_crit("concentration_block",
                          all(s <= G2["max_block_r_share"] for s in shares.values()),
                          abs_r_share=shares, threshold=G2["max_block_r_share"]))

    # not_applicable / reported never decide the gate.
    # not_run blocks a pass (cannot promote a model without the test) but is
    # recorded separately from an executed fail.
    hard_fail = []
    incomplete = []
    for c in criteria:
        status = c.get("status")
        if status in ("not_applicable", "reported"):
            continue
        if status == "not_run":
            incomplete.append(c["name"])
            continue
        if status == "fail" or not c.get("passed"):
            hard_fail.append(c["name"])
    passed = not hard_fail and not incomplete
    economic = {
        "walk_forward_expected_r", "block_consistency", "profit_factor",
        "confidence_interval", "bootstrap_tail",
    }
    economic_failed = [n for n in hard_fail if n in economic]
    return {
        "gate": "G2",
        "passed": passed,
        "hard_fail": hard_fail,
        "incomplete": incomplete,
        "economic_failed": economic_failed,
        "pooled": pooled,
        "per_window": per,
        "criteria": criteria,
        "seed": G2["bootstrap_seed"],
        "configuration": {"windows": list(windows), "g2_thresholds": G2},
        "finding_class": "reproduction",
        "note": "Classification accuracy is not a G2 input; a majority-class beat cannot promote.",
    }
