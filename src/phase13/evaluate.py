"""Economic validation for Phase 13 decisions. Synthetic scoring of historical outcomes only."""

from __future__ import annotations

import math

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate
from phase13.constants import (
    BOOTSTRAP_DRAWS,
    FDR_Q,
    FOLDS,
    HYPOTHESIS_IDS,
    MIN_FOLD_TRADES,
    MIN_H1_COVERAGE,
    MIN_POOLED_TRADES,
    SEED,
    SPREAD_FLOOR_USD,
)
from phase13.data_loader import fold_of


def _stress_r(net_r: float, initial_risk: float, mult: float) -> float:
    if initial_risk <= 0:
        return float("nan")
    return net_r - (mult - 1.0) * SPREAD_FLOOR_USD / initial_risk


def score_policy(bundle: dict, decisions: dict[str, str], *, label: str) -> dict:
    trades = []
    waits = 0
    missing_outcome = 0
    by_fold = {fid: [] for fid in FOLDS}
    by_side = {"BUY": [], "SELL": []}
    for t, action in decisions.items():
        if action == "WAIT":
            waits += 1
            continue
        outcome = bundle["outcomes"].get((t, action))
        if outcome is None:
            missing_outcome += 1
            continue
        fold_id = fold_of(t)
        row = {
            "decision_time": t,
            "side": action,
            "fold_id": fold_id,
            "net_r": outcome["net_r"],
            "net_pnl": outcome["net_pnl"],
            "initial_risk": outcome["initial_risk"],
            "net_r_1_5x": _stress_r(outcome["net_r"], outcome["initial_risk"], 1.5),
            "net_r_2_0x": _stress_r(outcome["net_r"], outcome["initial_risk"], 2.0),
        }
        trades.append(row)
        by_fold[fold_id].append(row)
        by_side[action].append(row)

    def _block(rows: list[dict]) -> dict:
        if not rows:
            return {
                "n": 0,
                "mean_r": float("nan"),
                "net_r": 0.0,
                "net_usd": 0.0,
                "profit_factor": float("nan"),
                "win_rate": float("nan"),
                "max_drawdown_usd": 0.0,
                "bootstrap": {
                    "mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                    "p_mean_le_0": float("nan"), "n_days": 0,
                },
            }
        r = np.asarray([x["net_r"] for x in rows], dtype=float)
        pnl = np.asarray([x["net_pnl"] for x in rows], dtype=float)
        times = [x["decision_time"] for x in rows]
        boot = day_cluster_bootstrap_mean(times, r, n_samples=BOOTSTRAP_DRAWS, seed=SEED)
        return {
            "n": int(len(rows)),
            "mean_r": float(r.mean()),
            "net_r": float(r.sum()),
            "net_usd": float(pnl.sum()),
            "profit_factor": float(profit_factor(r)),
            "win_rate": float(win_rate(r)),
            "max_drawdown_usd": float(max_drawdown(pnl)),
            "bootstrap": boot,
        }

    pooled = _block(trades)
    folds = {fid: _block(rows) for fid, rows in by_fold.items()}
    sides = {side: _block(rows) for side, rows in by_side.items()}

    stress = {}
    for name, key in (("1.5x", "net_r_1_5x"), ("2.0x", "net_r_2_0x")):
        vals = np.asarray([x[key] for x in trades if x[key] == x[key]], dtype=float)
        stress[name] = {
            "n": int(len(vals)),
            "mean_r": float(vals.mean()) if len(vals) else float("nan"),
        }

    fold_means = []
    for fid, block in folds.items():
        if block["n"] >= MIN_FOLD_TRADES:
            fold_means.append(block["mean_r"] > 0)
    majority_folds_positive = (
        sum(1 for x in fold_means if x) >= math.ceil(len(fold_means) / 2)
        if fold_means else False
    )
    all_active_folds_positive = all(fold_means) if fold_means else False

    return {
        "policy_id": label,
        "n_decisions": len(decisions),
        "n_wait": waits,
        "n_trades": pooled["n"],
        "missing_outcome": missing_outcome,
        "pooled": pooled,
        "folds": folds,
        "sides": sides,
        "cost_stress": stress,
        "majority_folds_positive": majority_folds_positive,
        "all_active_folds_positive": all_active_folds_positive,
        "buy_count": sides["BUY"]["n"],
        "sell_count": sides["SELL"]["n"],
    }


def bh_fdr(p_values: list[tuple[str, float]], q: float = FDR_Q) -> dict:
    eligible = [(k, p) for k, p in p_values if p == p]
    m = len(eligible)
    if m == 0:
        return {"q": q, "m": 0, "discoveries": [], "ranked": []}
    order = sorted(range(m), key=lambda i: eligible[i][1])
    ranked = []
    discoveries = []
    max_i = -1
    for rank, idx in enumerate(order, start=1):
        key, p = eligible[idx]
        thresh = q * rank / m
        passed = p <= thresh
        ranked.append({"id": key, "p": p, "rank": rank, "threshold": thresh, "pass": passed})
        if passed:
            max_i = rank
    if max_i >= 0:
        discoveries = [ranked[i]["id"] for i in range(max_i)]
        # BH: all with rank <= max passing rank
        discoveries = [r["id"] for r in ranked if r["rank"] <= max_i]
    return {"q": q, "m": m, "discoveries": discoveries, "ranked": ranked}


def assign_status(score: dict, *, fdr_pass: bool, sensitivity_ok: bool, h1_coverage_ok: bool) -> dict:
    pooled = score["pooled"]
    n = pooled["n"]
    mean_r = pooled["mean_r"]
    ci_low = pooled["bootstrap"]["ci_low"]
    stress_ok = score["cost_stress"]["1.5x"]["mean_r"] == score["cost_stress"]["1.5x"]["mean_r"] and \
        score["cost_stress"]["1.5x"]["mean_r"] > 0
    pf = pooled["profit_factor"]
    pf_ok = pf == pf and pf >= 1.0

    hard_reject_reasons = []
    if n < MIN_POOLED_TRADES:
        hard_reject_reasons.append("insufficient_trades")
    if not (mean_r == mean_r) or mean_r <= 0:
        hard_reject_reasons.append("non_positive_mean_r")
    if not score["all_active_folds_positive"]:
        hard_reject_reasons.append("not_all_active_folds_positive")
    if not (ci_low == ci_low) or ci_low <= 0:
        hard_reject_reasons.append("ci_lower_not_above_zero")
    if not fdr_pass:
        hard_reject_reasons.append("fdr_fail")
    if not stress_ok:
        hard_reject_reasons.append("cost_stress_fail")
    if not pf_ok:
        hard_reject_reasons.append("profit_factor_below_one")
    if not sensitivity_ok:
        hard_reject_reasons.append("sensitivity_sign_mismatch")
    if not h1_coverage_ok and score["policy_id"] == "H13_C_H1_PULLBACK":
        hard_reject_reasons.append("h1_coverage_below_threshold")

    if not hard_reject_reasons:
        status = "VALIDATED_CANDIDATE"
    elif (
        n >= MIN_POOLED_TRADES
        and mean_r == mean_r
        and mean_r > 0
        and score["majority_folds_positive"]
        and sensitivity_ok
        and (score["policy_id"] != "H13_C_H1_PULLBACK" or h1_coverage_ok)
    ):
        # Interesting but incomplete gate → EXPERIMENTAL only if not clearly FDR/CI dead
        status = "EXPERIMENTAL"
        hard_reject_reasons.append("gate_incomplete_experimental_only")
    else:
        status = "REJECTED"

    return {
        "status": status,
        "reasons": hard_reject_reasons,
        "fdr_pass": fdr_pass,
        "sensitivity_ok": sensitivity_ok,
        "h1_coverage_ok": h1_coverage_ok,
        "gate": {
            "min_pooled_trades": MIN_POOLED_TRADES,
            "require_ci_lower_gt_0": True,
            "require_all_active_folds_positive": True,
            "fdr_q": FDR_Q,
            "cost_stress_1_5x_mean_r_gt_0": True,
        },
    }


def evaluate_all(bundle: dict, generated: dict) -> dict:
    decisions = generated["decisions"]
    scores = {}
    for pid, dec in decisions.items():
        scores[pid] = score_policy(bundle, dec, label=pid)

    # Sensitivity for H13_A: same sign of pooled mean R when both trade enough
    a = scores["H13_A_BREAKOUT_FAILURE"]
    s = scores["H13_A_SENS_L8"]
    if a["n_trades"] >= MIN_POOLED_TRADES and s["n_trades"] >= MIN_POOLED_TRADES:
        sensitivity_ok = (a["pooled"]["mean_r"] > 0) == (s["pooled"]["mean_r"] > 0)
    else:
        # If primary lacks trades, sensitivity cannot rescue it; mark ok so reason stays sample size
        sensitivity_ok = True

    h1_ok = generated["h1_coverage"] >= MIN_H1_COVERAGE

    pvals = []
    for hid in HYPOTHESIS_IDS:
        p = scores[hid]["pooled"]["bootstrap"]["p_mean_le_0"]
        pvals.append((hid, p))
    fdr = bh_fdr(pvals)
    discoveries = set(fdr["discoveries"])

    registry = []
    for hid in HYPOTHESIS_IDS:
        sens = sensitivity_ok if hid == "H13_A_BREAKOUT_FAILURE" else True
        cov = h1_ok if hid == "H13_C_H1_PULLBACK" else True
        assignment = assign_status(
            scores[hid],
            fdr_pass=hid in discoveries,
            sensitivity_ok=sens,
            h1_coverage_ok=cov,
        )
        registry.append({
            "candidate_id": hid,
            "status": assignment["status"],
            "assignment": assignment,
            "score_summary": {
                "n_trades": scores[hid]["n_trades"],
                "mean_r": scores[hid]["pooled"]["mean_r"],
                "net_usd": scores[hid]["pooled"]["net_usd"],
                "profit_factor": scores[hid]["pooled"]["profit_factor"],
                "win_rate": scores[hid]["pooled"]["win_rate"],
                "max_drawdown_usd": scores[hid]["pooled"]["max_drawdown_usd"],
                "ci": [
                    scores[hid]["pooled"]["bootstrap"]["ci_low"],
                    scores[hid]["pooled"]["bootstrap"]["ci_high"],
                ],
                "p_mean_le_0": scores[hid]["pooled"]["bootstrap"]["p_mean_le_0"],
                "cost_stress_1_5x_mean_r": scores[hid]["cost_stress"]["1.5x"]["mean_r"],
                "folds": {
                    fid: {"n": scores[hid]["folds"][fid]["n"], "mean_r": scores[hid]["folds"][fid]["mean_r"]}
                    for fid in FOLDS
                },
            },
        })

    return {
        "scores": scores,
        "fdr": fdr,
        "registry": registry,
        "h1_coverage": generated["h1_coverage"],
        "cuts_by_fold": generated["cuts_by_fold"],
        "sensitivity_ok_h13_a": sensitivity_ok,
    }
