"""Part B — authorized data acquisition options (design only; not implemented)."""

from __future__ import annotations

from typing import Any


def authorized_acquisition_options() -> list[dict[str, Any]]:
    return [
        {
            "option_id": "A",
            "name": "Written permission and authorized historical signal export",
            "description": (
                "Channel owner grants written permission and supplies or authorizes "
                "an export of historical XAUUSD signals for AIBOT research/backtesting."
            ),
            "feasibility": "HIGHEST_COMPLIANCE_PATH",
            "limitations": [
                "Requires successful owner contact and negotiation.",
                "Export completeness (edits/deletes) may be incomplete.",
                "Format and field quality vary by provider.",
            ],
            "required_consent": [
                "Historical access",
                "Storage/retention",
                "Backtesting/performance evaluation",
                "Edit/delete handling",
                "Derived statistics sharing scope",
                "Separate AI/ML consent if applicable (default: not requested)",
            ],
            "phase15a_status": "NOT_OBTAINED",
            "implement_now": False,
        },
        {
            "option_id": "B",
            "name": "Provider-supplied CSV/JSON export with explicit research permission",
            "description": (
                "Owner provides a structured CSV/JSON file of signals with an explicit "
                "license for research and independent backtesting."
            ),
            "feasibility": "PREFERRED_WHEN_AVAILABLE",
            "limitations": [
                "Depends on provider tooling/willingness.",
                "May omit raw message IDs or edit history.",
                "Must still exclude AI/ML use unless separately granted.",
            ],
            "required_consent": [
                "Explicit research/backtest license covering the export file",
                "Storage/retention terms",
                "Sharing of derived metrics",
                "AI/ML carve-out or prohibition",
            ],
            "phase15a_status": "NOT_OBTAINED",
            "implement_now": False,
        },
        {
            "option_id": "C",
            "name": "Manually supplied small authorized sample",
            "description": (
                "Owner (or authorized agent) manually supplies a small synthetic-or-real "
                "sample explicitly authorized for schema validation and methodology dry-run. "
                "Phase 15A uses synthetic fixtures only; real samples require consent."
            ),
            "feasibility": "USEFUL_FOR_SCHEMA_PILOT",
            "limitations": [
                "Not sufficient for provider ranking or profitability claims.",
                "Selection bias if owner cherry-picks.",
                "Still permission-gated for any real messages.",
            ],
            "required_consent": [
                "Purpose-limited use of the sample",
                "No bulk scrape implied",
                "No AI/ML training unless separately granted",
            ],
            "phase15a_status": "SYNTHETIC_FIXTURES_ONLY",
            "implement_now": False,
        },
        {
            "option_id": "D",
            "name": "Future signal forwarding to a private research bot",
            "description": (
                "With channel-owner authorization and Telegram Bot ToS compliance, "
                "forward future signals to a private research bot for prospective capture."
            ),
            "feasibility": "FORWARD_LOOKING_ONLY",
            "limitations": [
                "Does not unlock historical archives via Bot API (~24h update window).",
                "Bot must be authorized by owner; public scrape still forbidden.",
                "Requires ongoing consent and retention policy.",
                "Prospective-only; cannot reconstruct past performance from forwarding alone.",
            ],
            "required_consent": [
                "Owner authorization to add/forward to research bot",
                "Storage/retention for forwarded messages",
                "Backtesting of prospectively captured signals",
                "AI/ML prohibition unless separately granted",
            ],
            "phase15a_status": "NOT_IMPLEMENTED_NOT_AUTHORIZED",
            "implement_now": False,
        },
    ]


def access_feasibility_report() -> dict[str, Any]:
    options = authorized_acquisition_options()
    return {
        "options": options,
        "any_option_authorized_now": False,
        "recommended_next_step_if_pursued": "A_OR_B_WITH_WRITTEN_PERMISSION",
        "scraping_allowed": False,
        "bot_api_historical_harvest_allowed": False,
        "paid_subscription_used": False,
        "acquisition_mechanism_implemented": False,
    }
