"""Source-specific descriptive summaries. Not used for optimization or edge claims."""

from __future__ import annotations

import math

import numpy as np

from phase3.nplib import profit_factor
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_store import PaperExperienceStore
from phase11.validation import historical_records, paper_decisions

LABEL = "DESCRIPTIVE — NOT USED FOR OPTIMIZATION; NOT AN EDGE CLAIM"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2)


def _finite_or_none(value: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return float(value)


def historical_performance(store: HistoricalExperienceStore) -> dict:
    rows = historical_records(store)
    buy = [r for r in rows if r.decision.side == "BUY"]
    sell = [r for r in rows if r.decision.side == "SELL"]
    r_all = [r.outcome.actual_net_r for r in rows]
    reasons: dict[str, int] = {}
    for rec in rows:
        reasons[rec.outcome.exit_reason] = reasons.get(rec.outcome.exit_reason, 0) + 1
    stamps = [r.decision.decision_timestamp for r in rows]
    ends = [r.outcome_end for r in rows]
    pf = profit_factor(np.asarray(r_all, dtype=float)) if r_all else float("nan")
    return {
        "source_type": "HISTORICAL_HYPOTHETICAL",
        "completed_BUY": len(buy),
        "completed_SELL": len(sell),
        "completed_total": len(rows),
        "exit_reason_distribution": dict(sorted(reasons.items())),
        "mean_net_r": (sum(r_all) / len(r_all)) if r_all else None,
        "median_net_r": _median(r_all),
        "profit_factor": _finite_or_none(float(pf)) if r_all else None,
        "profit_factor_raw": float(pf) if r_all else None,
        "chronological_coverage": {
            "earliest_decision": min(stamps) if stamps else None,
            "latest_decision": max(stamps) if stamps else None,
            "earliest_outcome_end": min(ends) if ends else None,
            "latest_outcome_end": max(ends) if ends else None,
        },
        "missing_incomplete_in_store": 0,
        "incomplete_excluded_from_phase10_load": 26,
        "note": LABEL,
        "not_equivalent_to_paper": True,
    }


def paper_performance(store: PaperExperienceStore, *, as_of: str) -> dict:
    decisions = paper_decisions(store)
    raw = {"BUY": 0, "SELL": 0, "WAIT": 0}
    final = {"BUY": 0, "SELL": 0, "WAIT": 0}
    gate = {"ALLOW": 0, "BLOCK": 0}
    for d in decisions:
        raw[d.raw_proposed_action] = raw.get(d.raw_proposed_action, 0) + 1
        final[d.final_action] = final.get(d.final_action, 0) + 1
        gate[d.risk_gate_result] = gate.get(d.risk_gate_result, 0) + 1
    completed = store.query_completed(as_of)
    has_outcomes = len(completed) > 0
    stamps = [d.decision_timestamp for d in decisions]
    return {
        "source_type": "AGENT_PAPER",
        "total_decisions": len(decisions),
        "raw_proposed_BUY": raw["BUY"],
        "raw_proposed_SELL": raw["SELL"],
        "raw_proposed_WAIT": raw["WAIT"],
        "final_BUY": final["BUY"],
        "final_SELL": final["SELL"],
        "final_WAIT": final["WAIT"],
        "gate_ALLOW": gate["ALLOW"],
        "gate_BLOCK": gate["BLOCK"],
        "completed_paper_trades": store.trade_count(),
        "completed_paper_outcomes": len(completed),
        "mean_net_r": None if not has_outcomes else float(
            sum(row["outcome"]["simulated_realized_r"] for row in completed) / len(completed)
        ),
        "median_net_r": None,
        "profit_factor": None,
        "win_rate": None,
        "metrics_status": "unavailable" if not has_outcomes else "computed",
        "chronological_coverage": {
            "earliest_decision": min(stamps) if stamps else None,
            "latest_decision": max(stamps) if stamps else None,
        },
        "note": LABEL,
        "unavailable_not_replaced_with_zero": not has_outcomes,
        "not_equivalent_to_historical": True,
    }


def separate_summaries(
    historical: HistoricalExperienceStore,
    paper: PaperExperienceStore,
    *,
    as_of: str,
) -> dict:
    return {
        "historical": historical_performance(historical),
        "paper": paper_performance(paper, as_of=as_of),
        "compared_as_equivalent_populations": False,
        "label": LABEL,
    }
