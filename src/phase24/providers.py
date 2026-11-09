"""Provider qualification matrix with evidence grades (docs + measured)."""

from __future__ import annotations

from typing import Any

from phase24.parity import run_algospecial_parity

CRITERIA = [
    "XAUUSD",
    "free_plan",
    "historical_m5",
    "live_streaming",
    "bid_ask_or_spread",
    "utc_timestamps",
    "rate_limits",
    "api_restrictions",
    "licensing",
    "retention_depth",
    "actual_data_validation",
]


def _score(**kwargs: str) -> dict[str, str]:
    return kwargs


def provider_qualification() -> dict[str, Any]:
    algo_parity = run_algospecial_parity()
    algo_pass = algo_parity.get("parity_result") == "PASS"

    candidates: list[dict[str, Any]] = [
        {
            "provider": "AlgoSpecial",
            "evidence_basis": ["official_docs", "live_preview_sample_2026-02-16_17", "mt5_parity_measured"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="PARTIAL",  # preview caps; full history paid downloads
                historical_m5="PARTIAL",  # free preview 2k rows / 31d
                live_streaming="FAIL",  # historical query API; continuous live not evidenced
                bid_ask_or_spread="PARTIAL",  # Spread field present; units mismatch vs MT5
                utc_timestamps="FAIL",  # docs: broker server time, not UTC
                rate_limits="PASS",  # 60/min, 1000/day
                api_restrictions="PASS",  # no key for preview
                licensing="PARTIAL",  # research OK; no resell as data service; as-is
                retention_depth="PARTIAL",
                actual_data_validation="FAIL" if not algo_pass else "PASS",
            ),
            "measured_parity": {
                "result": algo_parity.get("parity_result"),
                "common_timestamps": algo_parity.get("common_timestamps"),
                "coverage_of_mt5": algo_parity.get("coverage_of_mt5"),
                "close_abs_diff_p50": (algo_parity.get("ohlc_abs_diff") or {}).get("close", {}).get("p50"),
                "close_abs_diff_max": (algo_parity.get("ohlc_abs_diff") or {}).get("close", {}).get("max"),
                "spread_medians": algo_parity.get("spread_and_cost"),
            },
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
        },
        {
            "provider": "Dukascopy_public_historical",
            "evidence_basis": ["third_party_docs_and_community_tools", "no_phase24_download"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="PARTIAL",  # free historical feed; terms/redistribution caveats
                historical_m5="PASS",  # docs: M5 from 2003
                live_streaming="FAIL",  # historical archive, not cloud live stream contract
                bid_ask_or_spread="PASS",  # bid/ask sides documented
                utc_timestamps="PASS",  # UTC documented by tooling/docs reviewed
                rate_limits="PARTIAL",  # informal; 503s reported by community tools
                api_restrictions="PARTIAL",  # no key but binary feed protocol
                licensing="PARTIAL",  # personal/research; redistribution restricted
                retention_depth="PASS",
                actual_data_validation="FAIL",  # not measured this phase
            ),
            "measured_parity": None,
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
            "note": "Promising historical candidate; cannot qualify without Phase 24 binary download + MT5 parity.",
        },
        {
            "provider": "TickFeed",
            "evidence_basis": ["official_docs"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="FAIL",
                historical_m5="PARTIAL",
                live_streaming="PASS",
                bid_ask_or_spread="PASS",
                utc_timestamps="PASS",
                rate_limits="PARTIAL",
                api_restrictions="PARTIAL",
                licensing="PARTIAL",
                retention_depth="PARTIAL",
                actual_data_validation="FAIL",
            ),
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
        },
        {
            "provider": "TwelveData_Basic",
            "evidence_basis": ["official_docs"],
            "scores": _score(
                XAUUSD="PARTIAL",  # trial/commodity; Grow+ for commodity exchange page
                free_plan="PARTIAL",
                historical_m5="PARTIAL",
                live_streaming="PARTIAL",
                bid_ask_or_spread="FAIL",
                utc_timestamps="PARTIAL",  # timezone=UTC supported when authenticated
                rate_limits="PASS",
                api_restrictions="PARTIAL",  # API key / account
                licensing="PARTIAL",
                retention_depth="PARTIAL",
                actual_data_validation="FAIL",
            ),
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
        },
        {
            "provider": "Finnhub_Free",
            "evidence_basis": ["official_docs_community"],
            "scores": _score(
                XAUUSD="PARTIAL",
                free_plan="PASS",
                historical_m5="FAIL",
                live_streaming="FAIL",
                bid_ask_or_spread="FAIL",
                utc_timestamps="PARTIAL",
                rate_limits="PASS",
                api_restrictions="PARTIAL",
                licensing="PARTIAL",
                retention_depth="FAIL",
                actual_data_validation="FAIL",
            ),
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
        },
        {
            "provider": "biquote",
            "evidence_basis": ["marketing_site"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="PASS",
                historical_m5="PARTIAL",
                live_streaming="PARTIAL",
                bid_ask_or_spread="PARTIAL",
                utc_timestamps="FAIL",
                rate_limits="PARTIAL",
                api_restrictions="PASS",
                licensing="FAIL",
                retention_depth="PARTIAL",
                actual_data_validation="FAIL",
            ),
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
            "note": "Not qualified on marketing claims alone.",
        },
        {
            "provider": "V2BOT",
            "evidence_basis": ["official_apidocs_page"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="PARTIAL",
                historical_m5="FAIL",
                live_streaming="PARTIAL",
                bid_ask_or_spread="FAIL",
                utc_timestamps="FAIL",
                rate_limits="FAIL",
                api_restrictions="PARTIAL",
                licensing="FAIL",
                retention_depth="FAIL",
                actual_data_validation="FAIL",
            ),
            "verdict": "NOT_QUALIFIED",
            "qualified": False,
        },
        {
            "provider": "Local_MT5_reference",
            "evidence_basis": ["project_dataset"],
            "scores": _score(
                XAUUSD="PASS",
                free_plan="PASS",
                historical_m5="PASS",
                live_streaming="PASS",
                bid_ask_or_spread="PASS",
                utc_timestamps="PASS",
                rate_limits="PASS",
                api_restrictions="FAIL",  # Windows terminal; not cloud
                licensing="PARTIAL",
                retention_depth="PASS",
                actual_data_validation="PASS",
            ),
            "verdict": "REFERENCE_ONLY_NOT_CLOUD",
            "qualified": False,
        },
    ]

    any_qualified = any(c.get("qualified") for c in candidates)
    # Partial: docs-promising but no measured pass
    partial = any(
        c["provider"] == "Dukascopy_public_historical"
        and c["scores"].get("historical_m5") == "PASS"
        and c["scores"].get("actual_data_validation") == "FAIL"
        for c in candidates
    )

    if any_qualified:
        decision = "PROVIDER_QUALIFIED"
    elif partial and not algo_pass:
        # Empirical free preview failed; Dukascopy untested → still blocked for cloud use
        decision = "PROVIDER_BLOCKED"
    else:
        decision = "PROVIDER_BLOCKED"

    return {
        "criteria": CRITERIA,
        "candidates": candidates,
        "selected_provider": None,
        "any_qualified": False,
        "final_decision": decision,
        "blockers": [
            "AlgoSpecial measured MT5 parity FAIL (median abs close diff >> $0.50; spread scale mismatch; non-UTC stamps).",
            "No free provider completed live/streaming + UTC + spread + licensing + measured parity.",
            "Dukascopy historical looks promising on docs but Phase 24 did not download/validate actual bars.",
            "Twelve Data / Finnhub / TickFeed / biquote / V2BOT fail free-cloud mandatory gates or lack measured validation.",
        ],
        "note": "Do not invent a cloud provider. Thresholds not recalibrated.",
    }
