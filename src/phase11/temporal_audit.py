"""As-of retrieval audit for each source independently."""

from __future__ import annotations

from phase10.constants import MAX_ACCESS_TIMESTAMP
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_store import PaperExperienceStore
from phase10.validation import is_visible, outcome_end_for
from phase11.validation import ValidationError, historical_records, paper_decisions


def _as_of_cases(decision_times: list[str]) -> list[str]:
    first = decision_times[0]
    mid = decision_times[len(decision_times) // 2]
    last = decision_times[-1]
    first_end = outcome_end_for(first)
    return [first, first_end, mid, last, MAX_ACCESS_TIMESTAMP]


def audit_temporal(
    historical: HistoricalExperienceStore,
    paper: PaperExperienceStore,
    *,
    as_of: str,
) -> dict:
    hist_rows = historical_records(historical)
    hist_times = [r.decision.decision_timestamp for r in hist_rows]
    cases = _as_of_cases(hist_times)
    hist_checks = []
    for t in cases:
        visible = historical.query(t)
        n_expected = sum(1 for r in hist_rows if is_visible(r.outcome_end, t))
        equal_leaked = any(r.outcome_end == t for r in visible)
        future_leaked = any(r.outcome_end >= t for r in visible)
        hist_checks.append({
            "as_of": t,
            "visible": len(visible),
            "expected": n_expected,
            "equal_timestamp_excluded": not equal_leaked,
            "future_excluded": not future_leaked,
            "match": len(visible) == n_expected and not equal_leaked and not future_leaked,
        })

    paper_completed_at_as_of = paper.query_completed(as_of)
    paper_checks = {
        "as_of": as_of,
        "completed_visible": len(paper_completed_at_as_of),
        "expected": 0,
        "incomplete_excluded": paper.trade_count() == 0 and len(paper_completed_at_as_of) == 0,
        "decisions_have_no_outcome_keys": True,
    }
    for d in paper_decisions(paper):
        mapping = d.to_mapping()
        if any(k in mapping for k in ("actual_net_r", "simulated_realized_r", "outcome_end")):
            paper_checks["decisions_have_no_outcome_keys"] = False

    hist_ok = all(c["match"] for c in hist_checks)
    # equal-timestamp case: first_end as_of must exclude records whose end == first_end
    equal_case = hist_checks[1]
    paper_ok = (
        paper_checks["completed_visible"] == 0
        and paper_checks["incomplete_excluded"]
        and paper_checks["decisions_have_no_outcome_keys"]
    )
    passed = hist_ok and paper_ok and equal_case["equal_timestamp_excluded"]
    if not passed:
        raise ValidationError("HARD FAILURE: temporal availability audit")

    return {
        "passed": True,
        "boundary": "outcome_end < as_of_timestamp",
        "historical_cases": hist_checks,
        "paper": paper_checks,
        "equal_timestamp_unavailable": True,
        "incomplete_excluded": True,
        "future_excluded": True,
        "no_backdating_enforced_by_stores": True,
        "max_as_of": as_of,
    }
