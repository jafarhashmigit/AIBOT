"""Research audit of Phase39–57.1 — facts only, no new edge claims."""

from __future__ import annotations

from typing import Any

from phase58.constants import DO_NOT_REPEAT, canonical_json_sha256


def build_research_audit() -> dict[str, Any]:
    audit = {
        "scope": "Phase39–57.1 research history for Phase58",
        "standing_policy": {"champion": "NO_MODEL", "production": "WAIT"},
        "tested_families": [
            {"phase": 39, "ids": ["H13_C", "mean_reversion"], "verdict": "INSUFFICIENT_EVIDENCE"},
            {"phase": 41, "ids": ["H13_C", "mean_reversion"], "verdict": "EDGE_REJECTED / INSUFFICIENT"},
            {"phase": 42, "ids": [f"H42_{x}" for x in "ABCDEFGHIJ"], "verdict": "NO_PREDICTIVE_VALUE"},
            {"phase": 44, "ids": [f"H44_{i}" for i in range(1, 6)], "verdict": "NO_PREDICTIVE_VALUE"},
            {"phase": 47, "ids": ["13feat_calibrated_EV"], "verdict": "EV_ESTIMATION_UNRELIABLE"},
            {"phase": 49, "ids": ["H_A1-3", "H_B1-3", "H_C1-3", "H_D1-3", "H_E1-3", "H_F1-3"], "verdict": "NO_INFORMATION_FAMILY_FOUND"},
            {"phase": 50, "ids": ["shrink_bucket_hist_learning"], "verdict": "NO_DEMONSTRATED_LEARNING_VALUE"},
            {"phase": 51, "ids": ["frozen_shrink_bucket_v1"], "verdict": "INDEPENDENT_CONFIRMATION_FAILED"},
            {"phase": 53, "ids": ["F1_CMC", "F2_EXF", "F3_SLF"], "verdict": "NO_EDGE_FOUND"},
        ],
        "failed_why": [
            "Bonferroni date-block bootstrap CIs include zero (P49/P53)",
            "Insufficient trades / events (multiple H42/H44/F2)",
            "Sign flips under LODO / validation",
            "Learning incremental CI includes zero vs WAIT (P50); confirmation failed (P51)",
            "Overlapping H12 labels + weak features (P47/P48)",
        ],
        "do_not_repeat": list(DO_NOT_REPEAT),
        "insufficient_evidence_gaps": [
            "Phase49 C04 prior-day range never tested (calendar prior missing)",
            "AGENT_SHADOW largely empty through P50/P51; paper shadow now exists via P54–57.1 but not as validated learner",
            "Sealed confirmation dates remain unused for scoring until a survivor exists",
        ],
        "genuine_opportunities_non_duplicative": [
            {
                "id": "prior_archived_session_location",
                "note": "Previous archived session range location — not calendar-1 C04; not F1/F2/F3",
            },
            {
                "id": "costly_spread_wait_gate",
                "note": "WAIT when spread/ATR elevated vs constant-side baseline — not H44 tight-spread persistence",
            },
            {
                "id": "inactivity_wait",
                "note": "Low tick-activity → WAIT opportunity-cost study — not directional momentum",
            },
            {
                "id": "dual_experience_retest_with_shadow",
                "note": "Re-evaluate learning only as measurement; do not revive shrink_bucket_v1 as champion",
            },
        ],
        "agent_reliability_status": {
            "phase56": "AUTONOMOUS_REPLAY_AGENT_READY",
            "phase57": "AUTONOMOUS_RELIABILITY_PARTIAL",
            "phase57_1": "DURABLE_EXPERIENCE_RECOVERY_VALIDATED",
        },
        "recommendation": (
            "Preregister only non-duplicative H58_* families; keep NullPolicy production default; "
            "champion remains NO_MODEL unless Bonferroni date-block gates pass and holdout confirms."
        ),
    }
    audit["audit_sha256"] = canonical_json_sha256({k: v for k, v in audit.items() if k != "audit_sha256"})
    return audit
