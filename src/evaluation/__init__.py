"""Shared evaluation framework (Phase 1).

Public surface:
    splits, metrics, bootstrap, permutation, costs, gates, integrity, report.

Historical reproduction helpers live in evaluation.reproduce.
"""

from evaluation.constants import DEFAULT_SEED, EXPECTED_WF_WINDOWS, G2, RESEARCH_CUTOFF

__all__ = [
    "DEFAULT_SEED",
    "EXPECTED_WF_WINDOWS",
    "G2",
    "RESEARCH_CUTOFF",
]
