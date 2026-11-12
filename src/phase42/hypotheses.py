"""Frozen hypothesis registry — one primary hypothesis per research family. No H13/MR revival."""

from __future__ import annotations

from typing import Any

from phase42.constants import RECIPE_ID, RETIRED_CANDIDATES


def frozen_hypothesis_registry() -> dict[str, Any]:
    """Freeze BEFORE evaluation. Cosmetic parameter variants are forbidden as 'new' discoveries."""
    hyps = [
        {
            "id": "H42_A_VOL_COMPRESS_EXPAND",
            "family": "A_volatility_compression_expansion",
            "behavior": (
                "After sustained ATR compression (low realized range relative to ATR), "
                "the next expansion tends to produce larger absolute displacement than unconditional."
            ),
            "observable_inputs": ["atr_14", "range_efficiency_12", "compress_bars"],
            "entry_condition": "compress_bars>=6 AND atr_14_pct < rolling_p30_atr_pct",
            "directional_prediction": "UNSIGNED_EXPANSION",  # predicts |move|, not direction
            "horizon_bars": 12,
            "invalidation": "ATR expands without |return_H12|/ATR exceeding unconditional median",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Direction unknown → trading edge not implied by expansion alone",
            "success_criteria": "Conditional |ret_H12|/ATR > unconditional by >=0.15 with Bonferroni-corrected evidence",
            "predicts": "volatility_and_displacement",
            "decision_side": None,
        },
        {
            "id": "H42_B_TREND_EXHAUST_WICK",
            "family": "B_trend_continuation_exhaustion",
            "behavior": (
                "After a directional run with rising close displacement, a large opposing wick "
                "signals exhaustion and short-horizon mean reversion of the run."
            ),
            "observable_inputs": ["run_bars", "wick_reject_strength", "ema_9_20_spread"],
            "entry_condition": "run_bars>=5 AND wick_reject_strength>=1.2 AND sign(wick)!=sign(run)",
            "directional_prediction": "AGAINST_PRIOR_RUN",
            "horizon_bars": 6,
            "invalidation": "Price continues through wick extreme within H6",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Bid/ask required for decision evaluation",
            "success_criteria": "Conditional signed return in predicted direction exceeds unconditional",
            "predicts": "direction",
            "decision_side": "AGAINST_RUN",
        },
        {
            "id": "H42_C_SESSION_SWEEP_REJECT",
            "family": "C_liquidity_sweep_rejection",
            "behavior": (
                "Sweep of prior session high/low followed by close back inside range predicts "
                "continuation away from the swept level over H6–H12."
            ),
            "observable_inputs": ["session_high", "session_low", "sweep_flag", "reject_close"],
            "entry_condition": "sweep_high AND close < session_high - 0.25*ATR (or symmetric low)",
            "directional_prediction": "AWAY_FROM_SWEEP",
            "horizon_bars": 12,
            "invalidation": "Close beyond swept extreme by >0.5 ATR within H3",
            "required_data": ["M5 OHLC", "session segmentation UTC"],
            "execution_cost_note": "Sweeps often coincide with wider spreads",
            "success_criteria": "Signed conditional expectancy > unconditional after costs stress",
            "predicts": "direction",
            "decision_side": "AWAY_FROM_SWEEP",
        },
        {
            "id": "H42_D_RANGE_TO_TREND_BREAK",
            "family": "D_range_to_trend_transitions",
            "behavior": (
                "Tight range (low efficiency) followed by a close beyond range high/low by >=0.5 ATR "
                "predicts continuation in break direction over H12."
            ),
            "observable_inputs": ["range_high_20", "range_low_20", "range_width_atr", "break_close"],
            "entry_condition": "range_width_atr<=1.5 AND close beyond range by >=0.5 ATR",
            "directional_prediction": "BREAK_DIRECTION",
            "horizon_bars": 12,
            "invalidation": "Return inside range mid within H3",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Breaks may fill poorly; tick path required",
            "success_criteria": "Conditional directional R > 0 with CI surviving Bonferroni",
            "predicts": "direction",
            "decision_side": "BREAK_DIRECTION",
        },
        {
            "id": "H42_E_TREND_TO_RANGE_SLOWDOWN",
            "family": "E_trend_to_range_transitions",
            "behavior": (
                "After a strong trend (high efficiency), slowing displacement and falling efficiency "
                "predicts reduced absolute H12 returns (range onset), not a directional fade."
            ),
            "observable_inputs": ["efficiency_20", "disp_atr", "efficiency_delta"],
            "entry_condition": "efficiency_20 was high then efficiency_delta<0 AND |disp_atr|<0.8",
            "directional_prediction": "UNSIGNED_COMPRESSION",
            "horizon_bars": 12,
            "invalidation": "|ret_H12|/ATR remains above unconditional median",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Predicts quieter market — not a directional trade by itself",
            "success_criteria": "Conditional |ret|/ATR lower than unconditional",
            "predicts": "volatility",
            "decision_side": None,
        },
        {
            "id": "H42_F_MTF_MOMENTUM_DISAGREE",
            "family": "F_multi_timeframe_momentum_disagreement",
            "behavior": (
                "When completed H1 trend disagrees with M5 short momentum, M5 tends to realign "
                "toward H1 over H12 (H1 wins disagreement)."
            ),
            "observable_inputs": ["h1_trend", "m5_mom_6", "disagree_flag"],
            "entry_condition": "h1_trend in {up,down} AND sign(m5_mom_6)!=sign(h1) AND |m5_mom_6|/ATR>=0.3",
            "directional_prediction": "H1_DIRECTION",
            "horizon_bars": 12,
            "invalidation": "H1 trend flips on next completed H1 before H12",
            "required_data": ["M5 OHLC", "completed H1"],
            "execution_cost_note": "Uses completed H1 only — no forming candle",
            "success_criteria": "Conditional signed return toward H1 > unconditional",
            "predicts": "direction",
            "decision_side": "H1_DIRECTION",
            "note": "Distinct from retired H13_C pullback-to-EMA rules; no EMA pullback cuts reused",
        },
        {
            "id": "H42_G_TICK_IMBALANCE",
            "family": "G_bid_ask_tick_imbalance",
            "behavior": (
                "Within the current M5 bar's completed ticks, bid-hit vs ask-hit imbalance "
                "predicts short-horizon continuation over H3."
            ),
            "observable_inputs": ["tick_imbalance_bar", "spread_median_bar", "n_ticks_bar"],
            "entry_condition": "n_ticks_bar>=30 AND |imbalance|>=0.25 AND spread_median_bar<=p70",
            "directional_prediction": "IMBALANCE_SIGN",
            "horizon_bars": 3,
            "invalidation": "Imbalance flips within next bar",
            "required_data": ["M5 OHLC", "bid/ask ticks"],
            "execution_cost_note": "Microstructure on MetaQuotes-Demo is not live broker truth",
            "success_criteria": "Conditional H3 signed return aligned with imbalance",
            "predicts": "direction",
            "decision_side": "IMBALANCE_SIGN",
        },
        {
            "id": "H42_H_SESSION_NY_DRIFT",
            "family": "H_session_dependent_behavior",
            "behavior": (
                "During New York session UTC hours, overnight Asia range midpoint acts as magnet "
                "or continuation hinge: distance from Asia mid predicts H6 reversion toward mid."
            ),
            "observable_inputs": ["asia_mid", "dist_asia_mid_atr", "session_ny"],
            "entry_condition": "session_ny==1 AND |dist_asia_mid_atr|>=1.0",
            "directional_prediction": "TOWARD_ASIA_MID",
            "horizon_bars": 6,
            "invalidation": "Distance increases by >0.5 ATR within H3",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Session boundaries in UTC only",
            "success_criteria": "Conditional reversion expectancy > unconditional",
            "predicts": "direction",
            "decision_side": "TOWARD_ASIA_MID",
        },
        {
            "id": "H42_I_VOL_COND_DIRECTION",
            "family": "I_volatility_conditioned_directional",
            "behavior": (
                "In high ATR%-regime, short M5 momentum continuation is stronger than in low ATR% regime."
            ),
            "observable_inputs": ["atr_14_pct", "mom_3", "vol_regime"],
            "entry_condition": "vol_regime==high AND |mom_3|/ATR>=0.4",
            "directional_prediction": "MOM_SIGN",
            "horizon_bars": 6,
            "invalidation": "Immediate H1 adverse move >1 ATR",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "High-vol regimes often wider spreads",
            "success_criteria": "High-vol conditional continuation > low-vol continuation and > unconditional",
            "predicts": "direction",
            "decision_side": "MOM_SIGN",
        },
        {
            "id": "H42_J_DISPLACEMENT_RETRACE",
            "family": "J_price_displacement_retracement",
            "behavior": (
                "Large single-bar displacement (>=1.5 ATR) tends to partially retrace within H6 "
                "before continuing or ranging."
            ),
            "observable_inputs": ["bar_disp_atr", "disp_sign"],
            "entry_condition": "bar_disp_atr>=1.5",
            "directional_prediction": "AGAINST_DISPLACEMENT",
            "horizon_bars": 6,
            "invalidation": "No retrace of >=0.4 ATR within H6",
            "required_data": ["M5 OHLC"],
            "execution_cost_note": "Entry at next open after displacement bar",
            "success_criteria": "Conditional retrace signed R > unconditional",
            "predicts": "direction",
            "decision_side": "AGAINST_DISPLACEMENT",
        },
    ]

    return {
        "recipe_id": RECIPE_ID,
        "frozen_before_evaluation": True,
        "optimization_forbidden": True,
        "retired_not_revived": list(RETIRED_CANDIDATES),
        "n_hypotheses": len(hyps),
        "n_families": len({h["family"] for h in hyps}),
        "hypotheses": hyps,
        "note": "Exactly one primary hypothesis per family A–J; not parameter clones of each other or of retired strategies.",
    }
