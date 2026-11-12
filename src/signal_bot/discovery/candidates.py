"""Preregistered Prompt7 candidates — define before outcome cherry-picking.

All archive evaluations are EXPLORATORY_RETROSPECTIVE_ONLY.
No candidate is promoted; Champion remains NO_MODEL.
"""

from __future__ import annotations

from typing import Any

from signal_bot.discovery.constants import (
    EVIDENCE_CLASS,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NONE,
)


def preregistered_candidates() -> list[dict[str, Any]]:
    """Hypotheses considered in Prompt7 (before selection)."""
    return [
        {
            "candidate_id": "C07_A_SESSION_OPEN_DISCOVERY",
            "theme": "Session-driven price discovery (London open acceptance)",
            "economic_rationale": (
                "London open concentrates inventory rebalancing; first 30–60m acceptance "
                "away from Asia mid may continue into London AM if order flow persists."
            ),
            "expected_behavior": "Directional continuation after open range acceptance",
            "persistence_argument": "Institutional session open is structural, not indicator-specific",
            "why_not_already_rejected": (
                "Distinct from H70 Asia-sweep→MSS and H42_H NY drift; not pullback H13_C. "
                "H69_US1 was US open ORB with unresolved defs — this is London-only discovery."
            ),
            "required_data": "M5 OHLC + session timezone; ideally spread/swap",
            "objective_rules_sketch": (
                "OR = first N M5 bars after London 08:00; BUY if close > OR high + buffer; "
                "SELL if close < OR low − buffer; SL = OR opposite; TP = 1.5R; expiry 24 bars"
            ),
            "failure_conditions": "Chop open, news spikes, OR too wide vs ATR",
            "expected_frequency": "~0.3–1 signal/day when OR forms",
            "cost_sensitivity": "HIGH — open spreads often elevated",
            "overlap_risk": "Near H69_US1 / range-break themes; needs independent live dates",
            "preregister_disposition": "HOLD_FOR_DATA",
        },
        {
            "candidate_id": "C07_B_VOL_EXPANSION_AFTER_COMPRESSION",
            "theme": "Volatility expansion after compression",
            "economic_rationale": "Energy release after low realized vol periods",
            "expected_behavior": "Break of compressed range with follow-through",
            "persistence_argument": "Volatility clustering is well-documented",
            "why_not_already_rejected": "H42_A tested a specific compress→expand recipe and was REJECTED; "
            "reviving same family under new ID is forbidden.",
            "required_data": "M5 ATR / range stats",
            "objective_rules_sketch": "N/A — family retired",
            "failure_conditions": "False breakouts in gold",
            "expected_frequency": "variable",
            "cost_sensitivity": "HIGH",
            "overlap_risk": "DIRECT overlap H42_A",
            "preregister_disposition": "REJECT_FAMILY_RETIRED",
            "reject_reason": "vol_compress_expand family REJECTED in Phase45; do_not_revive",
        },
        {
            "candidate_id": "C07_C_FAILED_AUCTION",
            "theme": "Failed auction / acceptance-rejection at prior extremes",
            "economic_rationale": "Sweep beyond prior high/low then close back = trapped liquidity",
            "expected_behavior": "Reversal toward mid-range after failed breakout",
            "persistence_argument": "Auction theory / liquidity runs",
            "why_not_already_rejected": "H42_C session_sweep_reject REJECTED; H70 Asia-sweep London MSS "
            "exploratory negative. Same economic story.",
            "required_data": "M5 OHLC session windows",
            "objective_rules_sketch": "N/A — family exhausted",
            "failure_conditions": "True breakouts",
            "expected_frequency": "low–medium",
            "cost_sensitivity": "HIGH (stops near extremes)",
            "overlap_risk": "H42_C / H70",
            "preregister_disposition": "REJECT_FAMILY_RETIRED",
            "reject_reason": "Failed-auction / sweep-reject already rejected or H70-failed",
        },
        {
            "candidate_id": "C07_D_TREND_PULLBACK_CONTINUATION",
            "theme": "Trend continuation after structural pullback",
            "economic_rationale": "Higher-timeframe trend + pullback entry",
            "expected_behavior": "Resume prior direction after shallow pullback",
            "persistence_argument": "Trend persistence in commodity FX",
            "why_not_already_rejected": "H13_C is RETIRED do_not_revive — exact family",
            "required_data": "M5/H1 structure",
            "objective_rules_sketch": "N/A",
            "failure_conditions": "Regime flip",
            "expected_frequency": "medium",
            "cost_sensitivity": "MEDIUM",
            "overlap_risk": "H13_C",
            "preregister_disposition": "REJECT_FAMILY_RETIRED",
            "reject_reason": "pullback_H13_C RETIRED",
        },
        {
            "candidate_id": "C07_E_BREAKOUT_VS_FAILED_BREAKOUT",
            "theme": "Breakout continuation vs failed breakout filter",
            "economic_rationale": "Distinguish accepted vs rejected range breaks via close/volume/time",
            "expected_behavior": "Continue if accepted; fade if rejected within K bars",
            "persistence_argument": "Structural; needs objective acceptance metric",
            "why_not_already_rejected": "H42_D range_break had zero events; H44 breakout filters mixed. "
            "A dual-path rule is still in the same rejected neighborhood without new independent data.",
            "required_data": "M5 + optional tick",
            "objective_rules_sketch": "Deferred — insufficient independent data to define without overfit",
            "failure_conditions": "Ambiguous acceptance",
            "expected_frequency": "low",
            "cost_sensitivity": "HIGH",
            "overlap_risk": "H42_D / H44",
            "preregister_disposition": "REJECT_INSUFFICIENT_INDEPENDENT_DATA",
            "reject_reason": "Cannot honestly separate from rejected breakout families without sealed/live OOS",
        },
        {
            "candidate_id": "C07_F_REGIME_TRANSITION",
            "theme": "Market regime transitions (trend↔range)",
            "economic_rationale": "Strategy switches when realized vol / ADX-like state flips",
            "expected_behavior": "Different playbooks per regime",
            "persistence_argument": "Regime exists; profitable detection unproven",
            "why_not_already_rejected": "Not a single trade rule; meta-layer. Prior phases lacked confirmed base edge.",
            "required_data": "Long M5/H1 history + costs",
            "objective_rules_sketch": "Needs base edge first — not a standalone entry system",
            "failure_conditions": "Regime lag / misclassification",
            "expected_frequency": "N/A",
            "cost_sensitivity": "depends on sub-policies",
            "overlap_risk": "Meta overfit",
            "preregister_disposition": "REJECT_NO_BASE_EDGE",
            "reject_reason": "Regime layer without validated sub-strategies is research theater",
        },
        {
            "candidate_id": "C07_G_MICROSTRUCTURE_IMBALANCE",
            "theme": "Tick / quote imbalance at session windows",
            "economic_rationale": "Aggressive buy/sell pressure predicts short-horizon continuation",
            "expected_behavior": "Short-lived directional bursts",
            "persistence_argument": "Microstructure; may not survive retail spread",
            "why_not_already_rejected": "Tick imbalance features tested; live tick archive incomplete",
            "required_data": "Reliable tick/quote streams — not available as independent sample",
            "objective_rules_sketch": "N/A — data unavailable",
            "failure_conditions": "Spread dominates edge",
            "expected_frequency": "high if defined",
            "cost_sensitivity": "EXTREME",
            "overlap_risk": "prior tick-imbalance negatives",
            "preregister_disposition": "REJECT_DATA_UNAVAILABLE",
            "reject_reason": "No adequate independent tick dataset; live complete Asia+London dates=0",
        },
        {
            "candidate_id": "C07_H_H70_REVIVAL",
            "theme": "Revive or retune Asia-sweep London MSS",
            "economic_rationale": "Same as H70",
            "expected_behavior": "Same as H70",
            "persistence_argument": "N/A",
            "why_not_already_rejected": "Already challenged — exploratory negative / insufficient sample",
            "required_data": "N/A",
            "objective_rules_sketch": "FORBIDDEN",
            "failure_conditions": "Already failed exploratory",
            "expected_frequency": "N/A",
            "cost_sensitivity": "N/A",
            "overlap_risk": "H70",
            "preregister_disposition": "REJECT_PRIOR_FAILURE",
            "reject_reason": "H70 Prompt4: 6 trades, expectancy≈−0.228R, PF≈0.66; do not retune on same archive",
        },
    ]


def select_candidate(feasibility: dict[str, Any]) -> dict[str, Any]:
    """Evidence-driven selection: at most one survivor, else insufficient/none."""
    cands = preregistered_candidates()
    rejected = [c for c in cands if str(c.get("preregister_disposition", "")).startswith("REJECT")]
    held = [c for c in cands if c.get("preregister_disposition") == "HOLD_FOR_DATA"]

    independent_ok = bool(feasibility.get("sufficient_for_independent_validation"))
    complete = int(
        (feasibility.get("genuine_live_exness_xauusdm") or {}).get(
            "independent_complete_asia_london_dates"
        )
        or 0
    )

    # No candidate may be promoted without independent eligible data.
    # Even HOLD_FOR_DATA candidates are not survivors under INSUFFICIENT data.
    if not independent_ok or complete < 20:
        return {
            "primary_verdict": VERDICT_INSUFFICIENT_DATA,
            "secondary_note": VERDICT_NONE,
            "surviving_candidate_id": None,
            "status": "UNVALIDATED_NOT_SELECTED",
            "champion": "NO_MODEL",
            "production": "WAIT",
            "evidence_class": EVIDENCE_CLASS,
            "n_hypotheses_investigated": len(cands),
            "n_rejected": len(rejected),
            "n_held_pending_data": len(held),
            "held_ids": [c["candidate_id"] for c in held],
            "rejected_ids": [
                {"id": c["candidate_id"], "reason": c.get("reject_reason")} for c in rejected
            ],
            "independent_profitability_evidence": False,
            "net_profitability": "NOT_ESTABLISHED",
            "gross_performance_claim": None,
            "implementation": "NONE — no artificial strategy module",
            "rationale": (
                f"Independent complete Asia+London live dates={complete}. "
                "Archive-only screening cannot select a PROMISING candidate without "
                "falsely treating consumed MetaQuotes data as confirmation. "
                "C07_A remains conceptually interesting but is not selected for engineering."
            ),
        }

    # Path reserved if future live sample qualifies — still would need frozen rules + screen
    return {
        "primary_verdict": VERDICT_NONE,
        "surviving_candidate_id": None,
        "champion": "NO_MODEL",
        "n_hypotheses_investigated": len(cands),
        "implementation": "NONE",
    }
