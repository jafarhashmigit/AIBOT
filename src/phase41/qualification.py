"""Candidate verdicts — adversarial; no production promotion."""

from __future__ import annotations

from typing import Any

from phase41.constants import (
    MIN_INDEPENDENT_DATES_FOR_CONFIRM,
    MIN_RESOLVED_FOR_ANY_CLAIM,
    MIN_RESOLVED_TRADES_FOR_CONFIRM,
)


def verdict_for_candidate(result: dict[str, Any], *, indep_ok: bool) -> dict[str, Any]:
    s = result.get("summary") or {}
    boot = result.get("bootstrap") or {}
    lodo = result.get("leave_one_date_out") or {}
    n_scored = int(s.get("n_scored") or 0)
    n_dates = int(result.get("n_independent_dates_with_scores") or 0)
    n_cov = int(s.get("n_insufficient_coverage") or 0)
    mean_r = s.get("mean_r")
    n_signals = int(s.get("n_signals") or 0)
    pf = s.get("profit_factor")
    max_dd = s.get("max_dd_r")

    if not indep_ok:
        return {
            "verdict": "EXECUTION_MODEL_BLOCKED",
            "reason": "independent reconstruction mismatch",
        }

    if n_signals == 0:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "zero BUY/SELL signals on Phase40 full-session corpus",
        }

    if n_scored < MIN_RESOLVED_FOR_ANY_CLAIM:
        extra = ""
        if mean_r is not None:
            extra = f"; exploratory_mean_r={mean_r:.4f} (not a confirmatory claim)"
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": (
                f"scored_trades={n_scored} < {MIN_RESOLVED_FOR_ANY_CLAIM}; "
                f"insufficient_coverage={n_cov}; independent_dates={n_dates}{extra}"
            ),
            "merits_larger_independent_validation": False,
        }

    stress_ok = True
    base_scenario = next(
        (
            sc
            for sc in (result.get("scenarios") or [])
            if sc.get("slippage_per_side") == 0.1
            and sc.get("commission_per_side") == 0.05
            and sc.get("spread_widen_mult") == 1.5
        ),
        None,
    )
    if base_scenario and (base_scenario.get("mean_scenario_net_r") or 0) <= 0:
        stress_ok = False

    if mean_r is not None and mean_r <= 0:
        return {
            "verdict": "EDGE_REJECTED",
            "reason": (
                f"observed mean net R={mean_r:.4f} <= 0 under bid/ask fills "
                f"(pf={pf}, max_dd_r={max_dd}, dates={n_dates})"
            ),
        }

    # Positive mean alone is not enough
    survives_stats = bool(boot.get("ci95_excludes_zero")) and bool(boot.get("bonferroni_ci_excludes_zero"))
    lodo_stable = bool(lodo.get("all_folds_positive")) and not bool(lodo.get("sign_flip_count"))
    # sign_flip_count==0 and all positive means all folds same sign positive; all_folds_positive covers it
    lodo_ok = bool(lodo.get("ok")) and bool(lodo.get("all_folds_positive"))

    if (
        mean_r is not None
        and mean_r > 0
        and n_scored >= MIN_RESOLVED_TRADES_FOR_CONFIRM
        and n_dates >= MIN_INDEPENDENT_DATES_FOR_CONFIRM
        and survives_stats
        and stress_ok
        and not boot.get("dependent_on_one_date")
        and lodo_ok
        and pf is not None
        and pf > 1.0
    ):
        return {
            "verdict": "PROMISING_BUT_UNCONFIRMED",
            "reason": (
                "passes exploratory confirmatory bars on previously examined dates; "
                "NOT independent OOS; no production promotion"
            ),
            "merits_larger_independent_validation": True,
        }

    if mean_r is not None and mean_r > 0:
        return {
            "verdict": "PROMISING_BUT_UNCONFIRMED",
            "reason": (
                f"positive mean_r={mean_r:.4f} but insufficient confirmatory evidence "
                f"(scored={n_scored}, dates={n_dates}, ci95_excludes_0={boot.get('ci95_excludes_zero')}, "
                f"bonferroni_excludes_0={boot.get('bonferroni_ci_excludes_zero')}, "
                f"stress_ok={stress_ok}, lodo_all_pos={lodo.get('all_folds_positive')}, "
                f"dependent_one_date={boot.get('dependent_on_one_date')}, pf={pf})"
            ),
            "merits_larger_independent_validation": bool(
                n_scored >= MIN_RESOLVED_TRADES_FOR_CONFIRM
                and n_dates >= 5
                and stress_ok
                and not boot.get("dependent_on_one_date")
            ),
        }

    return {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "reason": "unable to confirm or reject with available Phase40 sample",
        "merits_larger_independent_validation": False,
    }
