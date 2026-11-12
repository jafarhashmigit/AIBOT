"""Future hypothesis candidates — ranked by plausibility/testability, not profit."""

from __future__ import annotations

from typing import Any

from phase67.constants import canonical_json_sha256


def future_hypothesis_candidates() -> dict[str, Any]:
    cands = [
        {
            "rank": 1,
            "id": "H67_FB1_FAILED_BREAKOUT_REVERSAL",
            "economic_rationale": (
                "Failed breakouts can leave trapped momentum; re-entry into prior range may precede "
                "mean-reversion toward range mid — classic liquidity-grab narrative. Requires Exness "
                "path evidence; exploratory archive only suggested asymmetry to investigate."
            ),
            "definition": (
                "Event at bar t if close_t breaks prior N=24 bar high/low by ≥0.5·ATR_14 and within "
                "K≤6 bars price re-enters range. Signal direction = opposite to breakout. "
                "WAIT otherwise."
            ),
            "required_features": ["M5 OHLC", "ATR_14", "prior_range_24", "session_state"],
            "data_availability": "Archive: yes (consumed). Live Exness: insufficient M5 history.",
            "expected_event_frequency": "Low–moderate; exploratory archive saw sparse re-entries per day",
            "entry_exit": "Entry at re-entry bar close semantics (ask/bid when quotes exist); exit horizon preregistered {6,12} M5; hard WAIT outside OPEN",
            "buy_sell_wait": "BUY after failed downside breakout re-entry; SELL after failed upside; WAIT if no event or non-OPEN",
            "main_failure_conditions": ["trending regime without re-entry", "gap through range", "spread explosion", "CLOSE_ONLY/BREAK"],
            "cost_dependencies": "Spread observable; commission/slippage/swap UNKNOWN — must stress, never zero",
            "required_independent_sample": "≥20 Exness OPEN date-blocks discovery + ≥10 validation; holdout sealed until survivor",
            "preregistration": "Freeze N,K,ATR mult,horizons,session gate,cost stress grid before any Exness evaluation",
        },
        {
            "rank": 2,
            "id": "H67_VC1_HIGH_VOL_CONTINUATION_FILTER",
            "economic_rationale": (
                "Large ATR-normalized displacements may continue more often in high realized-vol regimes "
                "if order-flow persistence dominates; alternatively reverse in low vol. Testability high "
                "once Exness M5 accumulates; do not reuse archive p-values as confirmation."
            ),
            "definition": (
                "Event when |Δclose|/ATR_14 ≥ 1.5. Trade continuation in direction of move only if "
                "ATR_14 is in upper tercile of trailing 20-day ATR distribution; else WAIT."
            ),
            "required_features": ["M5 OHLC", "ATR_14", "trailing ATR distribution", "session_state"],
            "data_availability": "Needs multi-week Exness M5; archive exploratory only",
            "expected_event_frequency": "Moderate on active days",
            "entry_exit": "Enter next bar OPEN only; exit at fixed horizon 12; no trailing until preregistered",
            "buy_sell_wait": "BUY/SELL with displacement; WAIT if ATR not high-vol or session≠OPEN",
            "main_failure_conditions": ["vol tercile instability", "cost > move", "session boundary"],
            "cost_dependencies": "Sensitive to spread at entry; UNKNOWN commission",
            "required_independent_sample": "≥25 date-blocks with ≥5 events/day expected under OPEN",
            "preregistration": "Freeze tercile window, displacement mult, horizon, BUY/SELL split tests",
        },
        {
            "rank": 3,
            "id": "H67_MR1_DISPLACEMENT_REVERSION_LOW_VOL",
            "economic_rationale": (
                "In low-vol regimes, extreme moves may overshoot microstructure liquidity and revert. "
                "Complement to H67_VC1 — mutually exclusive vol gate prevents double-counting."
            ),
            "definition": (
                "Same displacement event as VC1 but only when ATR_14 in lower tercile; trade opposite "
                "direction; WAIT otherwise."
            ),
            "required_features": ["M5 OHLC", "ATR_14", "vol tercile", "session_state"],
            "data_availability": "Exness M5 required; archive descriptive only",
            "expected_event_frequency": "Lower than VC1",
            "entry_exit": "Opposite-to-move entry; horizon 6 primary / 12 secondary (preregistered)",
            "buy_sell_wait": "Opposite of displacement; WAIT if not low-vol or not OPEN",
            "main_failure_conditions": ["news gaps", "vol regime misclassification"],
            "cost_dependencies": "Reversion edges often smaller than spread+costs",
            "required_independent_sample": "≥30 date-blocks due to lower frequency",
            "preregistration": "Must be registered jointly with VC1 to control family-wise error",
        },
        {
            "rank": 4,
            "id": "H67_S1_OPEN_SESSION_ONLY_SPREAD_GATE",
            "economic_rationale": (
                "Even if a signal family exists, trading outside OPEN or during abnormal spread "
                "destroys expectancy. This is a meta-filter hypothesis: signal ∩ OPEN ∩ spread≤P90."
            ),
            "definition": (
                "Any candidate entry permitted only if Phase64.13 state==OPEN and observed bid/ask "
                "spread ≤ trailing P90 of same-session spreads; else WAIT."
            ),
            "required_features": ["session_state", "live bid/ask spread history"],
            "data_availability": "Needs continuous Exness quote snapshots (Phase67 collector); ticks not approved",
            "expected_event_frequency": "Depends on base signal; filter reduces count",
            "entry_exit": "Filter only — does not invent entries",
            "buy_sell_wait": "WAIT when gate fails; else defer to base signal",
            "main_failure_conditions": ["insufficient spread history", "session UNKNOWN"],
            "cost_dependencies": "Directly spread-conditioned; still UNKNOWN commission/swap",
            "required_independent_sample": "≥15 Exness dates with dense quote snapshots across OPEN",
            "preregistration": "Freeze P90 window and session rules before pairing with base family",
        },
        {
            "rank": 5,
            "id": "H67_DA1_DIRECTIONAL_ASYMMETRY_GOLD",
            "economic_rationale": (
                "Gold often exhibits asymmetric upside/downside dynamics; forcing symmetric BUY/SELL "
                "thresholds may destroy signal. Test BUY-only and SELL-only variants as separate hypotheses."
            ),
            "definition": (
                "For a chosen base event family, evaluate BUY-only and SELL-only policies as distinct "
                "preregistered hypotheses with separate multiplicity penalties."
            ),
            "required_features": ["base family features", "direction label"],
            "data_availability": "Same as base family on Exness",
            "expected_event_frequency": "≈ half of symmetric family",
            "entry_exit": "Inherited from base; one direction disabled → WAIT",
            "buy_sell_wait": "One-sided; WAIT for opposite",
            "main_failure_conditions": ["underpowered one-sided samples"],
            "cost_dependencies": "Same UNKNOWN costs; swap may differ by side — UNKNOWN_FOR_EXECUTION",
            "required_independent_sample": "Larger date count than two-sided family",
            "preregistration": "Declare BUY-only and SELL-only as separate IDs before evaluation",
        },
    ]
    out = {
        "n": len(cands),
        "ranking_basis": "scientific_plausibility_and_testability_not_historical_profit",
        "confirmatory_tests_run": False,
        "candidates": cands,
        "note": "None may be promoted without Exness date-blocks + preregistration + cost stress",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
