"""Replication gates — do not weaken post-hoc."""

from __future__ import annotations

from typing import Any

from phase36.constants import (
    MIN_COMPLETE_DAYS_FOR_REPLICATION,
    MIN_RESOLVED_TRADES_FOR_REPLICATION,
)
from phase36.progress import write_json


def apply_gates(
    *,
    n_complete_days: int,
    evaluation: dict[str, Any],
    bootstrap: dict[str, Any],
    indep_cmp: dict[str, Any],
) -> dict[str, Any]:
    summary = evaluation.get("view_a_bidask") or {}
    stress = evaluation.get("view_c_stress_extra_005") or {}
    n_resolved = int(summary.get("n_resolved") or 0)
    mean_r = summary.get("mean_r")
    stress_mean = stress.get("mean_r")

    gates = {
        "min_10_complete_independent_dates": n_complete_days >= MIN_COMPLETE_DAYS_FOR_REPLICATION,
        "min_100_resolved_trades": n_resolved >= MIN_RESOLVED_TRADES_FOR_REPLICATION,
        "net_positive_after_bidask": mean_r is not None and mean_r > 0,
        "ci95_excludes_zero": bool(bootstrap.get("ci95_excludes_zero")),
        "not_dependent_on_one_exceptional_day": not bool(bootstrap.get("dependent_on_one_exceptional_day")),
        "chrono_not_materially_unstable": _chrono_ok(evaluation.get("chronological") or {}),
        "buy_sell_not_materially_unstable": _side_ok(evaluation),
        "stress_extra_005_still_positive": stress_mean is not None and stress_mean > 0,
        "independent_recompute_match": bool(indep_cmp.get("ok")),
    }
    failed = [k for k, v in gates.items() if not v]

    if n_complete_days < MIN_COMPLETE_DAYS_FOR_REPLICATION:
        verdict = "INSUFFICIENT_DATA"
    elif not gates["independent_recompute_match"]:
        verdict = "REPLICATION_FAILED"
    elif not failed:
        verdict = "INDEPENDENT_REPLICATION_CONFIRMED"
    elif gates["net_positive_after_bidask"] and gates["min_100_resolved_trades"] and n_complete_days >= 5:
        verdict = "PROMISING_BUT_UNCONFIRMED"
    elif mean_r is not None and mean_r <= 0 and n_resolved >= 30:
        verdict = "REPLICATION_FAILED"
    elif n_complete_days < MIN_COMPLETE_DAYS_FOR_REPLICATION or n_resolved < 30:
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "REPLICATION_FAILED"

    report = {
        "gates": gates,
        "failed_gates": failed,
        "final_verdict": verdict,
        "n_complete_days": n_complete_days,
        "n_resolved": n_resolved,
        "mean_r": mean_r,
        "stress_mean_r": stress_mean,
        "ci95": [bootstrap.get("ci95_low"), bootstrap.get("ci95_high")],
        "note": "Gates are minimum research criteria, not proof of future profitability.",
    }
    write_json("qualification.json", report)
    return report


def _chrono_ok(chrono: dict[str, Any]) -> bool:
    means = []
    for g in chrono.values():
        s = g.get("summary") or {}
        if s.get("n_resolved", 0) >= 5 and s.get("mean_r") is not None:
            means.append(float(s["mean_r"]))
    if len(means) < 2:
        return False
    # Material instability: mixed signs across groups with enough trades
    pos = sum(1 for m in means if m > 0)
    neg = sum(1 for m in means if m <= 0)
    return not (pos > 0 and neg > 0 and abs(max(means) - min(means)) > 0.5)


def _side_ok(evaluation: dict[str, Any]) -> bool:
    b = evaluation.get("buy_summary") or {}
    s = evaluation.get("sell_summary") or {}
    bm, sm = b.get("mean_r"), s.get("mean_r")
    bn, sn = int(b.get("n_resolved") or 0), int(s.get("n_resolved") or 0)
    if bn < 10 or sn < 10 or bm is None or sm is None:
        # Not enough side evidence to fail; require both sides sampled for CONFIRM
        return bn >= 10 and sn >= 10
    # Fail if one side strongly positive and other strongly negative
    if bm > 0.2 and sm < -0.2:
        return False
    if sm > 0.2 and bm < -0.2:
        return False
    return True
