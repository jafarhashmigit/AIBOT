"""Prompt 7 independent strategy discovery — exploratory only; no promotion."""

from signal_bot.discovery.audit import build_research_audit
from signal_bot.discovery.candidates import preregistered_candidates, select_candidate
from signal_bot.discovery.constants import (
    CHAMPION_STATUS,
    VERDICT_INSUFFICIENT_DATA,
)
from signal_bot.discovery.data_feasibility import build_data_feasibility
from signal_bot.discovery.evaluation import (
    build_statistical_evaluation,
    dual_experience_architecture_note,
)

__all__ = [
    "build_research_audit",
    "build_data_feasibility",
    "preregistered_candidates",
    "select_candidate",
    "build_statistical_evaluation",
    "dual_experience_architecture_note",
    "CHAMPION_STATUS",
    "VERDICT_INSUFFICIENT_DATA",
]
