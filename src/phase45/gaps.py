"""Architecture gap analysis synthesizing audits."""

from __future__ import annotations

from typing import Any

from phase45.progress import write_json


def build_gap_analysis(audits: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    gaps = [
        {
            "gap_id": "G1",
            "title": "No first-class costed EV objective",
            "maps_to": ["F1_TARGET_MISALIGNMENT", "F4_DECISION_STACK_INCOMPLETE"],
            "required_capability": "Predict E[net_R_bidask|x] and act iff EV > stress_cost",
        },
        {
            "gap_id": "G2",
            "title": "No calibrated probabilities",
            "maps_to": ["F4_DECISION_STACK_INCOMPLETE"],
            "required_capability": "Isotonic/Platt or histogram calibration on discovery; freeze before validation",
        },
        {
            "gap_id": "G3",
            "title": "No adaptive experience loop",
            "maps_to": ["F3_NON_ADAPTIVE_AGENT"],
            "required_capability": "AGENT_SHADOW decisions with matured outcomes updating calibration only under freeze discipline",
        },
        {
            "gap_id": "G4",
            "title": "Feature research still indicator-centric",
            "maps_to": ["F2_FEATURE_ONTOLOGY_STAGNATION"],
            "required_capability": "Cost-normalized, regime-state, and familiarity features; stop oscillator permutations",
        },
        {
            "gap_id": "G5",
            "title": "Intelligent WAIT missing",
            "maps_to": ["F4_DECISION_STACK_INCOMPLETE"],
            "required_capability": "OOD/familiarity score → forced WAIT when market state unseen",
        },
        {
            "gap_id": "G6",
            "title": "Portfolio exposure under-specified",
            "maps_to": ["F7_SAMPLE_BRITTLENESS"],
            "required_capability": "Non-overlap / max concurrent risk model in both research and shadow",
        },
    ]
    payload = {
        "gaps": gaps,
        "audits_referenced": sorted(audits.keys()),
        "primary_root_cause": taxonomy.get("primary_root_cause"),
        "what_success_is_not": "More phases that only permute indicators on the same labels",
        "what_success_is": "Close G1–G3 with measurable lift in costed EV and calibrated WAIT behavior",
    }
    write_json("architecture_gap_analysis.json", payload)
    return payload
