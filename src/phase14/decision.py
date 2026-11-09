"""Candidate decision under predeclared Phase 14 confirmatory criteria."""

from __future__ import annotations

from phase14.constants import (
    CHAMPION_STATUS,
    MIN_DAYS,
    MIN_FOLD_N,
    MIN_H1_COVERAGE,
    MIN_POOLED_N,
    PHASE13_REPORTED_N,
)


def decide_candidate(
    *,
    replication: dict,
    walk_forward: dict,
    cost: dict,
    stats: dict,
    sufficiency: dict,
    h1_coverage: float,
) -> dict:
    checks = {}

    checks["replication_exact"] = bool(replication.get("exact_economic_match"))
    checks["replication_n_226"] = replication.get("n_independent") == PHASE13_REPORTED_N
    checks["h1_coverage"] = h1_coverage >= MIN_H1_COVERAGE
    checks["pooled_n"] = walk_forward["pooled"]["n"] >= MIN_POOLED_N
    checks["days"] = walk_forward["pooled"]["n_days"] >= MIN_DAYS

    fold_ok = True
    fold_detail = {}
    for fid, block in walk_forward["folds"].items():
        positive = block["n"] >= MIN_FOLD_N and block["mean_r"] == block["mean_r"] and block["mean_r"] > 0
        fold_detail[fid] = {
            "n": block["n"],
            "mean_r": block["mean_r"],
            "passes": positive,
        }
        if not positive:
            fold_ok = False
    checks["all_wf_windows_positive"] = fold_ok

    cost_ok = True
    for key in ("1x", "1.25x", "1.5x"):
        cell = cost.get(key)
        ok = cell is not None and cell["mean_r_positive"]
        checks[f"cost_{key}"] = ok
        if not ok:
            cost_ok = False
    checks["cost_robust_1_0_1_25_1_5"] = cost_ok

    ci_low = stats["bootstrap"]["ci_low"]
    checks["ci_lower_gt_0"] = ci_low == ci_low and ci_low > 0
    checks["p_mean_le_0_lt_0_05"] = stats["bootstrap"]["p_mean_le_0"] < 0.05
    checks["sample_sufficient_flag"] = bool(sufficiency.get("sufficient_for_confirmation", False))

    confirmatory_pass = all([
        checks["replication_exact"],
        checks["replication_n_226"],
        checks["h1_coverage"],
        checks["pooled_n"],
        checks["days"],
        checks["all_wf_windows_positive"],
        checks["cost_robust_1_0_1_25_1_5"],
        checks["ci_lower_gt_0"],
        checks["p_mean_le_0_lt_0_05"],
        checks["sample_sufficient_flag"],
    ])

    if confirmatory_pass:
        status = "READY_FOR_CONTROLLED_PAPER_RESEARCH"
        rationale = "All confirmatory criteria passed. Still not production; champion unchanged."
    elif checks["replication_exact"] and walk_forward["pooled"]["mean_r"] == walk_forward["pooled"]["mean_r"]:
        # Reproducible but gate incomplete
        if walk_forward["pooled"]["mean_r"] <= 0 and stats["bootstrap"]["ci_high"] <= 0:
            status = "REJECTED"
            rationale = "Reproducible but confirmatory evidence is clearly non-positive."
        else:
            status = "RETAINED_EXPERIMENTAL"
            rationale = (
                "Independent reconstruction reproduces Phase 13, but confirmatory gate fails "
                "(typically a negative walk-forward window and/or CI including 0)."
            )
    elif not checks["replication_exact"]:
        status = "REJECTED"
        rationale = "Independent reconstruction does not match the Phase 13 trade set; investigate before any research use."
    else:
        status = "REJECTED"
        rationale = "Confirmatory evidence insufficient."

    return {
        "candidate_id": "H13_C_H1_PULLBACK",
        "status": status,
        "champion_status": CHAMPION_STATUS,
        "buy_sell_authorized": False,
        "stage_b_authorized": False,
        "production_promotion": False,
        "checks": checks,
        "fold_detail": fold_detail,
        "rationale": rationale,
    }
