"""Schema compatibility analysis for synthetic provider styles vs schema v1."""

from __future__ import annotations

from typing import Any

from phase15a.schema import REQUIRED_FIELDS, SCHEMA_VERSION
from phase15b.mappers import map_all_fixtures, validate_mapped


def field_mapping_vasilytrader_style() -> list[dict[str, str]]:
    return [
        {"source_field": "side", "target_field": "direction", "status": "direct"},
        {"source_field": "entry", "target_field": "entry_min/entry_max", "status": "direct_exact_as_market"},
        {"source_field": "(implicit exact entry)", "target_field": "entry_type", "status": "derived_MARKET"},
        {"source_field": "sl", "target_field": "stop_loss", "status": "direct"},
        {"source_field": "tp", "target_field": "take_profit_levels[0]", "status": "wrapped_to_list"},
        {"source_field": "published_at", "target_field": "published_at_utc", "status": "direct"},
        {"source_field": "updated_at", "target_field": "last_updated_at_utc", "status": "optional_source"},
        {"source_field": "msg_id", "target_field": "original_message_reference.message_id", "status": "direct"},
        {"source_field": "fixture_id", "target_field": "signal_id", "status": "direct"},
        {"source_field": "event/prior_sl", "target_field": "status/update_reference", "status": "derived"},
        {"source_field": "(absent)", "target_field": "permission_reference", "status": "required_injected_synthetic"},
        {"source_field": "(absent)", "target_field": "data_provenance", "status": "required_injected_SYNTHETIC_FIXTURE"},
        {"source_field": "(absent multi-TP)", "target_field": "take_profit_levels[1+]", "status": "not_in_source_format"},
        {"source_field": "(absent zone)", "target_field": "LIMIT_ZONE entry", "status": "not_in_source_format"},
    ]


def field_mapping_anabelsignals_style() -> list[dict[str, str]]:
    return [
        {"source_field": "direction", "target_field": "direction", "status": "direct"},
        {"source_field": "entry (scalar)", "target_field": "entry_min/entry_max", "status": "direct_as_market"},
        {"source_field": "entry {min,max}", "target_field": "entry_min/entry_max + LIMIT_ZONE", "status": "supported"},
        {"source_field": "sl", "target_field": "stop_loss", "status": "direct"},
        {"source_field": "tps[]", "target_field": "take_profit_levels", "status": "direct"},
        {"source_field": "published_at", "target_field": "published_at_utc", "status": "direct"},
        {"source_field": "updates[].at", "target_field": "last_updated_at_utc", "status": "direct_on_child"},
        {"source_field": "updates[].kind=sl_modified", "target_field": "status=MODIFIED + update_reference", "status": "supported"},
        {"source_field": "updates[].kind=cancelled", "target_field": "status=CANCELLED + update_reference", "status": "supported"},
        {"source_field": "msg_id / update_id", "target_field": "original_message_reference", "status": "direct"},
        {"source_field": "(absent)", "target_field": "permission_reference", "status": "required_injected_synthetic"},
        {"source_field": "(absent)", "target_field": "data_provenance", "status": "required_injected_SYNTHETIC_FIXTURE"},
        {"source_field": "updates[] unknown kind", "target_field": "status=AMBIGUOUS", "status": "ambiguous"},
    ]


def missing_ambiguous_optional() -> dict[str, Any]:
    return {
        "target_schema": SCHEMA_VERSION,
        "required_schema_fields": list(REQUIRED_FIELDS),
        "vasilytrader_style": {
            "missing_in_source": [
                "permission_reference (must be supplied by AIBOT ingestion gate)",
                "data_provenance (must be supplied by AIBOT ingestion gate)",
                "completeness_status (derived)",
                "entry_type (derived; format assumes exact entry → MARKET)",
                "native multi-TP list (single tp only)",
                "native entry zone fields",
            ],
            "ambiguous_in_source": [
                "Whether exact entry means MARKET fill or limit-at-price (mapped as MARKET)",
                "Whether a later SL change without parent id is a new signal or update",
                "Missing SL/TP → INCOMPLETE vs AMBIGUOUS (mapped INCOMPLETE)",
            ],
            "optional_in_source": [
                "updated_at",
                "prior_sl",
                "parent_fixture_id",
                "symbol (defaults XAUUSD)",
            ],
            "schema_gaps_for_style": [
                "None blocking: single TP wraps into take_profit_levels list",
            ],
        },
        "anabelsignals_style": {
            "missing_in_source": [
                "permission_reference (ingestion gate)",
                "data_provenance (ingestion gate)",
                "completeness_status (derived)",
            ],
            "ambiguous_in_source": [
                "Update kinds other than sl_modified/cancelled",
                "Empty tps with present SL/direction (INCOMPLETE)",
                "Scalar entry vs zone object coexistence rules",
            ],
            "optional_in_source": [
                "updates[]",
                "entry as zone object",
                "update_id",
            ],
            "schema_gaps_for_style": [
                "None blocking for open/multi-TP/SL-mod/cancel/incomplete/zone cases tested",
            ],
        },
        "provenance_and_timestamps": {
            "published_at_utc_preserved": True,
            "last_updated_at_utc_supported": True,
            "data_provenance_required": True,
            "permission_reference_required": True,
            "synthetic_audit_uses": "SYNTHETIC_FIXTURE + covers_ai_ml=false",
        },
    }


def compatibility_report() -> dict[str, Any]:
    mapped = map_all_fixtures()
    validation = validate_mapped(mapped)
    statuses = sorted({r["status"] for r in mapped})
    directions = sorted({r["direction"] for r in mapped})
    multi_tp = any(len(r.get("take_profit_levels") or []) > 1 for r in mapped)
    return {
        "audit_id": "phase15b_schema_compatibility",
        "target_schema": SCHEMA_VERSION,
        "styles_audited": ["vasilytrader_style", "anabelsignals_style"],
        "real_provider_content_used": False,
        "telegram_accessed": False,
        "mapped_record_count": len(mapped),
        "validation": validation,
        "observed_statuses": statuses,
        "observed_directions": directions,
        "multiple_tp_exercised": multi_tp,
        "modified_sl_exercised": any(r["status"] == "MODIFIED" for r in mapped),
        "cancellation_exercised": any(r["status"] == "CANCELLED" for r in mapped),
        "incomplete_exercised": any(r["status"] == "INCOMPLETE" for r in mapped),
        "field_mapping": {
            "vasilytrader_style": field_mapping_vasilytrader_style(),
            "anabelsignals_style": field_mapping_anabelsignals_style(),
        },
        "missing_ambiguous_optional": missing_ambiguous_optional(),
        "compatibility_verdict": (
            "COMPATIBLE_WITH_INJECTION"
            if validation["all_ok"]
            else "INCOMPATIBLE_OR_MAPPING_ERRORS"
        ),
        "notes": [
            "Both synthetic styles map onto phase15a_signal_schema_v1 when permission_reference and data_provenance are injected.",
            "VasilyTrader-style single TP is represented as a one-element take_profit_levels list.",
            "AnabelSignals-style updates emit child records preserving original published_at_utc.",
            "No backtesting or model training performed.",
        ],
    }
