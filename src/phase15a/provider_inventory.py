"""Part A — provider feasibility inventory (no channel scraping).

Evidence is limited to:
- Prior third-party public web references gathered without opening t.me channel pages
  during this phase (when available).
- Explicit UNVERIFIED markers where channel contents were not inspected.

No bulk message content is collected or stored.
"""

from __future__ import annotations

from typing import Any

from phase15a.constants import PROVIDERS


def _base(
    provider_id: str,
    *,
    public_channel_availability: str,
    xauusd_signals_appear_offered: str,
    structured_entry_sl_tp: str,
    free_or_restricted: str,
    historical_posts_visibly_accessible: str,
    publication_timestamps_available: str,
    edits_and_trade_updates_documented: str,
    owner_permission_contact_available: str,
    data_access_limitations: list[str],
    evidence_basis: list[str],
    outcome: str,
    notes: str,
) -> dict[str, Any]:
    meta = next(p for p in PROVIDERS if p["provider_id"] == provider_id)
    return {
        **meta,
        "public_channel_availability": public_channel_availability,
        "xauusd_signals_appear_offered": xauusd_signals_appear_offered,
        "structured_entry_sl_tp": structured_entry_sl_tp,
        "free_or_restricted": free_or_restricted,
        "historical_posts_visibly_accessible": historical_posts_visibly_accessible,
        "publication_timestamps_available": publication_timestamps_available,
        "edits_and_trade_updates_documented": edits_and_trade_updates_documented,
        "owner_permission_contact_available": owner_permission_contact_available,
        "data_access_limitations": data_access_limitations,
        "evidence_basis": evidence_basis,
        "phase15a_outcome": outcome,
        "historical_coverage_claimed": False,
        "messages_collected": 0,
        "notes": notes,
    }


def build_provider_inventory() -> list[dict[str, Any]]:
    common_limits = [
        "Telegram ToS prohibit scraping/harvesting for AI/ML datasets without explicit user consent.",
        "Public visibility ≠ research/archive/backtest authorization.",
        "No AIBOT Bot API or client API harvest attempted in Phase 15A.",
        "No paid subscription purchased.",
        "Historical coverage not verified; channel pages not scraped.",
    ]

    return [
        _base(
            "vasilytrader",
            public_channel_availability="REPORTED_PUBLIC_BY_THIRD_PARTY",
            xauusd_signals_appear_offered="LIKELY_YES_UNVERIFIED_IN_CHANNEL",
            structured_entry_sl_tp="UNKNOWN_UNSTRUCTURED_LIKELY",
            free_or_restricted="REPORTED_FREE_PUBLIC_CHANNEL",
            historical_posts_visibly_accessible="UNVERIFIED_NO_CHANNEL_INSPECTION",
            publication_timestamps_available="TYPICAL_FOR_TELEGRAM_UNVERIFIED",
            edits_and_trade_updates_documented="UNVERIFIED",
            owner_permission_contact_available="HANDLE_ONLY_NO_WRITTEN_PERMISSION",
            data_access_limitations=common_limits
            + ["No written owner permission on file."],
            evidence_basis=[
                "Third-party articles/directories referencing @vasilytrading as a public trading signal channel.",
                "No t.me page fetch or message harvest in Phase 15A.",
            ],
            outcome="PERMISSION_REQUIRED",
            notes=(
                "Public mentions suggest gold/FX signal activity, but Phase 15A did not "
                "inspect channel messages. Treat as permission-gated."
            ),
        ),
        _base(
            "anabelsignals",
            public_channel_availability="REPORTED_PUBLIC_BY_THIRD_PARTY",
            xauusd_signals_appear_offered="LIKELY_YES_UNVERIFIED_IN_CHANNEL",
            structured_entry_sl_tp="UNKNOWN_UNSTRUCTURED_LIKELY",
            free_or_restricted="REPORTED_FREE_PUBLIC_CHANNEL",
            historical_posts_visibly_accessible="UNVERIFIED_NO_CHANNEL_INSPECTION",
            publication_timestamps_available="TYPICAL_FOR_TELEGRAM_UNVERIFIED",
            edits_and_trade_updates_documented="UNVERIFIED",
            owner_permission_contact_available="HANDLE_ONLY_NO_WRITTEN_PERMISSION",
            data_access_limitations=common_limits
            + ["No written owner permission on file."],
            evidence_basis=[
                "Third-party references to @anabelsignals as a signal channel.",
                "No t.me page fetch or message harvest in Phase 15A.",
            ],
            outcome="PERMISSION_REQUIRED",
            notes="XAUUSD offer and structure remain unverified without authorized access.",
        ),
        _base(
            "goldtradersunny",
            public_channel_availability="REPORTED_PUBLIC_BY_THIRD_PARTY",
            xauusd_signals_appear_offered="LIKELY_YES_NAME_SUGGESTS_GOLD",
            structured_entry_sl_tp="UNKNOWN_UNSTRUCTURED_LIKELY",
            free_or_restricted="REPORTED_FREE_PUBLIC_CHANNEL",
            historical_posts_visibly_accessible="UNVERIFIED_NO_CHANNEL_INSPECTION",
            publication_timestamps_available="TYPICAL_FOR_TELEGRAM_UNVERIFIED",
            edits_and_trade_updates_documented="UNVERIFIED",
            owner_permission_contact_available="HANDLE_ONLY_NO_WRITTEN_PERMISSION",
            data_access_limitations=common_limits
            + ["No written owner permission on file."],
            evidence_basis=[
                "Third-party references to @goldtradersunny.",
                "Display name suggests gold focus; channel contents not inspected.",
            ],
            outcome="PERMISSION_REQUIRED",
            notes="Do not claim structured SL/TP or historical coverage without authorized samples.",
        ),
        _base(
            "fxpremiere",
            public_channel_availability="UNVERIFIED",
            xauusd_signals_appear_offered="UNVERIFIED",
            structured_entry_sl_tp="UNVERIFIED",
            free_or_restricted="UNVERIFIED_MAY_BE_TRIAL_OR_RESTRICTED",
            historical_posts_visibly_accessible="UNVERIFIED_NO_CHANNEL_INSPECTION",
            publication_timestamps_available="UNVERIFIED",
            edits_and_trade_updates_documented="UNVERIFIED",
            owner_permission_contact_available="HANDLE_ONLY_NO_WRITTEN_PERMISSION",
            data_access_limitations=common_limits
            + [
                "Handle name suggests a trial/signals group; access model unknown.",
                "Insufficient public evidence in Phase 15A without channel inspection.",
            ],
            evidence_basis=[
                "Handle @forexsignalstrialgroup listed in audit request only.",
                "No authorized channel inspection; no third-party confirmation relied upon as proof of XAUUSD coverage.",
            ],
            outcome="INSUFFICIENT_ACCESS",
            notes=(
                "Public availability and XAUUSD signal presence not established under "
                "Phase 15A no-scrape rules. Permission still required if access later obtained."
            ),
        ),
        _base(
            "unitedkings",
            public_channel_availability="UNVERIFIED",
            xauusd_signals_appear_offered="UNVERIFIED",
            structured_entry_sl_tp="UNVERIFIED",
            free_or_restricted="UNVERIFIED",
            historical_posts_visibly_accessible="UNVERIFIED_NO_CHANNEL_INSPECTION",
            publication_timestamps_available="UNVERIFIED",
            edits_and_trade_updates_documented="UNVERIFIED",
            owner_permission_contact_available="HANDLE_ONLY_NO_WRITTEN_PERMISSION",
            data_access_limitations=common_limits
            + ["Insufficient public evidence without channel inspection."],
            evidence_basis=[
                "Handle @unitedkings1 listed in audit request only.",
                "No authorized channel inspection in Phase 15A.",
            ],
            outcome="INSUFFICIENT_ACCESS",
            notes="Treat as inaccessible for research until availability and permission are established.",
        ),
    ]


def inventory_summary(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows or build_provider_inventory()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["phase15a_outcome"]] = counts.get(r["phase15a_outcome"], 0) + 1
    return {
        "provider_count": len(rows),
        "outcome_counts": counts,
        "authorized_research_path_identified": False,
        "any_messages_collected": False,
        "historical_coverage_verified": False,
    }
