"""Provenance classification — backfill never equals newly observed live."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from phase69.constants import (
    BROKER_OBSERVED_LIVE_BAR,
    BROKER_OBSERVED_QUOTE,
    HISTORICAL_BACKFILL,
    LIVE_INCOMPLETE_OR_FORMING_M5,
    PROVENANCE_ALIASES,
    SYNTHETIC_FIXTURE,
)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def normalize_provenance(label: str | None) -> str | None:
    if not label:
        return None
    return PROVENANCE_ALIASES.get(label, label)


def classify_record(
    record: dict[str, Any],
    *,
    collector_started_utc: str | None,
    collector_ended_utc: str | None = None,
) -> str:
    """Classify a journal record into Phase69 canonical provenance."""
    # Prefer already-stamped field
    stamped = normalize_provenance(record.get("evidence_provenance"))
    if stamped in {
        HISTORICAL_BACKFILL,
        BROKER_OBSERVED_LIVE_BAR,
        BROKER_OBSERVED_QUOTE,
        SYNTHETIC_FIXTURE,
        LIVE_INCOMPLETE_OR_FORMING_M5,
    }:
        return stamped

    if record.get("synthetic") or record.get("source_classification") in (
        "SYNTHETIC_TEST_FIXTURE",
        SYNTHETIC_FIXTURE,
    ):
        return SYNTHETIC_FIXTURE

    kind = record.get("kind")
    started = _parse(collector_started_utc)
    ended = _parse(collector_ended_utc)
    srv = _parse(record.get("server_timestamp_utc"))

    if kind == "QUOTE_SNAPSHOT":
        return BROKER_OBSERVED_QUOTE

    if kind == "M5_BAR":
        if srv is None or started is None:
            return "M5_UNCLASSIFIED"
        bar_close = srv + timedelta(minutes=5)
        if bar_close <= started:
            return HISTORICAL_BACKFILL
        end_ref = ended or _parse(record.get("collection_timestamp_utc")) or started
        if bar_close <= end_ref:
            return BROKER_OBSERVED_LIVE_BAR
        return LIVE_INCOMPLETE_OR_FORMING_M5

    return "UNKNOWN"


def stamp_quote_provenance(rec: dict[str, Any], *, cycle: int | None = None) -> dict[str, Any]:
    out = dict(rec)
    out["evidence_provenance"] = BROKER_OBSERVED_QUOTE if not rec.get("synthetic") else SYNTHETIC_FIXTURE
    if cycle is not None:
        out["collector_cycle"] = cycle
    return out


def stamp_m5_provenance(
    rec: dict[str, Any],
    *,
    collector_started_utc: str,
    collection_time_utc: str,
    cycle: int | None = None,
) -> dict[str, Any]:
    out = dict(rec)
    if rec.get("synthetic"):
        out["evidence_provenance"] = SYNTHETIC_FIXTURE
    else:
        out["evidence_provenance"] = classify_record(
            rec,
            collector_started_utc=collector_started_utc,
            collector_ended_utc=collection_time_utc,
        )
    if cycle is not None:
        out["collector_cycle"] = cycle
    out["collector_started_utc"] = collector_started_utc
    # Recompute content hash identity fields are already set; provenance is additive metadata
    # Do NOT change stable_key (idempotency on bar identity remains)
    return out
