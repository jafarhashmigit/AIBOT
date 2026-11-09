"""Live-feed assessment — separate from historical bi5 qualification."""

from __future__ import annotations

from typing import Any


def assess_live_feed() -> dict[str, Any]:
    """Document-only assessment. No live sockets opened in Phase 25.

    Historical datafeed.dukascopy.com bi5 archives must not be assumed to imply
    an officially supported unattended cloud live stream.
    """
    return {
        "status": "DUKASCOPY_LIVE_UNAVAILABLE",
        "historical_implies_live": False,
        "findings": [
            {
                "topic": "historical_datafeed",
                "evidence": "https://datafeed.dukascopy.com/datafeed/.../HHh_ticks.bi5",
                "result": "Hourly historical tick archives (LZMA). Empty body for closed hours. Not a streaming API.",
            },
            {
                "topic": "jforex_api_live",
                "evidence": "https://www.dukascopy.com/swiss/english/forex/api/jforex-api/",
                "result": (
                    "JForex API supports strategies with live data via authenticated sessions to Dukascopy "
                    "trade servers. Requires client/SDK usage; not verified in Phase 25 (no account, no socket)."
                ),
            },
            {
                "topic": "demo_vs_live_ticks",
                "evidence": "Dukascopy wiki Overview Historical Data",
                "result": "DEMO realtime ticks differ from LIVE; historical on DEMO comes from LIVE environment.",
            },
            {
                "topic": "licensing",
                "evidence": "JForex API EULA / website TCU excerpts reviewed via public docs",
                "result": (
                    "Personal, non-commercial default; commercial use needs supplementary agreement. "
                    "Website TCU language restricts redistribution, database construction, and scraping-style acquisition."
                ),
            },
            {
                "topic": "latency_update_frequency_stability_reconnect",
                "evidence": None,
                "result": "NOT MEASURED — no live connection established in Phase 25.",
            },
        ],
        "latency": None,
        "update_frequency": None,
        "connection_stability": None,
        "reconnection_support": None,
        "licensing_restrictions": (
            "Non-commercial/personal default for JForex API content; redistribution/database/scraping "
            "restrictions appear in public terms summaries. Cloud Always Free commercial shadow use is not cleared."
        ),
        "verified_official_unattended_live_xauusd_feed": False,
        "note": "Live capability BLOCKED / UNAVAILABLE for cloud qualification based on Phase 25 evidence.",
    }
