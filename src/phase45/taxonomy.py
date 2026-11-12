"""Research failure taxonomy — why 44 phases did not yield a validated edge."""

from __future__ import annotations

from typing import Any

from phase45.progress import write_json


def build_failure_taxonomy() -> dict[str, Any]:
    taxonomy = [
        {
            "id": "F1_TARGET_MISALIGNMENT",
            "name": "Prediction target ≠ tradable EV",
            "severity": "HIGH",
            "description": (
                "Screens optimize directional/ATR mid-returns or rule triggers; trading requires "
                "costed bid/ask net R. Positive mid-effect can coexist with negative trade EV."
            ),
            "evidence_phases": ["phase39", "phase41", "phase42", "phase44"],
        },
        {
            "id": "F2_FEATURE_ONTOLOGY_STAGNATION",
            "name": "Repeated conventional indicator families",
            "severity": "HIGH",
            "description": (
                "EMA/RSI/ATR/z-score/session variants recur from Phase14–44. Phase42/44 new wrappers "
                "still rest on similar microstructure. Little new independent information."
            ),
            "evidence_phases": ["phase14", "phase25", "phase35", "phase42", "phase44"],
        },
        {
            "id": "F3_NON_ADAPTIVE_AGENT",
            "name": "No genuine experience→policy learning loop",
            "severity": "HIGH",
            "description": (
                "AGENT_SHADOW empty in Phase42/44; HISTORICAL_HYPOTHETICAL is post-hoc logging. "
                "System does not improve decisions from accumulated experience."
            ),
            "evidence_phases": ["phase42", "phase44", "phase16a", "phase20"],
        },
        {
            "id": "F4_DECISION_STACK_INCOMPLETE",
            "name": "Missing calibrated EV and intelligent WAIT",
            "severity": "HIGH",
            "description": "Pipeline jumps from features/triggers to actions without calibrated P and EV-under-cost.",
            "evidence_phases": ["phase25", "phase39", "phase44"],
        },
        {
            "id": "F5_DATA_WAS_BINDING_THEN_SOLVED",
            "name": "Earlier phases blocked by data; later phases not blocked",
            "severity": "MEDIUM_HISTORICAL",
            "description": (
                "Phases 33–40 largely spent establishing bid/ask/MT5 coverage. Phase43 removed the "
                "independent-data blocker; Phase44 still found no edge — data no longer primary constraint."
            ),
            "evidence_phases": ["phase36", "phase37", "phase38", "phase39", "phase40", "phase43", "phase44"],
        },
        {
            "id": "F6_DUPLICATE_EXPERIMENTATION",
            "name": "Retesting same candidates under better data",
            "severity": "MEDIUM",
            "description": "H13_C and mean_reversion re-evaluated across many phases until retirement; diminishing information.",
            "evidence_phases": ["phase35", "phase36", "phase39", "phase41"],
        },
        {
            "id": "F7_SAMPLE_BRITTLENESS",
            "name": "Sparse events / unstable effects under proper multiple testing",
            "severity": "MEDIUM",
            "description": "Several Phase44 hyps showed positive point estimates but failed n/Bonferroni/LODO — correct rejects.",
            "evidence_phases": ["phase42", "phase44"],
        },
        {
            "id": "F8_DEMO_EXECUTION_CEILING",
            "name": "Demo microstructure ceiling",
            "severity": "MEDIUM",
            "description": "Cannot claim live edge from MetaQuotes-Demo spreads; microstructure hyps especially fragile.",
            "evidence_phases": ["phase37", "phase41", "phase44"],
        },
    ]
    payload = {
        "n_categories": len(taxonomy),
        "taxonomy": taxonomy,
        "primary_root_cause": "F1_TARGET_MISALIGNMENT + F3_NON_ADAPTIVE_AGENT + F4_DECISION_STACK_INCOMPLETE",
        "secondary_root_cause": "F2_FEATURE_ONTOLOGY_STAGNATION after data blockers cleared (F5)",
        "note": "Do not weaken statistical thresholds; they correctly prevented false positives.",
    }
    write_json("research_failure_taxonomy.json", payload)
    return payload
