"""Idempotent session-evidence ingestion into BrokerEvidenceJournal."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_12.applicability import build_applicability_matrix
from phase64_12.constants import (
    ACTIVE_SYMBOL,
    RETRIEVAL_DATE,
    SCHEDULE_VERSION,
    SESSION_JOURNAL_ROOT,
    SOURCE_SNAPSHOT_DIR,
    SRC_DST_UPDATE,
    SRC_SUFFIXES,
    canonical_json_sha256,
    sha256_hex,
)
from phase64_12.schedule import build_verified_schedule_spec
from phase64_12.sources import official_source_inventory


def _event(
    *,
    evidence_id: str,
    kind: str,
    payload: dict[str, Any],
    source_url: str,
) -> dict[str, Any]:
    body = {
        "evidence_id": evidence_id,
        "kind": kind,
        "symbol": ACTIVE_SYMBOL,
        "schedule_version": SCHEDULE_VERSION,
        "retrieval_date": RETRIEVAL_DATE,
        "source_url": source_url,
        "payload": payload,
        "synthetic": False,
        "evidence_label": "BROKER_PUBLISHED",
    }
    body_hash = canonical_json_sha256(body)
    return {
        **body,
        "stable_key": f"session_evidence:{evidence_id}:{SCHEDULE_VERSION}",
        "body_hash": body_hash,
        "event_id": f"evt_{sha256_hex(evidence_id + body_hash)[:24]}",
    }


def ingest_session_evidence(
    journal_root: Path | None = None,
    *,
    crash_after_wal: bool = False,
) -> dict[str, Any]:
    root = journal_root or SESSION_JOURNAL_ROOT
    root.mkdir(parents=True, exist_ok=True)
    SOURCE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    inventory = official_source_inventory()
    appl = build_applicability_matrix()
    schedule = build_verified_schedule_spec()

    # Persist source snapshot (provenance + schedule body)
    snapshot = {
        "inventory": inventory,
        "applicability": appl,
        "schedule": schedule,
        "retrieval_date": RETRIEVAL_DATE,
    }
    snap_bytes = (json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    snap_name = f"session_sources_{SCHEDULE_VERSION}.json"
    (SOURCE_SNAPSHOT_DIR / snap_name).write_bytes(snap_bytes)

    journal = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
    raw_meta = journal.save_raw_bytes(
        source_name=snap_name,
        content=snap_bytes,
        provenance="phase64_12_official_exness_help_center",
    )
    batch_id = journal.begin_batch(
        source_file=snap_name,
        source_sha256=raw_meta["sha256"],
        parser_version="phase64_12_session_ingest_v1",
    )

    events = [
        _event(
            evidence_id="exness_xauusd_dst_hours",
            kind="WEEKLY_SCHEDULE",
            payload={"winter": schedule["winter_weekly_utc"], "summer": schedule["summer_weekly_utc"]},
            source_url=SRC_DST_UPDATE,
        ),
        _event(
            evidence_id="exness_suffix_applicability_xauusdm",
            kind="SYMBOL_APPLICABILITY",
            payload=appl,
            source_url=SRC_SUFFIXES,
        ),
        _event(
            evidence_id="exness_session_source_inventory",
            kind="SOURCE_INVENTORY",
            payload={"n_sources": inventory["n_sources"], "primary_hour_source": inventory["primary_hour_source"]},
            source_url=SRC_DST_UPDATE,
        ),
    ]

    results = []
    for ev in events:
        try:
            results.append(journal.append_event(ev, import_batch_id=batch_id, crash_after_wal=crash_after_wal))
        except RuntimeError as exc:
            if "CrashInjected" in str(exc):
                # Re-open journal to recover WAL
                recovered = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
                return {
                    "status": "CRASH_INJECTED_THEN_RECOVERABLE",
                    "results": results,
                    "integrity": recovered.integrity_report(),
                    "batch_id": batch_id,
                }
            raise

    # Idempotent second pass
    dup_results = [journal.append_event(ev, import_batch_id=batch_id) for ev in events]

    out = {
        "batch_id": batch_id,
        "raw": raw_meta,
        "ingest_results": results,
        "idempotent_results": dup_results,
        "all_duplicate_on_replay": all(r.get("status") == "DUPLICATE_SUPPRESSED" for r in dup_results),
        "integrity": journal.integrity_report(),
        "n_events": len(journal.all_events()),
        "journal_root": str(root),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def ingest_conflicting_payload(journal_root: Path) -> dict[str, Any]:
    """Demonstrate conflict preservation: same stable_key, different body_hash."""
    journal = BrokerEvidenceJournal(journal_root, allow_synthetic=False, store_label="GENUINE")
    batch = journal.begin_batch(
        source_file="conflict_test",
        source_sha256="0" * 64,
        parser_version="phase64_12_conflict_v1",
    )
    base = {
        "evidence_id": "conflict_probe",
        "kind": "WEEKLY_SCHEDULE",
        "symbol": ACTIVE_SYMBOL,
        "schedule_version": SCHEDULE_VERSION,
        "retrieval_date": RETRIEVAL_DATE,
        "source_url": SRC_DST_UPDATE,
        "payload": {"hours": "A"},
        "synthetic": False,
        "evidence_label": "BROKER_PUBLISHED",
        "stable_key": f"session_evidence:conflict_probe:{SCHEDULE_VERSION}",
    }
    a = {**base, "body_hash": canonical_json_sha256({**base, "payload": {"hours": "A"}}), "event_id": f"evt_{uuid.uuid4().hex[:16]}"}
    b = {
        **base,
        "payload": {"hours": "B"},
        "body_hash": canonical_json_sha256({**base, "payload": {"hours": "B"}}),
        "event_id": f"evt_{uuid.uuid4().hex[:16]}",
    }
    r1 = journal.append_event(a, import_batch_id=batch)
    r2 = journal.append_event(b, import_batch_id=batch)
    return {
        "first": r1,
        "second": r2,
        "conflict_quarantined": r2.get("status") == "QUARANTINED",
        "incidents": journal.incidents(),
        "integrity": journal.integrity_report(),
    }
