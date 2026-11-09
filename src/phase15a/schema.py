"""Part C — normalized external signal schema (synthetic examples only)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "phase15a_signal_schema_v1"

REQUIRED_FIELDS = (
    "provider_id",
    "signal_id",
    "original_message_reference",
    "published_at_utc",
    "last_updated_at_utc",
    "instrument",
    "direction",
    "entry_type",
    "entry_min",
    "entry_max",
    "stop_loss",
    "take_profit_levels",
    "status",
    "update_reference",
    "permission_reference",
    "data_provenance",
    "completeness_status",
)

ALLOWED_DIRECTIONS = ("BUY", "SELL", "UNKNOWN")
ALLOWED_ENTRY_TYPES = ("MARKET", "LIMIT_ZONE", "UNKNOWN")
ALLOWED_STATUSES = (
    "OPEN",
    "MODIFIED",
    "CANCELLED",
    "UNFILLED",
    "AMBIGUOUS",
    "INCOMPLETE",
    "CLOSED_UNKNOWN",
)
ALLOWED_COMPLETENESS = ("COMPLETE", "PARTIAL", "AMBIGUOUS", "INCOMPLETE")
ALLOWED_PROVENANCE = (
    "OWNER_EXPORT",
    "AUTHORIZED_SAMPLE",
    "AUTHORIZED_FORWARD",
    "SYNTHETIC_FIXTURE",
)


def empty_signal_template() -> dict[str, Any]:
    return {
        "provider_id": "",
        "signal_id": "",
        "original_message_reference": {
            "channel_handle": "",
            "message_id": None,
            "export_row_id": None,
        },
        "published_at_utc": "",
        "last_updated_at_utc": "",
        "instrument": "XAUUSD",
        "direction": "UNKNOWN",
        "entry_type": "UNKNOWN",
        "entry_min": None,
        "entry_max": None,
        "stop_loss": None,
        "take_profit_levels": [],
        "status": "INCOMPLETE",
        "update_reference": {
            "parent_signal_id": None,
            "update_kind": None,
            "prior_stop_loss": None,
            "prior_take_profit_levels": None,
        },
        "permission_reference": {
            "permission_id": None,
            "granted_by": None,
            "granted_at_utc": None,
            "covers_ai_ml": False,
        },
        "data_provenance": "SYNTHETIC_FIXTURE",
        "completeness_status": "INCOMPLETE",
    }


def synthetic_signal_fixtures() -> list[dict[str, Any]]:
    """Synthetic examples only — not real provider messages."""
    fixtures: list[dict[str, Any]] = []

    buy_market = empty_signal_template()
    buy_market.update(
        {
            "provider_id": "synthetic_alpha",
            "signal_id": "SYN-001",
            "original_message_reference": {
                "channel_handle": "@synthetic_alpha",
                "message_id": "syn-msg-1",
                "export_row_id": "exp-1",
            },
            "published_at_utc": "2026-01-10T12:00:00Z",
            "last_updated_at_utc": "2026-01-10T12:00:00Z",
            "direction": "BUY",
            "entry_type": "MARKET",
            "entry_min": 2650.0,
            "entry_max": 2650.0,
            "stop_loss": 2640.0,
            "take_profit_levels": [2655.0, 2660.0, 2665.0],
            "status": "OPEN",
            "permission_reference": {
                "permission_id": "SYN-PERM-NONE",
                "granted_by": None,
                "granted_at_utc": None,
                "covers_ai_ml": False,
            },
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "COMPLETE",
        }
    )
    fixtures.append(buy_market)

    sell_zone = empty_signal_template()
    sell_zone.update(
        {
            "provider_id": "synthetic_beta",
            "signal_id": "SYN-002",
            "original_message_reference": {
                "channel_handle": "@synthetic_beta",
                "message_id": "syn-msg-2",
                "export_row_id": "exp-2",
            },
            "published_at_utc": "2026-01-11T08:30:00Z",
            "last_updated_at_utc": "2026-01-11T08:30:00Z",
            "direction": "SELL",
            "entry_type": "LIMIT_ZONE",
            "entry_min": 2668.0,
            "entry_max": 2672.0,
            "stop_loss": 2680.0,
            "take_profit_levels": [2660.0, 2650.0],
            "status": "OPEN",
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "COMPLETE",
        }
    )
    fixtures.append(sell_zone)

    modified_sl = deepcopy(buy_market)
    modified_sl.update(
        {
            "signal_id": "SYN-001-U1",
            "last_updated_at_utc": "2026-01-10T14:00:00Z",
            "stop_loss": 2645.0,
            "status": "MODIFIED",
            "update_reference": {
                "parent_signal_id": "SYN-001",
                "update_kind": "STOP_LOSS_MODIFIED",
                "prior_stop_loss": 2640.0,
                "prior_take_profit_levels": [2655.0, 2660.0, 2665.0],
            },
            "completeness_status": "COMPLETE",
        }
    )
    fixtures.append(modified_sl)

    cancelled = empty_signal_template()
    cancelled.update(
        {
            "provider_id": "synthetic_gamma",
            "signal_id": "SYN-003",
            "published_at_utc": "2026-01-12T09:00:00Z",
            "last_updated_at_utc": "2026-01-12T09:15:00Z",
            "direction": "BUY",
            "entry_type": "LIMIT_ZONE",
            "entry_min": 2640.0,
            "entry_max": 2642.0,
            "stop_loss": 2630.0,
            "take_profit_levels": [2650.0],
            "status": "CANCELLED",
            "update_reference": {
                "parent_signal_id": "SYN-003",
                "update_kind": "CANCELLED",
                "prior_stop_loss": 2630.0,
                "prior_take_profit_levels": [2650.0],
            },
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "COMPLETE",
        }
    )
    fixtures.append(cancelled)

    ambiguous = empty_signal_template()
    ambiguous.update(
        {
            "provider_id": "synthetic_delta",
            "signal_id": "SYN-004",
            "published_at_utc": "2026-01-13T11:00:00Z",
            "last_updated_at_utc": "2026-01-13T11:00:00Z",
            "direction": "UNKNOWN",
            "entry_type": "UNKNOWN",
            "entry_min": None,
            "entry_max": None,
            "stop_loss": None,
            "take_profit_levels": [],
            "status": "AMBIGUOUS",
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "AMBIGUOUS",
        }
    )
    fixtures.append(ambiguous)

    unfilled = empty_signal_template()
    unfilled.update(
        {
            "provider_id": "synthetic_epsilon",
            "signal_id": "SYN-005",
            "published_at_utc": "2026-01-14T07:00:00Z",
            "last_updated_at_utc": "2026-01-14T16:00:00Z",
            "direction": "SELL",
            "entry_type": "LIMIT_ZONE",
            "entry_min": 2700.0,
            "entry_max": 2705.0,
            "stop_loss": 2715.0,
            "take_profit_levels": [2680.0],
            "status": "UNFILLED",
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "COMPLETE",
        }
    )
    fixtures.append(unfilled)

    incomplete = empty_signal_template()
    incomplete.update(
        {
            "provider_id": "synthetic_zeta",
            "signal_id": "SYN-006",
            "published_at_utc": "2026-01-15T10:00:00Z",
            "last_updated_at_utc": "2026-01-15T10:00:00Z",
            "direction": "BUY",
            "entry_type": "MARKET",
            "entry_min": 2655.0,
            "entry_max": 2655.0,
            "stop_loss": None,
            "take_profit_levels": [],
            "status": "INCOMPLETE",
            "data_provenance": "SYNTHETIC_FIXTURE",
            "completeness_status": "INCOMPLETE",
        }
    )
    fixtures.append(incomplete)

    return fixtures


def validate_signal_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing_field:{field}")
    if record.get("direction") not in ALLOWED_DIRECTIONS:
        errors.append("invalid_direction")
    if record.get("entry_type") not in ALLOWED_ENTRY_TYPES:
        errors.append("invalid_entry_type")
    if record.get("status") not in ALLOWED_STATUSES:
        errors.append("invalid_status")
    if record.get("completeness_status") not in ALLOWED_COMPLETENESS:
        errors.append("invalid_completeness_status")
    if record.get("data_provenance") not in ALLOWED_PROVENANCE:
        errors.append("invalid_data_provenance")
    tps = record.get("take_profit_levels")
    if tps is not None and not isinstance(tps, list):
        errors.append("take_profit_levels_not_list")
    return errors


def schema_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "required_fields": list(REQUIRED_FIELDS),
        "allowed_directions": list(ALLOWED_DIRECTIONS),
        "allowed_entry_types": list(ALLOWED_ENTRY_TYPES),
        "allowed_statuses": list(ALLOWED_STATUSES),
        "allowed_completeness": list(ALLOWED_COMPLETENESS),
        "allowed_provenance": list(ALLOWED_PROVENANCE),
        "supports": [
            "BUY and SELL",
            "Market entry and entry zones",
            "Multiple take-profit levels",
            "Modified stop loss",
            "Cancelled signals",
            "Ambiguous signals",
            "Unfilled signals",
            "Incomplete records",
            "Original timestamps and provenance",
        ],
        "synthetic_fixture_count": len(synthetic_signal_fixtures()),
        "real_provider_signals_included": False,
    }
