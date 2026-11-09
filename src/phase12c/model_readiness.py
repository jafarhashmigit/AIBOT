"""Champion readiness audit from existing Phase 1–11 evidence. No holdout. No training."""

from __future__ import annotations

from phase12c.constants import CHAMPION, CHAMPION_STATUS, RESEARCH_CUTOFF_UTC

# Evidence is drawn from frozen docs/reports already produced by prior phases.
# No xauusd_m5_test.csv. No post-cutoff market files. No re-fitting.


CANDIDATES = [
    {
        "model_id": "phase1_rf_m5_baseline",
        "source_phase": 1,
        "training_boundary": "Phase 1 validation window; distinct task (BUY/SELL/WAIT labels)",
        "oos_evidence": "1,518 validation trades, mean −0.0169R, PF 0.965",
        "walk_forward_stability": "not Phase 2 walk-forward; historical reference only",
        "cost_aware_economic": "negative after costs on its own task",
        "drawdown_uncertainty": "reported in Phase 1; not confirmatory",
        "leakage_temporal_safety": "pre-Phase-2 feature clock issues later corrected; not reused",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Different task; losing after costs; not comparable to Phase 2 side-outcome OOS.",
    },
    {
        "model_id": "phase2_rf_side_outcome",
        "source_phase": 2,
        "training_boundary": f"WF folds ending at or before {RESEARCH_CUTOFF_UTC}; holdout never opened",
        "oos_evidence": "36,468 side-outcome rows; RF balanced acc 0.465 beats prior; E1 mean R −0.021",
        "walk_forward_stability": "E1 negative on WF1/WF2/WF3",
        "cost_aware_economic": "E1 PF 0.956; CI [−0.060, +0.017]; P(mean≤0)=0.86",
        "drawdown_uncertainty": "E1 max DD USD/oz 1,642",
        "leakage_temporal_safety": "feature allowlist + cutoff enforced; exploratory only",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Classification vs prior is not a trading edge; cost-aware E1 loses on every fold.",
    },
    {
        "model_id": "phase2_ridge_side_outcome",
        "source_phase": 2,
        "training_boundary": "Same WF folds as Phase 2 RF",
        "oos_evidence": "MAE ≈ constant baseline; corr(pred, actual) ≈ 0.02",
        "walk_forward_stability": "no useful fold-level predictive association",
        "cost_aware_economic": "no standalone economic policy cleared Phase 2 gate",
        "drawdown_uncertainty": "n/a (not an economic champion)",
        "leakage_temporal_safety": "same as Phase 2",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Regression essentially matches constant mean; not economically actionable.",
    },
    {
        "model_id": "phase3_p3_conservative_ev",
        "source_phase": 3,
        "training_boundary": "Inner nested folds; outer WF2+WF3 only",
        "oos_evidence": "12,156 WAIT decisions; 0 trades",
        "walk_forward_stability": "identical to Always WAIT",
        "cost_aware_economic": "net 0 by refusal; not an edge",
        "drawdown_uncertainty": "0 (no trades)",
        "leakage_temporal_safety": "passed Phase 3 leakage audit",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Frozen policy is WAIT refusal. Not a directional model candidate.",
    },
    {
        "model_id": "phase3_meta_ridge",
        "source_phase": 3,
        "training_boundary": "Inner calibration; outer WF2+WF3",
        "oos_evidence": "3,322 outer trades; mean trade R −0.011; CI includes 0",
        "walk_forward_stability": "inner positive, outer collapses (overfit)",
        "cost_aware_economic": "net USD +54.66 but PF≈1 and fold signs mixed",
        "drawdown_uncertainty": "CI [−0.092, +0.071]; P(mean≤0)=0.57",
        "leakage_temporal_safety": "decision-layer overfit to calibration window",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Inner positivity did not survive outer evaluation.",
    },
    {
        "model_id": "phase4_ny_sell_slice",
        "source_phase": 4,
        "training_boundary": "Outer OOS session×side catalogue; not a trained model",
        "oos_evidence": "NY SELL mean R +0.036 on outer sample (promising slice only)",
        "walk_forward_stability": "both outer folds positive in Phase 4 slice table",
        "cost_aware_economic": "exploratory slice; not a frozen production rule",
        "drawdown_uncertainty": "short research history; seasonal risk acknowledged",
        "leakage_temporal_safety": "corrected UTC sessions; BH-FDR catalogue",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Promising slice only. Phase 5 independent replication failed.",
    },
    {
        "model_id": "phase5_ny_sell_replication",
        "source_phase": 5,
        "training_boundary": "Independent 2025-06 → 2026-02 sample; frozen rule; no retune",
        "oos_evidence": "8,446 eligible trades; mean R −0.0816; PF 0.929",
        "walk_forward_stability": "0/3 chronological blocks positive",
        "cost_aware_economic": "CI [−0.139, −0.025] entirely below 0; worsens under cost stress",
        "drawdown_uncertainty": "max DD USD 2,611",
        "leakage_temporal_safety": "hypothesis pre-registered; independent sample not pooled with Phase 4",
        "independently_replicated": True,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Independent replication falsified the Phase 4 NY-SELL promise.",
    },
    {
        "model_id": "phase6_null_predictor",
        "source_phase": 6,
        "training_boundary": "Architecture only; NullPredictor; no production fit",
        "oos_evidence": "no economic experiment",
        "walk_forward_stability": "n/a",
        "cost_aware_economic": "n/a",
        "drawdown_uncertainty": "n/a",
        "leakage_temporal_safety": "architecture enforces cutoff and forbidden outcome keys",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "NullPredictor is a scaffold, not a candidate.",
    },
    {
        "model_id": "phase7_p7_phase6_default",
        "source_phase": 7,
        "training_boundary": "Phase 2 OOS lookup only; no retrain; max ts 2026-09-29 17:50",
        "oos_evidence": "18,234 WAIT after WAIT-only gate; baselines E1/Direction lose",
        "walk_forward_stability": "WAIT on WF1/WF2/WF3",
        "cost_aware_economic": "agent net 0 by WAIT; E1 mean R −0.021",
        "drawdown_uncertainty": "agent DD 0 (no trades)",
        "leakage_temporal_safety": "holdout 0; Phase 2 OOS hash verified",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "ARCHITECTURE VALIDATED — NO ECONOMIC EDGE. Gate correctly forced WAIT.",
    },
    {
        "model_id": "phase9_experience_ridge_v1",
        "source_phase": 9,
        "training_boundary": "Chronological experience replay ≤ cutoff; min 100/side",
        "oos_evidence": "final BUY/SELL/WAIT = 0/0/18234; mean R diff vs Phase 6 = 0",
        "walk_forward_stability": "no improvement vs frozen Phase 6",
        "cost_aware_economic": "EXPERIENCE LEARNING DID NOT IMPROVE OOS DECISION QUALITY",
        "drawdown_uncertainty": "unchanged vs WAIT baseline after gate",
        "leakage_temporal_safety": "temporal leakage violations 0; holdout 0",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Learner did not improve OOS decision quality; remains experimental and blocked.",
    },
    {
        "model_id": "phase10_11_dual_source",
        "source_phase": "10-11",
        "training_boundary": "Dual-source stores validated; no combined learner trained",
        "oos_evidence": "paper completed outcomes = 0; historical R not comparable to paper R",
        "walk_forward_stability": "n/a (validation only)",
        "cost_aware_economic": "no shared learner; no edge claimed",
        "drawdown_uncertainty": "paper metrics unavailable (null), not zero",
        "leakage_temporal_safety": "source separation and temporal audits passed",
        "independently_replicated": False,
        "justifies_further_shadow_research": False,
        "verdict": "REJECTED",
        "reason": "Architecture validated; no eligible combined or paper-backed model exists.",
    },
]


def audit_model_readiness() -> dict:
    rejected = [c for c in CANDIDATES if c["verdict"] == "REJECTED"]
    experimental = [c for c in CANDIDATES if c["verdict"] == "EXPERIMENTAL_CANDIDATE"]
    validated = [c for c in CANDIDATES if c["verdict"] == "VALIDATED_CANDIDATE"]
    status = CHAMPION_STATUS
    if validated:
        status = "VALIDATED_CANDIDATE"
    elif experimental:
        status = "EXPERIMENTAL_CANDIDATE"
    else:
        status = "NO_MODEL"
    return {
        "champion_status": status,
        "champion_id": CHAMPION,
        "production_promotion": False,
        "buy_sell_authorized": False,
        "candidates": CANDIDATES,
        "counts": {
            "total": len(CANDIDATES),
            "rejected": len(rejected),
            "experimental": len(experimental),
            "validated": len(validated),
        },
        "selection_rule": (
            "Do not pick the least-bad loser. Classification accuracy alone is insufficient. "
            "Historical hypothetical and agent paper experiences were not combined."
        ),
        "rationale": (
            "Every audited candidate fails cost-aware OOS, independent replication, "
            "or is an architecture/WAIT scaffold. Retain no_model."
        ),
    }


def candidate_comparison_table() -> list[dict]:
    rows = []
    for c in CANDIDATES:
        rows.append({
            "model_id": c["model_id"],
            "source_phase": c["source_phase"],
            "verdict": c["verdict"],
            "economic_summary": c["cost_aware_economic"],
            "replicated": c["independently_replicated"],
            "shadow_research": c["justifies_further_shadow_research"],
            "reason": c["reason"],
        })
    return rows
