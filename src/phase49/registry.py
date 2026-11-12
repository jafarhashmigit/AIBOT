"""Frozen feature & hypothesis registries (≤30 features, ≤18 hypotheses)."""

from __future__ import annotations

from typing import Any

from phase49.constants import REPORTS_DIR, canonical_json_sha256
from phase49.progress import write_json

# Verified source fields from Phase43/49 M5/tick inventory (documented at freeze time)
SOURCE_FIELDS_M5 = ("open", "high", "low", "close", "tick_volume", "spread", "real_volume", "timestamp_utc")
SOURCE_FIELDS_TICK = ("bid", "ask", "timestamp_msc", "timestamp_utc", "volume", "flags")
SOURCE_FIELDS_H1 = ("open", "high", "low", "close", "tick_volume", "spread", "timestamp_utc")


def build_feature_registry() -> dict[str, Any]:
    """Formal registry — no VWAP (real_volume typically 0 / not exchange volume)."""
    features = [
        # A — Price acceptance / rejection
        _f("A01_sess_range_pos", "A_price_acceptance", "Session range position (close-sess_low)/(sess_high-sess_low) on completed bars today", ["close", "high", "low"], 1, "BUY high / SELL low acceptance"),
        _f("A02_dist_sess_high_atr", "A_price_acceptance", "(sess_high-close)/ATR14", ["high", "close"], 14, "Near highs → BUY rejection risk"),
        _f("A03_dist_sess_low_atr", "A_price_acceptance", "(close-sess_low)/ATR14", ["low", "close"], 14, "Near lows → SELL rejection risk"),
        _f("A04_failed_break_up", "A_price_acceptance", "1 if prior bar high>prev_sess_high and close back inside", ["high", "close"], 2, "Failed upside break → SELL bias"),
        _f("A05_time_above_open", "A_price_acceptance", "Fraction of today's completed bars with close>day_open", ["close", "open"], 1, "Acceptance above open → BUY"),
        # B — Structure / path geometry
        _f("B01_efficiency_12", "B_structure", "|close-close_12|/sum(|Δclose|) over 12", ["close"], 12, "Trend efficiency"),
        _f("B02_net_disp_atr_12", "B_structure", "(close-close_12)/ATR14", ["close"], 14, "Signed displacement"),
        _f("B03_consec_dir", "B_structure", "Signed count of consecutive same-direction closes (capped ±8)", ["close"], 8, "Persistence"),
        _f("B04_impulse_retr_ratio", "B_structure", "Last 6-bar net / prior 6-bar net magnitude", ["close"], 12, "Impulse vs retracement"),
        _f("B05_compression", "B_structure", "(high-low)/ATR14", ["high", "low"], 14, "Range compression/expansion"),
        # C — Volatility
        _f("C01_rv_12", "C_volatility", "Std of 1-bar returns over 12", ["close"], 12, "Short realized vol"),
        _f("C02_rv_48", "C_volatility", "Std of 1-bar returns over 48", ["close"], 48, "Longer realized vol"),
        _f("C03_vol_accel", "C_volatility", "rv_12/(rv_48+eps)", ["close"], 48, "Vol acceleration"),
        _f("C04_range_vs_prior", "C_volatility", "Today range so far / prior completed day range", ["high", "low"], 1, "Range expansion vs prior day"),
        _f("C05_vol_of_vol", "C_volatility", "Std of rolling 6-bar ranges over 24", ["high", "low"], 24, "Vol instability"),
        # D — Session / temporal
        _f("D01_london_active", "D_session", "1 if hour UTC in [07,16)", ["timestamp_utc"], 0, "London session"),
        _f("D02_ny_active", "D_session", "1 if hour UTC in [12,21)", ["timestamp_utc"], 0, "New York session"),
        _f("D03_overlap", "D_session", "1 if London∩NY overlap [12,16)", ["timestamp_utc"], 0, "Overlap liquidity"),
        _f("D04_hours_since_london", "D_session", "Hours since 07:00 UTC (clipped)", ["timestamp_utc"], 0, "Time since London open"),
        _f("D05_dow", "D_session", "Day-of-week Mon=0..Fri=4", ["timestamp_utc"], 0, "Calendar effect"),
        # E — Execution / liquidity
        _f("E01_spread_price", "E_execution", "ask-bid from last tick in decision bar (or M5 spread points*0.01 proxy)", ["bid", "ask", "spread"], 1, "Absolute spread"),
        _f("E02_spread_atr", "E_execution", "spread_price/ATR14", ["bid", "ask"], 14, "Spread vs risk"),
        _f("E03_spread_delta", "E_execution", "spread_now - median spread prior 12 bars", ["bid", "ask"], 12, "Spread expansion"),
        _f("E04_tick_intensity", "E_execution", "n_ticks in decision bar / median prior 12", ["timestamp_msc"], 12, "Tick arrival intensity"),
        _f("E05_uptick_frac", "E_execution", "Fraction of ticks with mid up vs prior tick in bar", ["bid", "ask"], 1, "Micro directional pressure"),
        # F — Multi-timeframe (completed bars only)
        _f("F01_m15_ret", "F_mtf", "Last completed M15 return (aggregated from M5)", ["close"], 3, "M15 drift"),
        _f("F02_h1_ret", "F_mtf", "Last completed H1 return before decision", ["close"], 1, "H1 drift"),
        _f("F03_h1_range_pos", "F_mtf", "Position in last completed H1 range", ["high", "low", "close"], 1, "H1 location"),
        _f("F04_mtf_agree", "F_mtf", "sign(m15_ret)*sign(h1_ret)", ["close"], 3, "TF agreement"),
        _f("F05_h1_stability", "F_mtf", "1 - |h1_ret|/(h1_range/close+eps)", ["high", "low", "close"], 1, "H1 quiet vs trending"),
    ]
    assert len(features) <= 30
    reg = {
        "n_features": len(features),
        "max_features": 30,
        "families": sorted({f["family"] for f in features}),
        "source_fields_m5": list(SOURCE_FIELDS_M5),
        "source_fields_tick": list(SOURCE_FIELDS_TICK),
        "source_fields_h1": list(SOURCE_FIELDS_H1),
        "vwap_included": False,
        "vwap_reason": "real_volume not verified as exchange volume; tick_volume is not eligible VWAP weight",
        "features": features,
        "leakage_policy": "Only bars/ticks with timestamps <= decision bar end; H1/M15 must be completed",
        "missing_data": "Feature set to NaN; event excluded from hypothesis if any required feature NaN",
    }
    reg["registry_sha256"] = canonical_json_sha256({k: v for k, v in reg.items() if k != "registry_sha256"})
    write_json(REPORTS_DIR / "feature_registry.json", reg)
    return reg


def _f(fid: str, family: str, definition: str, sources: list[str], lookback: int, rationale: str) -> dict[str, Any]:
    return {
        "feature_id": fid,
        "family": family,
        "definition": definition,
        "source_fields": sources,
        "lookback_bars": lookback,
        "decision_time_available": True,
        "missing_data_behavior": "NaN → exclude event from tests using this feature",
        "leakage_tests": ["completed_bars_only", "no_future_session_extrema", "h1_close_before_decision"],
        "economic_rationale": rationale,
        "expected_buy_relation": "see hypothesis registry",
        "expected_sell_relation": "see hypothesis registry",
    }


def build_hypothesis_registry() -> dict[str, Any]:
    """≤3 pre-registered hypotheses per family (18 total). Polarity frozen before evaluation."""
    hyps = [
        # A
        _h("H_A1", "A_price_acceptance", "A01_sess_range_pos", "BUY", "high", "Acceptance near session highs favors BUY continuation"),
        _h("H_A2", "A_price_acceptance", "A04_failed_break_up", "SELL", "high", "Failed breakout favors SELL"),
        _h("H_A3", "A_price_acceptance", "A03_dist_sess_low_atr", "BUY", "low", "Near session lows (small dist) favors BUY bounce"),
        # B
        _h("H_B1", "B_structure", "B01_efficiency_12", "BUY", "high", "High efficiency with positive B02 → BUY"),
        _h("H_B2", "B_structure", "B02_net_disp_atr_12", "BUY", "high", "Positive displacement favors BUY"),
        _h("H_B3", "B_structure", "B05_compression", "BUY", "low", "Compression precedes expansion; directional via B02 sign handled in combo note"),
        # C
        _h("H_C1", "C_volatility", "C03_vol_accel", "SELL", "high", "Vol acceleration after expansion favors mean fade SELL — diagnostic"),
        _h("H_C2", "C_volatility", "C04_range_vs_prior", "BUY", "high", "Range expansion day favors continuation BUY if B02>0 filtered in eval"),
        _h("H_C3", "C_volatility", "C01_rv_12", "SELL", "low", "Low short vol favors quieter SELL? exploratory polarity"),
        # D
        _h("H_D1", "D_session", "D03_overlap", "BUY", "high", "Overlap hours favor BUY liquidity continuation — diagnostic"),
        _h("H_D2", "D_session", "D04_hours_since_london", "SELL", "high", "Late session fade SELL"),
        _h("H_D3", "D_session", "D01_london_active", "BUY", "high", "London active BUY bias diagnostic"),
        # E
        _h("H_E1", "E_execution", "E02_spread_atr", "BUY", "low", "Tight spread/ATR improves BUY net R"),
        _h("H_E2", "E_execution", "E03_spread_delta", "SELL", "high", "Spread expansion hurts; prefer SELL only if spread low — use low for BUY actually"),
        _h("H_E3", "E_execution", "E04_tick_intensity", "BUY", "high", "High intensity favors informative BUY"),
        # F
        _h("H_F1", "F_mtf", "F04_mtf_agree", "BUY", "high", "TF agreement + positive favors BUY"),
        _h("H_F2", "F_mtf", "F02_h1_ret", "BUY", "high", "Positive completed H1 return favors BUY"),
        _h("H_F3", "F_mtf", "F03_h1_range_pos", "SELL", "high", "At H1 highs favors SELL fade"),
    ]
    # Fix H_E2 to coherent polarity: high spread delta → avoid BUY; test SELL when spread_delta low is odd.
    # Keep as registered: high spread_delta → worse for both; hypothesis tests action when feature in selected tail.
    assert len(hyps) <= 18
    reg = {
        "n_hypotheses": len(hyps),
        "max_hypotheses": 18,
        "bonferroni_n": 18,
        "selection_rule": (
            "On discovery dates only: select events where feature is in the upper tercile ('high') "
            "or lower tercile ('low') of the discovery-date feature distribution. "
            "Compare mean action net_R vs unconditional action mean on same events universe. "
            "Tercile edges frozen from discovery for confirmation."
        ),
        "retired_not_revived": ["H13_C", "mean_reversion", "H42_*", "H44_*"],
        "hypotheses": hyps,
    }
    reg["hypothesis_registry_sha256"] = canonical_json_sha256(
        {k: v for k, v in reg.items() if k != "hypothesis_registry_sha256"}
    )
    write_json(REPORTS_DIR / "hypothesis_registry.json", reg)
    return reg


def _h(hid: str, family: str, feature_id: str, action: str, tail: str, rationale: str) -> dict[str, Any]:
    return {
        "hypothesis_id": hid,
        "family": family,
        "feature_id": feature_id,
        "action": action,
        "tail": tail,  # high | low tercile
        "rationale": rationale,
    }
