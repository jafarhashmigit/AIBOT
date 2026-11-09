"""Independent audit of AGENT_PAPER. Zero trades is honest, not a failure."""

from __future__ import annotations

from phase10.constants import SOURCE_PAPER
from phase10.paper_store import PaperExperienceStore
from phase11.validation import (
    EXPECTED_PAPER_DECISIONS,
    EXPECTED_PAPER_OUTCOMES,
    EXPECTED_PAPER_TRADES,
    ValidationError,
    paper_decisions,
)


def audit_paper(store: PaperExperienceStore, *, as_of: str) -> dict:
    decisions = paper_decisions(store)
    ids = [d.decision_id for d in decisions]
    sources = {d.source_type for d in decisions}
    stamps = [d.decision_timestamp for d in decisions]
    ordered = stamps == sorted(stamps)
    unique = len(ids) == len(set(ids))
    prefixes = {i.split(":", 1)[0] for i in ids}
    wait_as_trade = 0
    blocked_as_trade = 0
    outcome_on_decision = 0
    for d in decisions:
        mapping = d.to_mapping()
        for key in ("simulated_realized_r", "simulated_exit_price", "actual_net_r", "outcome_end"):
            if key in mapping:
                outcome_on_decision += 1
        if d.final_action == "WAIT" and d.decision_id in store._trade_by_decision:
            wait_as_trade += 1
        if d.risk_gate_result == "BLOCK" and d.decision_id in store._trade_by_decision:
            blocked_as_trade += 1

    completed = store.query_completed(as_of)
    n_trades = store.trade_count()
    n_outcomes = len(store._outcomes)
    fabricated_prices = 0
    for trade in store._trades.values():
        if trade.provenance == "fabricated":
            fabricated_prices += 1

    defects = []
    if sources and sources != {SOURCE_PAPER}:
        defects.append("source_type")
    if "hist" in prefixes:
        defects.append("cross_source_id")
    if not unique:
        defects.append("duplicate_id")
    if not ordered:
        defects.append("timestamp_order")
    if len(decisions) != EXPECTED_PAPER_DECISIONS:
        defects.append("decision_count")
    if n_trades != EXPECTED_PAPER_TRADES:
        defects.append("trade_count")
    if n_outcomes != EXPECTED_PAPER_OUTCOMES or len(completed) != EXPECTED_PAPER_OUTCOMES:
        defects.append("outcome_count")
    if wait_as_trade or blocked_as_trade:
        defects.append("wait_or_block_as_trade")
    if outcome_on_decision:
        defects.append("outcome_on_decision")
    if fabricated_prices:
        defects.append("fabricated_prices")
    for oid in store._outcomes:
        if oid not in store._trades:
            defects.append("outcome_without_trade")

    passed = not defects
    if not passed:
        raise ValidationError(f"HARD FAILURE: paper audit defects {defects}")

    raw = {"BUY": 0, "SELL": 0, "WAIT": 0}
    final = {"BUY": 0, "SELL": 0, "WAIT": 0}
    gate = {"ALLOW": 0, "BLOCK": 0}
    for d in decisions:
        raw[d.raw_proposed_action] = raw.get(d.raw_proposed_action, 0) + 1
        final[d.final_action] = final.get(d.final_action, 0) + 1
        gate[d.risk_gate_result] = gate.get(d.risk_gate_result, 0) + 1

    return {
        "passed": True,
        "source_type": SOURCE_PAPER,
        "decision_count": len(decisions),
        "trade_count": n_trades,
        "completed_outcomes": len(completed),
        "unique_ids": unique,
        "timestamps_ordered": ordered,
        "raw_proposed_action": raw,
        "final_action": final,
        "risk_gate": gate,
        "wait_treated_as_trade": wait_as_trade,
        "blocked_treated_as_trade": blocked_as_trade,
        "zero_trades_is_honest_state": n_trades == 0,
        "as_of": as_of,
        "note": "zero completed paper trades is expected under WAIT-only RiskGate",
        "defects": defects,
    }
