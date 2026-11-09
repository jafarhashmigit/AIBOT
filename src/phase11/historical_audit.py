"""Independent audit of HISTORICAL_HYPOTHETICAL. Does not regenerate outcomes."""

from __future__ import annotations

from phase10.constants import SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_store import HistoricalExperienceStore
from phase10.validation import is_visible
from phase11.validation import (
    EXPECTED_HIST_BUY,
    EXPECTED_HIST_SELL,
    EXPECTED_HIST_SKIPPED,
    EXPECTED_HISTORICAL,
    ValidationError,
    historical_records,
)


OUTCOME_ON_DECISION = (
    "actual_net_r", "outcome_end", "exit_reason", "realized_pnl",
    "simulated_realized_r",
)


def audit_historical(store: HistoricalExperienceStore, *, as_of: str, skipped: int) -> dict:
    rows = historical_records(store)
    visible = store.query(as_of)
    ids = [r.experience_id for r in rows]
    sources = {r.source_type for r in rows}
    sides = [r.decision.side for r in rows]
    provenances = {r.decision.provenance for r in rows}
    statuses = {r.outcome.outcome_status for r in rows}
    prefixes = {rid.split(":", 1)[0] for rid in ids}
    decision_has_outcome = []
    future = []
    described_as_paper = []
    for rec in rows:
        mapping = rec.decision.to_mapping()
        for key in OUTCOME_ON_DECISION:
            if key in mapping:
                decision_has_outcome.append(rec.experience_id)
        note = rec.to_mapping().get("note", "")
        if "paper" in note.lower() and "not" not in note.lower():
            described_as_paper.append(rec.experience_id)
        if not is_visible(rec.outcome_end, as_of):
            future.append(rec.experience_id)
        if rec.outcome_end >= rec.decision.decision_timestamp and not (
            rec.outcome_end > rec.decision.decision_timestamp
        ):
            future.append(rec.experience_id)

    n_buy = sides.count("BUY")
    n_sell = sides.count("SELL")
    unique = len(ids) == len(set(ids))
    defects = []
    if sources != {SOURCE_HISTORICAL}:
        defects.append("source_type")
    if SOURCE_PAPER in sources or "paper" in prefixes:
        defects.append("cross_source_id")
    if not unique:
        defects.append("duplicate_id")
    if n_buy != EXPECTED_HIST_BUY or n_sell != EXPECTED_HIST_SELL:
        defects.append("side_counts")
    if len(rows) != EXPECTED_HISTORICAL:
        defects.append("record_count")
    if skipped != EXPECTED_HIST_SKIPPED:
        defects.append("skipped_count")
    if statuses != {"completed"}:
        defects.append("outcome_status")
    if "" in provenances or None in provenances:
        defects.append("provenance")
    if decision_has_outcome:
        defects.append("outcome_on_decision")
    if len(visible) != len(rows):
        defects.append("incomplete_in_completed_store")
    if any(r.outcome_end >= as_of for r in rows):
        defects.append("future_exposed")

    passed = not defects
    if not passed:
        raise ValidationError(f"HARD FAILURE: historical audit defects {defects}")

    return {
        "passed": True,
        "source_type": SOURCE_HISTORICAL,
        "record_count": len(rows),
        "buy_count": n_buy,
        "sell_count": n_sell,
        "skipped_incomplete": skipped,
        "unique_ids": unique,
        "provenances": sorted(provenances),
        "outcome_statuses": sorted(statuses),
        "visible_at_as_of": len(visible),
        "as_of": as_of,
        "note": "HISTORICAL_HYPOTHETICAL — not agent paper trades",
        "reconciled_with_phase10": True,
        "defects": defects,
    }
