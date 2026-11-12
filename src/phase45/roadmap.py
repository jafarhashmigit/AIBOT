"""Prioritized 3–5 milestones — information & decision quality over model complexity."""

from __future__ import annotations

from typing import Any

from phase45.constants import PHASE44_VALIDATION_DATES_LOCKED
from phase45.progress import write_json


def build_roadmap() -> dict[str, Any]:
    milestones = [
        {
            "id": "M1",
            "title": "Costed EV label & evaluation substrate",
            "problem": "Discovery targets mid-returns; trading needs bid/ask net R after costs.",
            "why_profitability": "Aligns optimization with money; stops false-positive directional screens.",
            "implementation": (
                "Define frozen outcome: next-bar entry ASK/BID, path TP/SL/timeout, net_R; "
                "primary metric E[net_R], secondary P(net_R>0), calibration curves. "
                "No new MT5 downloads; use Phase43 discovery dates only."
            ),
            "dependencies": ["Phase43 discovery dates", "existing tick paths"],
            "success_criteria": [
                "EV label recomputable independently with hash-locked definition",
                "Baseline random/trigger policies report costed EV on discovery with CIs",
            ],
            "failure_criteria": ["Any use of Phase44 validation dates for discovery", "Silent mid-price fills"],
            "compute": "CPU hours: low–moderate (tick path replay on 15 discovery dates)",
            "needs_new_independent_data": False,
        },
        {
            "id": "M2",
            "title": "Calibrated decision head + intelligent WAIT",
            "problem": "Binary triggers without P(success) or EV≤0 → WAIT policy.",
            "why_profitability": "Avoids negative-EV trades; WAIT becomes value-preserving.",
            "implementation": (
                "Train simple calibrated classifier/regressor ONLY on discovery for P(net_R>0) or E[net_R]; "
                "freeze; optional one-shot check later on a NEW held-out set (not Phase44 val). "
                "No NN/RL required."
            ),
            "dependencies": ["M1"],
            "success_criteria": [
                "Reliability diagram on discovery with ECE reported",
                "Policy: trade iff E[net_R] > stress_cost else WAIT",
                "Policy EV ≥ baseline trigger EV on discovery (pre-registered)",
            ],
            "failure_criteria": ["Tuning on Phase44 validation dates", "Uncalibrated probability claims"],
            "compute": "Low",
            "needs_new_independent_data": False,
        },
        {
            "id": "M3",
            "title": "Feature ontology reset (non-indicator-first)",
            "problem": "Repeated EMA/RSI/ATR/z families exhaust information.",
            "why_profitability": "Only new independent information can create new edges.",
            "implementation": (
                "Freeze ≤5 feature groups: (1) edge-to-spread ratio, (2) regime-state persistence, "
                "(3) familiarity/OOD distance to discovery manifold, (4) session-structure acceptance, "
                "(5) vol-time progress to 1R. Ban oscillator permutations as 'new hyps'."
            ),
            "dependencies": ["M1"],
            "success_criteria": [
                "Each feature group has causal definition + leakage tests",
                "Ablation shows incremental costed-EV information vs Phase25 baseline features",
            ],
            "failure_criteria": ["Cosmetic renames of Phase42/44 hyps", "Lookahead in regime labels"],
            "compute": "Low–moderate",
            "needs_new_independent_data": False,
        },
        {
            "id": "M4",
            "title": "Bounded AGENT_SHADOW learning loop",
            "problem": "AGENT_SHADOW empty; system does not learn from agent decisions.",
            "why_profitability": "Closes sim-to-decision gap; detects policy failure in live-like context.",
            "implementation": (
                "Shadow-only: log decision, features, EV, rationale; mature outcomes offline; "
                "update calibration freeze-versions only. No broker orders. Keep HISTORICAL_HYPOTHETICAL separate."
            ),
            "dependencies": ["M1", "M2"],
            "success_criteria": [
                "N>=100 matured shadow decisions with intact attribution",
                "Measurable calibration update protocol with version hash",
                "Stores never merged",
            ],
            "failure_criteria": ["Any order_send", "Merging experience stores", "Unversioned policy edits"],
            "compute": "Low ongoing",
            "needs_new_independent_data": False,
        },
        {
            "id": "M5",
            "title": "Preregistered independent confirmation (new dates only)",
            "problem": "Phase44 validation dates must stay closed; need true OOS when a policy finally passes M1–M4.",
            "why_profitability": "Prevents false discovery; only path to INDEPENDENT_VALIDATION_READY for a policy.",
            "implementation": (
                "Only after M1–M4 gates: acquire/select NEW unseen dates (exposure registry), "
                "freeze policy hash, one-shot evaluate. Do not run if discovery EV fails."
            ),
            "dependencies": ["M1", "M2", "M3", "M4", "Phase43 exposure methodology"],
            "success_criteria": [
                "One-shot costed EV>0 with Bonferroni/block bootstrap on new dates",
                "Drawdown and stress gates pass",
            ],
            "failure_criteria": ["Opening Phase44 validation for discovery", "Retuning after peeking"],
            "compute": "Moderate (new tick acquisition if needed)",
            "needs_new_independent_data": True,
            "forbidden_dates": PHASE44_VALIDATION_DATES_LOCKED,
        },
    ]
    payload = {
        "n_milestones": len(milestones),
        "milestones": milestones,
        "priority_order": ["M1", "M2", "M3", "M4", "M5"],
        "anti_pattern": "Do not schedule phases that only test more indicator combinations on mid-return labels.",
        "champion_remains": "NO_MODEL",
        "production_remains": "WAIT",
    }
    write_json("strategic_roadmap.json", payload)
    return payload
