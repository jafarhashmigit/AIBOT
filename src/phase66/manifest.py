"""Immutable dataset manifest for a collection period."""

from __future__ import annotations

import json
from typing import Any

from phase66.constants import (
    ACTIVE_SYMBOL,
    DATASET_VERSION,
    MANIFEST_PATH,
    RECIPE_ID,
    SCHEMA_VERSION,
    canonical_json_sha256,
)
from phase66.schema import utc_now


def build_dataset_manifest(
    *,
    events: list[dict[str, Any]],
    evidence_class: str,
    research_use_status: str,
    quality_summary: dict[str, Any],
    date_range: tuple[str | None, str | None] | None = None,
) -> dict[str, Any]:
    ts_list = [e.get("server_timestamp_utc") for e in events if e.get("server_timestamp_utc")]
    start = min(ts_list) if ts_list else (date_range[0] if date_range else None)
    end = max(ts_list) if ts_list else (date_range[1] if date_range else None)
    hashes = sorted({e.get("content_hash") for e in events if e.get("content_hash")})
    out = {
        "manifest_id": f"manifest_{canonical_json_sha256({'v': DATASET_VERSION, 'n': len(events), 'h': hashes[:5]})[:24]}",
        "recipe_id": RECIPE_ID,
        "dataset_version": DATASET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_utc": utc_now(),
        "symbol": ACTIVE_SYMBOL,
        "timeframes": sorted({e.get("timeframe") for e in events if e.get("timeframe")}),
        "date_range": {"start": start, "end": end},
        "observation_count": len(events),
        "quote_count": sum(1 for e in events if e.get("kind") == "QUOTE_SNAPSHOT"),
        "m5_count": sum(1 for e in events if e.get("kind") == "M5_BAR"),
        "source_classification": evidence_class,
        "content_hashes": hashes,
        "missingness": quality_summary.get("missingness"),
        "data_quality_results": quality_summary,
        "research_use_status": research_use_status,
        "immutable": True,
        "note": "Observation count ≠ independent statistical sample size",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
