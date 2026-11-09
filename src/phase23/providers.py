"""Offline provider qualification matrix (public docs only; no network calls)."""

from __future__ import annotations

from typing import Any

CRITERIA = [
    "Q1_free_plan",
    "Q2_xauusd",
    "Q3_historical_m5",
    "Q4_live_or_streaming",
    "Q5_timestamp_utc",
    "Q6_ohlc_construction",
    "Q7_spread",
    "Q8_rate_limits",
    "Q9_auth_eligibility",
    "Q10_licensing",
    "Q11_reliability",
    "Q12_mt5_parity_measured",
]


def _row(
    name: str,
    scores: dict[str, str],
    *,
    notes: str,
    verdict: str,
) -> dict[str, Any]:
    fails = [k for k, v in scores.items() if v == "FAIL"]
    partials = [k for k, v in scores.items() if v == "PARTIAL"]
    return {
        "provider": name,
        "scores": scores,
        "fail_count": len(fails),
        "partial_count": len(partials),
        "failed_criteria": fails,
        "notes": notes,
        "verdict": verdict,
        "selected": False,
    }


def provider_comparison() -> dict[str, Any]:
    """Static assessment — does not contact providers."""
    candidates = [
        _row(
            "AlgoSpecial",
            {
                "Q1_free_plan": "PARTIAL",
                "Q2_xauusd": "PASS",
                "Q3_historical_m5": "PARTIAL",
                "Q4_live_or_streaming": "FAIL",
                "Q5_timestamp_utc": "FAIL",
                "Q6_ohlc_construction": "PARTIAL",
                "Q7_spread": "FAIL",
                "Q8_rate_limits": "PASS",
                "Q9_auth_eligibility": "PASS",
                "Q10_licensing": "PARTIAL",
                "Q11_reliability": "PARTIAL",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Broker-server timestamps; preview caps; live forward unclear; spread often 0.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "TickFeed",
            {
                "Q1_free_plan": "FAIL",
                "Q2_xauusd": "PASS",
                "Q3_historical_m5": "PARTIAL",
                "Q4_live_or_streaming": "PASS",
                "Q5_timestamp_utc": "PASS",
                "Q6_ohlc_construction": "PASS",
                "Q7_spread": "PASS",
                "Q8_rate_limits": "PARTIAL",
                "Q9_auth_eligibility": "PARTIAL",
                "Q10_licensing": "PARTIAL",
                "Q11_reliability": "PASS",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Strong candle semantics but usage-priced; not Always Free sustainable.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "TwelveData_Basic",
            {
                "Q1_free_plan": "PARTIAL",
                "Q2_xauusd": "PARTIAL",
                "Q3_historical_m5": "PARTIAL",
                "Q4_live_or_streaming": "PARTIAL",
                "Q5_timestamp_utc": "PARTIAL",
                "Q6_ohlc_construction": "FAIL",
                "Q7_spread": "FAIL",
                "Q8_rate_limits": "PASS",
                "Q9_auth_eligibility": "PASS",
                "Q10_licensing": "PARTIAL",
                "Q11_reliability": "PARTIAL",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Free credits may cover M5 polling; spread/OHLC construction and metals free depth unclear.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "Finnhub_Free",
            {
                "Q1_free_plan": "PASS",
                "Q2_xauusd": "PARTIAL",
                "Q3_historical_m5": "FAIL",
                "Q4_live_or_streaming": "FAIL",
                "Q5_timestamp_utc": "PARTIAL",
                "Q6_ohlc_construction": "FAIL",
                "Q7_spread": "FAIL",
                "Q8_rate_limits": "PASS",
                "Q9_auth_eligibility": "PASS",
                "Q10_licensing": "PARTIAL",
                "Q11_reliability": "PARTIAL",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Forex/metals candles commonly paid-gated on free tier.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "biquote",
            {
                "Q1_free_plan": "PASS",
                "Q2_xauusd": "PASS",
                "Q3_historical_m5": "PARTIAL",
                "Q4_live_or_streaming": "PASS",
                "Q5_timestamp_utc": "FAIL",
                "Q6_ohlc_construction": "PARTIAL",
                "Q7_spread": "PARTIAL",
                "Q8_rate_limits": "PASS",
                "Q9_auth_eligibility": "PASS",
                "Q10_licensing": "FAIL",
                "Q11_reliability": "FAIL",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Marketing claims free MT5-sourced CFD feed; licensing/UTC/SLA/parity unverified.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "V2BOT",
            {
                "Q1_free_plan": "PARTIAL",
                "Q2_xauusd": "PASS",
                "Q3_historical_m5": "FAIL",
                "Q4_live_or_streaming": "PARTIAL",
                "Q5_timestamp_utc": "FAIL",
                "Q6_ohlc_construction": "FAIL",
                "Q7_spread": "FAIL",
                "Q8_rate_limits": "FAIL",
                "Q9_auth_eligibility": "PARTIAL",
                "Q10_licensing": "FAIL",
                "Q11_reliability": "FAIL",
                "Q12_mt5_parity_measured": "FAIL",
            },
            notes="Insufficient public depth on history, TZ, spread, license, reliability.",
            verdict="NOT_QUALIFIED",
        ),
        _row(
            "Local_MT5_reference_only",
            {
                "Q1_free_plan": "PASS",
                "Q2_xauusd": "PASS",
                "Q3_historical_m5": "PASS",
                "Q4_live_or_streaming": "PASS",
                "Q5_timestamp_utc": "PASS",
                "Q6_ohlc_construction": "PASS",
                "Q7_spread": "PASS",
                "Q8_rate_limits": "PASS",
                "Q9_auth_eligibility": "PASS",
                "Q10_licensing": "PARTIAL",
                "Q11_reliability": "PASS",
                "Q12_mt5_parity_measured": "PASS",
            },
            notes="Compatibility reference for thresholds; NOT a Linux ARM64 cloud runtime option.",
            verdict="REFERENCE_ONLY_NOT_CLOUD",
        ),
    ]
    any_selected = any(c["verdict"] == "QUALIFIED" for c in candidates)
    return {
        "criteria": CRITERIA,
        "candidates": candidates,
        "selected_provider": None,
        "any_qualified_for_cloud": False,
        "provider_blocker": not any_selected,
        "note": (
            "No provider selected. Public-doc review only; Q12 parity not measured. "
            "Never fabricate candles or inherit MT5 threshold validity."
        ),
    }
