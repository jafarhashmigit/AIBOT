"""Candidate verdicts — attempt to disprove; no promotion."""

from __future__ import annotations

from typing import Any

from phase39.constants import (
    MIN_INDEPENDENT_DATES_FOR_CONFIRM,
    MIN_RESOLVED_FOR_ANY_CLAIM,
    MIN_RESOLVED_TRADES_FOR_CONFIRM,
)


def verdict_for_candidate(result: dict[str, Any], *, indep_ok: bool) -> dict[str, Any]:
    s = result.get("summary") or {}
    boot = result.get("bootstrap") or {}
    n_scored = int(s.get("n_scored") or 0)
    n_dates = int(result.get("n_independent_dates_with_scores") or 0)
    n_cov = int(s.get("n_insufficient_coverage") or 0)
    mean_r = s.get("mean_r")
    n_signals = int(s.get("n_signals") or 0)

    if not indep_ok:
        return {
            "verdict": "EXECUTION_MODEL_BLOCKED",
            "reason": "independent reconstruction mismatch",
        }

    # Structural impossibility / almost no evaluable trades
    if n_signals == 0:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "zero signals on Phase38 corpus (often missing H1 context for H13_C)",
        }
    if n_scored < MIN_RESOLVED_FOR_ANY_CLAIM:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": (
                f"scored_trades={n_scored} < {MIN_RESOLVED_FOR_ANY_CLAIM}; "
                f"insufficient_coverage={n_cov}; independent_dates={n_dates}. "
                "Phase38 tick windows are only 12:00–15:00 UTC on 10 dates."
            ),
        }

    # Enough to discuss but not confirm
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
            "reason": f"observed mean net R={mean_r:.4f} <= 0 under bid/ask fills (adverse for ambiguous)",
        }

    if (
        mean_r is not None
        and mean_r > 0
        and n_scored >= MIN_RESOLVED_TRADES_FOR_CONFIRM
        and n_dates >= MIN_INDEPENDENT_DATES_FOR_CONFIRM
        and boot.get("ci95_excludes_zero")
        and stress_ok
        and not boot.get("dependent_on_one_date")
    ):
        # Still do not promote in Phase39 — mark promising only
        return {
            "verdict": "PROMISING_BUT_UNCONFIRMED",
            "reason": "passes internal bars but Phase39 forbids promotion; treat as hypothesis only",
        }

    if mean_r is not None and mean_r > 0:
        return {
            "verdict": "PROMISING_BUT_UNCONFIRMED",
            "reason": (
                f"positive mean_r={mean_r:.4f} but insufficient confirmatory sample "
                f"(scored={n_scored}, dates={n_dates}, ci_excludes_0={boot.get('ci95_excludes_zero')})"
            ),
        }

    return {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "reason": "unable to confirm or reject with available Phase38 sample",
    }
