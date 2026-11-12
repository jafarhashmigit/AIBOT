"""Historical bid/ask provider investigation (docs/evidence only; no downloads)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase32.constants import PROJECT_ROOT


def run_provider_investigation() -> dict[str, Any]:
    """Reuse Phase24 qualification evidence; do not download large datasets."""
    p24 = PROJECT_ROOT / "reports" / "phase24" / "provider_qualification.json"
    phase24 = None
    if p24.exists():
        phase24 = json.loads(p24.read_text(encoding="utf-8"))

    dukas = {
        "provider": "Dukascopy_public_historical",
        "status": "NOT_YET_QUALIFIED",
        "evidence_basis": [
            "phase24_provider_qualification",
            "third_party_docs_and_community_tools",
            "no_phase32_download",
        ],
        "findings": {
            "XAUUSD_documented": True,
            "historical_m5_documented": True,
            "bid_ask_documented": True,
            "utc_documented": True,
            "genuinely_free_for_research": "PARTIAL_with_redistribution_caveats",
            "account_required_for_bulk": "unclear_from_docs_alone",
            "actual_bars_downloaded_this_phase": False,
            "mt5_parity_measured": False,
            "licensing": "personal/research; redistribution restricted (per Phase24 review)",
            "local_processing_possible_in_principle": True,
            "paid_infrastructure_required": False,
        },
        "phase24_verdict": "NOT_QUALIFIED",
        "note": (
            "Do not assume qualification from documentation alone. "
            "Phase24 did not download/validate Dukascopy bars. Phase32 also does not download."
        ),
    }

    parity_protocol = {
        "instrument": "XAUUSD",
        "timestamp_basis": "UTC",
        "candle_boundary": "M5 open timestamps aligned",
        "bid_ask_convention": "explicit bid and ask (or mid+spread) documented",
        "price_precision": "0.01 USD point",
        "required_comparisons": [
            "spread_distribution_vs_MT5_floored_spread",
            "missing_candle_alignment",
            "multi_day_OHLC_parity",
            "DST_transition_checks",
            "session_gap_alignment",
        ],
        "pass_gate": "measured_parity_report_required_before_HISTORICAL_BID_ASK_VERIFIED",
        "mt5_parity_claimed_without_data": False,
    }

    return {
        "phase24_report_present": p24.exists(),
        "phase24_selected_provider": None if not phase24 else phase24.get("selected_provider"),
        "dukascopy": dukas,
        "other_free_providers": "See Phase24 — none qualified with measured parity",
        "future_parity_protocol": parity_protocol,
        "downloads_performed": False,
        "mt5_connected": False,
        "paid_services_used": False,
    }
