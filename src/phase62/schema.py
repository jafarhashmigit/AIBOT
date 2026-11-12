"""Normalized Exness demo execution record schema."""

from __future__ import annotations

from typing import Any

from phase62.constants import canonical_json_sha256

EXECUTION_FIELDS = [
    "broker",
    "environment",
    "pseudonymous_account_ref",
    "platform",
    "symbol",
    "order_id",
    "deal_id",
    "position_id",
    "side",
    "volume",
    "entry_exit_classification",
    "order_type",
    "requested_price",
    "actual_fill_price",
    "fill_timestamp_utc",
    "commission",
    "swap",
    "profit",
    "fee",
    "currency",
    "rejection_or_execution_status",
    "source_timestamp_utc",
    "collection_timestamp_utc",
    "source_provenance",
    "record_kind",  # DEAL | ORDER | POSITION_SUMMARY — never conflate
]


def execution_record_schema() -> dict[str, Any]:
    out = {
        "schema_version": "phase62_exness_demo_execution_v1",
        "fields": EXECUTION_FIELDS,
        "rules": [
            "Preserve raw source separately from normalized records",
            "Store source hashes",
            "Stable broker identifiers for deduplication",
            "Handle partial fills and multiple deals per order",
            "Do not interpret an order record as a completed fill",
            "Do not interpret a position record as an individual deal",
            "Missing fields remain null/UNKNOWN — never zero-filled",
            "Never manufacture fill prices or timestamps",
            "Never mix simulated paper with genuine Exness demo records",
        ],
        "record_kinds": ["DEAL", "ORDER", "POSITION_SUMMARY"],
        "genuine_category": "EXNESS_DEMO_EXECUTION",
        "synthetic_forbidden_in_genuine_store": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
