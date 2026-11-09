"""Part A research evidence inventory. No scoring."""

from __future__ import annotations


def research_inventory() -> dict:
    return {
        "tested_hypotheses": [
            {
                "id": "P1_RF_BASELINE",
                "phase": 1,
                "result": "REJECTED",
                "why": "Validation trades losing after costs; task not Phase 2 side-outcome comparable",
            },
            {
                "id": "P2_E1_MAX_PRED_R",
                "phase": 2,
                "result": "REJECTED",
                "why": "OOS mean R −0.021; negative on WF1/WF2/WF3; CI includes 0",
            },
            {
                "id": "P3_CONSERVATIVE_EV",
                "phase": 3,
                "result": "REJECTED",
                "why": "Frozen to Always WAIT; refusal is not an edge",
            },
            {
                "id": "P3_META_RIDGE",
                "phase": 3,
                "result": "REJECTED",
                "why": "Inner positive; outer mean R negative / CI includes 0",
            },
            {
                "id": "P4_NY_SELL_SLICE",
                "phase": 4,
                "result": "PROMISING_UNCONFIRMED",
                "why": "Both outer folds positive but CI includes 0 and FDR failed",
            },
            {
                "id": "P5_NY_SELL_REPLICATION",
                "phase": 5,
                "result": "REJECTED",
                "why": "Independent sample CI entirely below 0; 0/3 blocks positive",
            },
            {
                "id": "P7_AGENT_WAIT_GATE",
                "phase": 7,
                "result": "NO_EDGE",
                "why": "Architecture validated; WAIT-only after gate; E1/Direction lose",
            },
            {
                "id": "P9_EXPERIENCE_RIDGE",
                "phase": 9,
                "result": "REJECTED",
                "why": "Did not improve OOS decision quality vs Phase 6",
            },
            {
                "id": "P10_11_DUAL_SOURCE",
                "phase": "10-11",
                "result": "NO_MODEL",
                "why": "Stores validated; paper completed outcomes = 0; no combined learner",
            },
        ],
        "do_not_repeat_without_improvement": [
            "Unconditional corrected-NY SELL",
            "Raw E1 without additional pre-registered filters",
            "Phase 3 META_RIDGE retune on same decision features",
            "Combined HISTORICAL_HYPOTHETICAL + AGENT_PAPER learner",
        ],
        "insufficient_evidence_families": [
            "Economic calendar overlays (research CSV exists; no confirmatory economic gate)",
            "Kronos forecast overlays (exploratory only)",
            "Macro FX basket features (exploratory only)",
        ],
        "underinvestigated_conditions": [
            "Volatility-contraction breakout-failure structure",
            "Joint volatility-expansion + EMA-stack continuation with train-only cuts",
            "Closed H1 trend context for M5 pullbacks",
            "Prediction conviction-gap + mid-vol filter (distinct from E1)",
        ],
        "sample_sufficiency": {
            "oos_span": "Phase 2 WF1–WF3 ~ 2026-06-19 → 2026-09-29 17:50",
            "oos_timestamps": 18234,
            "assessment": (
                "Adequate to reject fragile rules; underpowered for confirming small edges. "
                "H1 history is longer, but M5 labeled OOS is short."
            ),
            "more_independent_m5_history_needed_for_confirmation": True,
        },
    }
