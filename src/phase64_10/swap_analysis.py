"""Swap conflict investigation — preserve both observations; never force agreement."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    CONFLICTING,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    SWAP_MODE_POINTS,
    SWAP_ROLLOVER3DAYS,
    SWAP_SHORT_LIVE,
    UNKNOWN_FOR_EXECUTION,
    canonical_json_sha256,
)


def analyze_swap_conflict() -> dict[str, Any]:
    """
    Investigate -488.7 vs -644.8 without overwriting either.
    """
    obs = [
        {
            "id": "phase63_user_reported",
            "swap_long": SWAP_LONG_PHASE63,
            "swap_short": 0,
            "swap_type": "POINTS",
            "provenance": "USER_REPORTED_PHASE63_ACTIVE_XAUUSDM_SPEC",
            "observation_context": "Phase63 metadata intake (pre-live API verification)",
        },
        {
            "id": "phase64_7_live_mt5",
            "swap_long": SWAP_LONG_PHASE64_7,
            "swap_short": SWAP_SHORT_LIVE,
            "swap_mode_raw": SWAP_MODE_POINTS,
            "swap_type": "POINTS",
            "swap_rollover3days": SWAP_ROLLOVER3DAYS,
            "provenance": "LIVE_MT5_API_symbol_info",
            "observation_timestamp_utc": "2026-11-12T05:20:41Z",
        },
    ]

    delta = SWAP_LONG_PHASE64_7 - SWAP_LONG_PHASE63
    hypotheses = [
        {
            "hypothesis": "different_observation_dates_spec_change",
            "plausible": True,
            "proven": False,
            "note": "Broker can change swap points over time; no continuous history to prove when it changed",
        },
        {
            "hypothesis": "different_account_or_symbol_state",
            "plausible": True,
            "proven": False,
            "note": "Same symbol XAUUSDm claimed; account was Trial15 at live probe — Phase63 account state not API-verified then",
        },
        {
            "hypothesis": "contract_specification_change",
            "plausible": True,
            "proven": False,
            "note": "Both labeled POINTS; magnitude change without unit change suggests broker update",
        },
        {
            "hypothesis": "triple_swap_day_confusion",
            "plausible": False,
            "proven": False,
            "note": (
                f"Triple-swap weekday={SWAP_ROLLOVER3DAYS} (Wed) multiplies overnight charge; "
                "it does not rewrite symbol_info.swap_long itself. Unlikely to explain metadata conflict."
            ),
        },
        {
            "hypothesis": "quote_metadata_timing",
            "plausible": True,
            "proven": False,
            "note": "Live value is a point-in-time symbol_info read; Phase63 was a user-reported snapshot",
        },
        {
            "hypothesis": "source_semantics_mismatch",
            "plausible": True,
            "proven": False,
            "note": "User Spec UI vs API field could differ in rounding/display; both preserved",
        },
    ]

    # Conflict status
    conflict_status = "still_unresolved"
    if any(h["proven"] for h in hypotheses):
        conflict_status = "resolved"
    elif any(h["plausible"] for h in hypotheses):
        conflict_status = "explainable_but_not_reconciled"

    out = {
        "field": "swap_long",
        "observations": obs,
        "delta": delta,
        "overwrite": False,
        "interchangeable": False,
        "conflict_status": conflict_status,
        "status_for_execution": UNKNOWN_FOR_EXECUTION,
        "component_status": CONFLICTING,
        "hypotheses": hypotheses,
        "swap_short_live": SWAP_SHORT_LIVE,
        "conclusion": (
            "Both original values preserved. Difference is explainable as broker/spec/time/source "
            "divergence but not reconciled to a single verified execution value. "
            "swap = UNKNOWN_FOR_EXECUTION."
        ),
        "safe_for_calculations": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
