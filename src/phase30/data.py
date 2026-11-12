"""Approved historical research data for Phase 30 (no holdout)."""

from __future__ import annotations

from phase25.data import fold_counts as _fold_counts
from phase25.data import load_research_bundle
from phase30.constants import HOLDOUT_NAME, MAX_DECISION_TIME_UTC, RESEARCH_CUTOFF_UTC


def load_bundle() -> dict:
    """Reuse Phase 25 approved loader; never opens holdout."""
    bundle = load_research_bundle()
    assert HOLDOUT_NAME not in str(bundle.get("bounds", {}))
    assert bundle["bounds"].get("holdout_opened") is False
    assert bundle["bounds"]["research_cutoff"] == RESEARCH_CUTOFF_UTC
    assert all(t <= MAX_DECISION_TIME_UTC for t in bundle["timestamps"])
    return bundle


def fold_counts(bundle_or_timestamps) -> dict[str, int]:
    if isinstance(bundle_or_timestamps, dict):
        return _fold_counts(bundle_or_timestamps["timestamps"])
    return _fold_counts(bundle_or_timestamps)


__all__ = ["load_bundle", "fold_counts"]
