"""Phase45 final verdict selection."""

from __future__ import annotations

from typing import Any


def decide_verdict(
    *,
    taxonomy: dict[str, Any],
    learning: dict[str, Any],
    data: dict[str, Any],
    gaps: dict[str, Any],
) -> dict[str, Any]:
    """
    Choose among:
    ARCHITECTURE_READY
    MAJOR_RESEARCH_GAPS_IDENTIFIED
    DATA_LIMITATIONS_BLOCK_RESEARCH
    LEARNING_ARCHITECTURE_NOT_GENUINELY_ADAPTIVE
    RESEARCH_PROGRAM_REDIRECT_REQUIRED
    """
    data_blocks = bool(data.get("data_blocks_research"))
    adaptive = bool(learning.get("genuinely_adaptive"))

    if data_blocks:
        return {
            "final_verdict": "DATA_LIMITATIONS_BLOCK_RESEARCH",
            "reason": "Data integrity/coverage still blocks meaningful research",
            "primary_root_cause": taxonomy.get("primary_root_cause"),
        }

    # Data is ready (Phase43) but learning not adaptive and decision/target gaps dominate
    # RESEARCH_PROGRAM_REDIRECT_REQUIRED is the strongest accurate program-level call:
    # stop indicator-permutation research; redirect to EV/calibration/shadow learning.
    if not adaptive:
        return {
            "final_verdict": "RESEARCH_PROGRAM_REDIRECT_REQUIRED",
            "reason": (
                "After 44 phases, data readiness is no longer the binding constraint, yet no credible edge exists. "
                "Root causes are target misalignment, incomplete decision stack, non-adaptive learning, and "
                "stagnant feature ontology. Continue indicator-family screens would waste independent data. "
                "Also: LEARNING_ARCHITECTURE_NOT_GENUINELY_ADAPTIVE (AGENT_SHADOW empty; no policy updates)."
            ),
            "also_true": [
                "LEARNING_ARCHITECTURE_NOT_GENUINELY_ADAPTIVE",
                "MAJOR_RESEARCH_GAPS_IDENTIFIED",
            ],
            "primary_root_cause": taxonomy.get("primary_root_cause"),
            "redirect_to_milestones": ["M1", "M2", "M3", "M4", "M5"],
            "gaps": [g["gap_id"] for g in (gaps.get("gaps") or [])],
        }

    return {
        "final_verdict": "MAJOR_RESEARCH_GAPS_IDENTIFIED",
        "reason": "Architecture incomplete",
        "primary_root_cause": taxonomy.get("primary_root_cause"),
    }
