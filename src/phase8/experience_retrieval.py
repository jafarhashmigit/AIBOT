"""Deterministic retrieval wrapper. Same store + T → same summary."""

from __future__ import annotations

from phase8.experience_schema import ExperienceSummary
from phase8.experience_store import ExperienceStore


def retrieve(store: ExperienceStore, decision_time: str) -> tuple[list, ExperienceSummary]:
    rows = store.query(decision_time)
    summary = store.summary(decision_time)
    return rows, summary


def summaries_equal(a: ExperienceSummary, b: ExperienceSummary) -> bool:
    return a.to_mapping() == b.to_mapping()
