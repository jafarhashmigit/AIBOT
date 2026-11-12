"""Architecture audits — evidence-backed, no new strategy evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase45.constants import (
    PHASE44_VALIDATION_DATES_LOCKED,
    PROJECT_ROOT,
    REPORTS_ROOT,
    SRC_DIR,
)
from phase45.progress import write_json


def _exists(rel: str) -> bool:
    return (PROJECT_ROOT / rel).exists() or (SRC_DIR / rel.replace("src/", "", 1)).exists()


def audit_prediction_targets() -> dict[str, Any]:
    findings = [
        {
            "finding": "Dominant label is fixed-horizon mid/ATR return (H1/H3/H6/H12 bars), not costed expected trade return.",
            "evidence": [
                "src/phase42/labels.py",
                "src/phase44/labels.py",
                "src/phase39/execution.py",
            ],
            "impact": "Directional mid-return can look informative while bid/ask net R remains negative (Phase41 MR).",
        },
        {
            "finding": "Trade outcome labels (PASS/FAIL/TIMEOUT on TP/SL) are used in decision layers but rarely as primary discovery targets.",
            "evidence": ["src/phase41/execution.py", "src/phase44/evaluate.py"],
            "impact": "Discovery optimizes for predictive association; decision layer is a second filter — misalignment.",
        },
        {
            "finding": "WAIT is usually residual (no trigger), not an explicit EV-maximizing action.",
            "evidence": ["src/phase25/strategies/mean_reversion.py", "src/phase44/triggers.py"],
            "impact": "Agent cannot learn when NOT to trade from calibrated EV; WAIT is default, not intelligence.",
        },
        {
            "finding": "MFE/MAE and fav-before-adverse computed in places but not used as primary success criteria consistently.",
            "evidence": ["src/phase42/labels.py", "src/phase41/metrics.py"],
            "recommendation": "Prefer labels: net_R under bid/ask path, P(fav before adv), and calibrated P(edge>cost).",
        },
        {
            "finding": "Horizons are fixed bar counts, not volatility-time.",
            "evidence": ["src/phase44/constants.py HORIZONS", "src/phase39/constants.py HORIZON_BARS=12"],
            "recommendation": "Evaluate volatility-adjusted holding time (e.g., target 1R path time) as research milestone, without rewriting history.",
        },
    ]
    payload = {
        "audit": "prediction_targets",
        "findings": findings,
        "suitability_verdict": "CURRENT_LABELS_ARE_NOISY_AND_MISALIGNED_WITH_TRADE_EV",
        "math_note": (
            "If discovery maximizes E[sign(r_mid)*side] but trading maximizes E[(exit_bidask-entry_bidask)/risk - costs], "
            "the argmax policies differ whenever spread/slippage dominate signal magnitude."
        ),
    }
    write_json("audit_prediction_targets.json", payload)
    return payload


def audit_features() -> dict[str, Any]:
    findings = [
        {
            "category": "conventional_technical",
            "examples": ["EMA9/20/50", "RSI14", "ATR14", "z-score", "volatility ratios"],
            "evidence": ["src/phase35/features.py", "src/phase25/indicators.py", "src/phase39/features.py"],
            "assessment": "Heavily reused across phases; low incremental information after Phase25–41 failures.",
        },
        {
            "category": "structure_session",
            "examples": ["session flags", "prev-day levels", "sweeps", "range width"],
            "evidence": ["src/phase42/features.py", "src/phase44/features.py"],
            "assessment": "Useful ontology but event definitions brittle; Phase44 H44_1 produced 0 events on discovery.",
        },
        {
            "category": "microstructure",
            "examples": ["tick imbalance", "bar spread median"],
            "evidence": ["src/phase42/features.py", "src/phase44/features.py"],
            "assessment": "Demo quote dynamics ≠ live; Phase44 H44_5 had large n but negative effect.",
        },
        {
            "category": "missing",
            "examples": [
                "order-book depth (unavailable on demo ticks)",
                "explicit regime state machine with persistence",
                "cost-aware features (edge-to-spread ratio)",
                "uncertainty / familiarity scores for WAIT",
            ],
            "assessment": "Highest-value missing category is cost-normalized and regime-state features, not more oscillators.",
        },
        {
            "leakage_risks": [
                "Forming H1 candle if close_time not enforced (mitigated in phase35 h1_trend_at)",
                "Using validation outcomes during discovery (mitigated in phase44 process)",
                "Prev-day OHLC fallback from Phase40 for Phase44 features (context only; documented)",
            ],
            "evidence": ["src/phase35/features.py", "src/phase44/corpus.py", "src/phase44/run_phase44.py"],
        },
    ]
    payload = {"audit": "features", "findings": findings}
    write_json("audit_features.json", payload)
    return payload


def audit_learning() -> dict[str, Any]:
    p42 = REPORTS_ROOT / "phase42" / "experience_stores.json"
    p44 = REPORTS_ROOT / "phase44" / "experience_stores.json"
    p42_data = json.loads(p42.read_text(encoding="utf-8")) if p42.is_file() else {}
    p44_data = json.loads(p44.read_text(encoding="utf-8")) if p44.is_file() else {}
    shadow42 = (p42_data.get("AGENT_SHADOW") or {}).get("n_decisions")
    shadow44 = (p44_data.get("AGENT_SHADOW") or {}).get("n_decisions")

    findings = [
        {
            "store": "HISTORICAL_HYPOTHETICAL",
            "status": "PRESENT_AS_SUMMARY_ARTIFACTS",
            "evidence": [str(p42).replace("\\", "/"), str(p44).replace("\\", "/")],
            "assessment": (
                "Stores counterfactual trade summaries after evaluation. "
                "No online policy update, no contextual bandit, no experience replay that changes future decisions."
            ),
        },
        {
            "store": "AGENT_SHADOW",
            "status": "EMPTY",
            "n_decisions_phase42": shadow42,
            "n_decisions_phase44": shadow44,
            "evidence": [
                "reports/phase42/experience_stores.json",
                "reports/phase44/experience_stores.json",
                "src/phase16a/ (shadow pilot historically), src/phase20/ AGENT_SHADOW path referenced in phase33",
            ],
            "assessment": (
                "Architecture declares separation but Phase42/44 explicitly leave AGENT_SHADOW empty. "
                "No adaptive loop from agent decisions → matured outcomes → policy improvement in recent research."
            ),
        },
        {
            "finding": "Program is primarily batch hypothesis testing, not a learning agent.",
            "evidence": ["src/phase42/run_phase42.py", "src/phase44/run_phase44.py"],
            "implication": "LEARNING_ARCHITECTURE_NOT_GENUINELY_ADAPTIVE is a justified program-level diagnosis.",
        },
        {
            "recommendation": (
                "Before RL/NN: implement offline policy evaluation on HISTORICAL_HYPOTHETICAL with costed EV, "
                "then a bounded AGENT_SHADOW loop that logs decisions and updates only calibration/thresholds under freeze rules."
            ),
        },
    ]
    payload = {
        "audit": "learning",
        "findings": findings,
        "merged_stores": False,
        "genuinely_adaptive": False,
    }
    write_json("audit_learning.json", payload)
    return payload


def audit_decision_pipeline() -> dict[str, Any]:
    findings = [
        {
            "stage": "Observation→Features",
            "status": "IMPLEMENTED",
            "gap": "Feature set conventional; weak cost/regime representation",
        },
        {
            "stage": "Features→Predictions",
            "status": "RULE_TRIGGERS_NOT_PROBABILITIES",
            "evidence": ["src/phase44/triggers.py", "src/phase25/strategies/mean_reversion.py"],
            "gap": "No calibrated P(success) or P(net_R>0); binary triggers only",
        },
        {
            "stage": "Predictions→Expected Value",
            "status": "MISSING_AS_FIRST_CLASS_OBJECT",
            "gap": "EV under bid/ask+costs not computed before entry; stress tests are post-hoc",
        },
        {
            "stage": "Risk Assessment",
            "status": "PARTIAL",
            "evidence": ["fixed ATR SL/TP multiples in phase39/41/44"],
            "gap": "No uncertainty/familiarity gate; no portfolio exposure model beyond notes",
        },
        {
            "stage": "BUY/SELL/WAIT",
            "status": "TRIGGER_OR_WAIT",
            "gap": "WAIT not chosen by max EV; no 'unfamiliar regime → WAIT' policy",
        },
    ]
    payload = {
        "audit": "decision_intelligence",
        "pipeline": "Market Observation → Features → Predictions → Expected Value → Risk → Action",
        "findings": findings,
        "blocking_missing_components": [
            "calibrated probability model for trade success / net_R",
            "explicit EV = E[net_R|x] - cost_stress with WAIT if EV<=0",
            "regime familiarity / OOD score",
            "portfolio concurrent exposure constraints",
        ],
    }
    write_json("audit_decision.json", payload)
    return payload


def audit_data_execution() -> dict[str, Any]:
    p43 = json.loads((REPORTS_ROOT / "phase43" / "final_verdict.json").read_text(encoding="utf-8"))
    p44pf = json.loads((REPORTS_ROOT / "phase44" / "preflight.json").read_text(encoding="utf-8"))
    findings = [
        {
            "finding": "Phase43 delivered 30 UNSEEN dates and ~10M ticks with verified manifests.",
            "evidence": ["reports/phase43/final_verdict.json", "reports/phase43/independent_verification.json"],
            "verdict_snapshot": p43.get("final_verdict"),
            "ticks_total": p43.get("ticks_total"),
        },
        {
            "finding": "Phase44 preflight flagged unusually high tick counts on late validation-window dates (density anomaly).",
            "evidence": ["reports/phase44/preflight.json unusual_tick_counts"],
            "unusual_n": len(p44pf.get("unusual_tick_counts") or []),
            "impact": "Demo tick density regime shift may confound microstructure features across discovery vs validation eras.",
        },
        {
            "finding": "Demo bid/ask is reconstruction substrate, not live broker truth.",
            "evidence": ["reports/phase37/final_verdict.json", "reports/phase41/PHASE41_FINAL_REPORT.md"],
        },
        {
            "finding": "No additional large downloads in Phase45 (constraint honored).",
            "evidence": ["phase45 mission constraints"],
        },
        {
            "finding": "Phase44 validation dates remain locked from future discovery.",
            "locked_dates": PHASE44_VALIDATION_DATES_LOCKED,
        },
    ]
    payload = {
        "audit": "data_execution",
        "findings": findings,
        "data_blocks_research": False,
        "data_is_necessary_but_insufficient": True,
    }
    write_json("audit_data_execution.json", payload)
    return payload


def audit_statistics() -> dict[str, Any]:
    findings = [
        {
            "practice": "Chronological discovery/validation splits",
            "status": "USED",
            "evidence": ["src/phase42/constants.py", "src/phase44/constants.py"],
        },
        {
            "practice": "Bonferroni / date-block bootstrap / LODO",
            "status": "USED",
            "evidence": ["src/phase42/stats.py", "src/phase44/stats.py", "src/phase41/metrics.py"],
        },
        {
            "practice": "Independent recomputation",
            "status": "USED",
            "evidence": [
                "src/phase41/independent_eval.py",
                "src/phase42/independent.py",
                "src/phase44/independent.py",
            ],
        },
        {
            "practice": "Exposure tracking for independent dates",
            "status": "INTRODUCED_PHASE43",
            "evidence": ["src/phase43/exposure.py", "reports/phase43/prior_exposure_registry.json"],
        },
        {
            "risk": "Validation-set reuse",
            "status": "PHASE44_VALIDATION_MUST_STAY_CLOSED_FOR_DISCOVERY",
            "locked_dates": PHASE44_VALIDATION_DATES_LOCKED,
        },
        {
            "risk": "Overlapping events / serial dependence",
            "status": "PARTIALLY_MITIGATED_BY_BLOCK_BOOTSTRAP",
            "gap": "Portfolio exposure still under-modeled in decision EV",
        },
        {
            "finding": "Statistical bar was NOT the primary failure mode after Phase43 data expansion — hypotheses still failed on discovery.",
            "evidence": ["reports/phase44/discovery_results.json", "reports/phase42/rejected_hypothesis_registry.json"],
        },
    ]
    payload = {"audit": "statistics", "findings": findings}
    write_json("audit_statistics.json", payload)
    return payload
