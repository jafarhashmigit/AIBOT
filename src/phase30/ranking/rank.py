"""Research ranking / gates (NOT production)."""

from __future__ import annotations

import math
from typing import Any

from phase30.constants import (
    CHAMPION_STATUS,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_GATES,
    VALID_STATUSES,
    VALID_VERDICTS,
)


def _finite(x: Any) -> bool:
    try:
        return x is not None and x == x and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _gt0(x: Any) -> bool:
    return _finite(x) and float(x) > 0


def classify_strategy(
    *,
    strategy_id: str,
    metrics: dict[str, Any],
    robustness: dict[str, Any] | None,
    h13c_mean_r: float,
    n_strategies_tested: int,
) -> dict[str, Any]:
    pooled = metrics["score"]["pooled"]
    cost = metrics["cost_robustness"]
    n = int(pooled["n"])
    mean_r = pooled["mean_r"]
    ci_high = pooled["bootstrap"]["ci_high"]
    ci_low = pooled["bootstrap"]["ci_low"]
    cost15 = (cost.get("1.5x") or {}).get("mean_r")

    gates = {
        "A_min_pooled_n": n >= int(RESEARCH_GATES["min_pooled_n"]),
        "B_mean_r_gt_0": _gt0(mean_r),
        "C_ci_not_strongly_below_zero": _finite(ci_high) and float(ci_high) > 0,
        "D_fold_stability": bool(metrics["score"].get("all_active_folds_positive")),
        "E_cost_1_5x_mean_r_gt_0": _gt0(cost15),
        "F_param_robust": None,  # filled if robustness present
        "G_multiple_testing_aware": True,  # always apply penalty in ranking
    }
    if robustness and robustness.get("parameter_perturbation", {}).get("status") == "COMPLETED":
        gates["F_param_robust"] = bool(robustness["parameter_perturbation"].get("all_tested_positive"))
    else:
        gates["F_param_robust"] = False if robustness else None

    perm = (robustness or {}).get("permutation") or {}
    perm_ok = perm.get("status") == "COMPLETED" and _finite(perm.get("p_value_mean_r_ge_obs")) and float(
        perm["p_value_mean_r_ge_obs"]
    ) < 0.1

    # Status ladder (research only)
    if n < 20:
        status = "WEAK_UNCONFIRMED"
        why = "Too few trades for credible inference."
    elif not _gt0(mean_r):
        status = "REJECTED"
        why = "Non-positive pooled mean R after costs."
    elif not gates["C_ci_not_strongly_below_zero"]:
        status = "REJECTED"
        why = "Bootstrap CI does not support upside (ci_high <= 0)."
    else:
        core = [
            gates["A_min_pooled_n"],
            gates["B_mean_r_gt_0"],
            gates["C_ci_not_strongly_below_zero"],
            gates["D_fold_stability"],
            gates["E_cost_1_5x_mean_r_gt_0"],
        ]
        if all(core) and gates["F_param_robust"] is True and perm_ok:
            status = "RESEARCH_CANDIDATE"
            why = "Passed predeclared research gates including robustness/permutation."
        elif gates["B_mean_r_gt_0"] and (
            gates["D_fold_stability"] or gates["E_cost_1_5x_mean_r_gt_0"] or gates["A_min_pooled_n"]
        ):
            status = "PROMISING_BUT_UNCONFIRMED"
            why = "Positive expectancy but incomplete research-gate confirmation."
        elif gates["B_mean_r_gt_0"]:
            status = "WEAK_UNCONFIRMED"
            why = "Positive mean R without fold/cost/sample confirmation."
        else:
            status = "REJECTED"
            why = "Failed primary research gates."

    assert status in VALID_STATUSES
    beats_h13c = _gt0(mean_r) and _finite(h13c_mean_r) and float(mean_r) > float(h13c_mean_r)
    return {
        "strategy_id": strategy_id,
        "status": status,
        "rationale": why,
        "gates": gates,
        "permutation_p_lt_0_1": perm_ok,
        "beats_h13c_mean_r": beats_h13c,
        "n_strategies_tested": n_strategies_tested,
        "production_ready": False,
        "champion_unchanged": CHAMPION_STATUS,
        "h13c_unchanged": H13C_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
    }


def composite_rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transparent composite score — not mean-R alone."""
    ranked = []
    for r in rows:
        m = r["metrics"]
        pooled = m["score"]["pooled"]
        n = max(int(pooled["n"]), 0)
        mean_r = float(pooled["mean_r"]) if _finite(pooled["mean_r"]) else -999.0
        pf = float(pooled["profit_factor"]) if _finite(pooled["profit_factor"]) else 0.0
        dd = float(pooled["max_drawdown_usd"]) if _finite(pooled["max_drawdown_usd"]) else 0.0
        ci_low = float(pooled["bootstrap"]["ci_low"]) if _finite(pooled["bootstrap"]["ci_low"]) else -999.0
        fold_ok = 1.0 if m["score"].get("all_active_folds_positive") else 0.0
        n_term = min(n / 100.0, 2.0)
        dd_pen = min(abs(dd) / 50.0, 2.0)
        mt_pen = math.log(max(int(r["decision"]["n_strategies_tested"]), 1)) * 0.02
        rob = r.get("robustness") or {}
        param_ok = 1.0 if (rob.get("parameter_perturbation") or {}).get("all_tested_positive") else 0.0
        perm = rob.get("permutation") or {}
        perm_bonus = 0.0
        if perm.get("status") == "COMPLETED" and _finite(perm.get("p_value_mean_r_ge_obs")):
            p = float(perm["p_value_mean_r_ge_obs"])
            perm_bonus = max(0.0, 0.15 - p)
        score = (
            1.5 * mean_r
            + 0.15 * math.log1p(max(pf, 0.0))
            + 0.25 * fold_ok
            + 0.2 * n_term
            + 0.1 * max(ci_low, -1.0)
            + 0.2 * param_ok
            + perm_bonus
            - 0.15 * dd_pen
            - mt_pen
        )
        ranked.append({**r, "composite_score": score})
    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked


def multiple_testing_summary(decisions: dict[str, dict]) -> dict[str, Any]:
    n = len(decisions)
    counts = {s: 0 for s in VALID_STATUSES}
    for d in decisions.values():
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    return {
        "n_strategies_tested": n,
        "status_counts": counts,
        "note": (
            f"{n} predeclared strategies evaluated once (no iterative OOS retuning). "
            "Best raw mean R is not automatically a winner; composite rank + gates applied. "
            "Multiple-testing penalty included in composite score via log(n) term."
        ),
    }


def phase_verdict(decisions: dict[str, dict]) -> str:
    statuses = [d["status"] for d in decisions.values()]
    if any(s == "RESEARCH_CANDIDATE" for s in statuses):
        v = "RESEARCH_CANDIDATE_FOUND"
    elif any(s == "PROMISING_BUT_UNCONFIRMED" for s in statuses):
        v = "PROMISING_BUT_UNCONFIRMED"
    else:
        v = "NO_NEW_EDGE_FOUND"
    assert v in VALID_VERDICTS
    return v
