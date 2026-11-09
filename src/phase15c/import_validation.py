"""Read-only validation interface for future provider-supplied CSV/JSON exports."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from phase15a.schema import REQUIRED_FIELDS, validate_signal_record
from phase15c.constants import IMPORT_CONTRACT_VERSION, TARGET_SIGNAL_SCHEMA
from phase15c.enforcement import evaluate_permission


REQUIRED_EXPORT_META = (
    "provider_id",
    "schema_version",
    "permission_evidence_reference",
    "data_provenance",
    "export_id",
    "file_sha256",
    "records",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def synthetic_export_fixtures() -> list[dict[str, Any]]:
    """Synthetic exports only — not real provider content."""
    good_record = {
        "provider_id": "synthetic_authorized",
        "signal_id": "SYN-IMP-001",
        "original_message_reference": {
            "channel_handle": "@synthetic_authorized",
            "message_id": "m1",
            "export_row_id": "r1",
        },
        "published_at_utc": "2026-03-01T10:00:00Z",
        "last_updated_at_utc": "2026-03-01T10:00:00Z",
        "instrument": "XAUUSD",
        "direction": "BUY",
        "entry_type": "MARKET",
        "entry_min": 2650.0,
        "entry_max": 2650.0,
        "stop_loss": 2640.0,
        "take_profit_levels": [2660.0],
        "status": "OPEN",
        "update_reference": {
            "parent_signal_id": None,
            "update_kind": None,
            "prior_stop_loss": None,
            "prior_take_profit_levels": None,
        },
        "permission_reference": {
            "permission_id": "SYN-PERM-FULL",
            "granted_by": "synthetic_owner",
            "granted_at_utc": "2026-02-01T00:00:00Z",
            "covers_ai_ml": False,
        },
        "data_provenance": "OWNER_EXPORT",
        "completeness_status": "COMPLETE",
    }

    incomplete_record = {
        **good_record,
        "signal_id": "SYN-IMP-002",
        "stop_loss": None,
        "take_profit_levels": [],
        "status": "INCOMPLETE",
        "completeness_status": "INCOMPLETE",
    }

    ambiguous_record = {
        **good_record,
        "signal_id": "SYN-IMP-003",
        "direction": "UNKNOWN",
        "entry_type": "UNKNOWN",
        "entry_min": None,
        "entry_max": None,
        "status": "AMBIGUOUS",
        "completeness_status": "AMBIGUOUS",
    }

    def wrap(export_id: str, provider_id: str, records: list[dict[str, Any]], **meta: Any) -> dict[str, Any]:
        payload = {
            "provider_id": provider_id,
            "schema_version": TARGET_SIGNAL_SCHEMA,
            "permission_evidence_reference": meta.get("permission_evidence_reference"),
            "data_provenance": meta.get("data_provenance", "OWNER_EXPORT"),
            "export_id": export_id,
            "records": records,
            "permission_scope_status": meta.get(
                "permission_scope_status",
                {
                    "historical_message_access": "GRANTED",
                    "signal_storage": "GRANTED",
                    "backtesting_evaluation": "GRANTED",
                    "data_retention": "GRANTED",
                    "ai_ml_training": "NOT_REQUESTED",
                },
            ),
            "permission_expiry_utc": meta.get("permission_expiry_utc", "2099-01-01T00:00:00Z"),
        }
        # file integrity over canonical JSON without hash field
        digest = _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        payload["file_sha256"] = digest
        payload["declared_file_sha256"] = meta.get("declared_file_sha256", digest)
        payload["fixture_tag"] = meta.get("fixture_tag", export_id)
        return payload

    authorized = wrap(
        "EXP-AUTH-001",
        "synthetic_authorized",
        [good_record, incomplete_record, ambiguous_record],
        permission_evidence_reference="SYN-PERM-FULL",
        fixture_tag="authorized_valid",
    )

    unauthorized = wrap(
        "EXP-UNAUTH-001",
        "synthetic_unauthorized",
        [{**good_record, "provider_id": "synthetic_unauthorized", "signal_id": "SYN-IMP-U1"}],
        permission_evidence_reference=None,
        permission_scope_status={
            "historical_message_access": "NOT_REQUESTED",
            "signal_storage": "NOT_REQUESTED",
            "backtesting_evaluation": "NOT_REQUESTED",
            "data_retention": "NOT_REQUESTED",
            "ai_ml_training": "NOT_REQUESTED",
        },
        fixture_tag="unauthorized_no_evidence",
    )

    bad_hash = wrap(
        "EXP-BADHASH-001",
        "synthetic_authorized",
        [{**good_record, "signal_id": "SYN-IMP-H1"}],
        permission_evidence_reference="SYN-PERM-FULL",
        fixture_tag="integrity_mismatch",
    )
    bad_hash["declared_file_sha256"] = "0" * 64

    dupes = wrap(
        "EXP-DUP-001",
        "synthetic_authorized",
        [
            {**good_record, "signal_id": "SYN-IMP-DUP"},
            {**good_record, "signal_id": "SYN-IMP-DUP"},
        ],
        permission_evidence_reference="SYN-PERM-FULL",
        fixture_tag="duplicate_ids",
    )

    wrong_schema = wrap(
        "EXP-SCHEMA-001",
        "synthetic_authorized",
        [{**good_record, "signal_id": "SYN-IMP-S1"}],
        permission_evidence_reference="SYN-PERM-FULL",
        fixture_tag="wrong_schema_version",
    )
    wrong_schema["schema_version"] = "unknown_schema_v0"
    # recompute actual hash after mutation; keep declared matching mutated content
    # so rejection is due to schema, not hash
    body = {k: v for k, v in wrong_schema.items() if k not in ("file_sha256", "declared_file_sha256", "fixture_tag")}
    digest = _sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":")))
    wrong_schema["file_sha256"] = digest
    wrong_schema["declared_file_sha256"] = digest

    wrong_provider_perm = wrap(
        "EXP-XPROV-001",
        "synthetic_beta",
        [{**good_record, "provider_id": "synthetic_beta", "signal_id": "SYN-IMP-X1"}],
        permission_evidence_reference="SYN-PERM-ALPHA-ONLY",
        fixture_tag="cross_provider_mismatch",
    )
    # Permission object claims alpha while export claims beta — enforced via requesting id check
    wrong_provider_perm["_permission_provider_id"] = "synthetic_alpha"

    return [authorized, unauthorized, bad_hash, dupes, wrong_schema, wrong_provider_perm]


def validate_export(export: dict[str, Any]) -> dict[str, Any]:
    """Read-only validation. Rejects unauthorized or unverifiable records."""
    errors: list[str] = []
    warnings: list[str] = []
    record_results: list[dict[str, Any]] = []

    for key in REQUIRED_EXPORT_META:
        if key not in export:
            errors.append(f"missing_export_meta:{key}")

    provider_id = export.get("provider_id")
    if not provider_id:
        errors.append("missing_provider_identity")

    if export.get("schema_version") != TARGET_SIGNAL_SCHEMA:
        errors.append(f"unsupported_schema_version:{export.get('schema_version')}")

    evidence = export.get("permission_evidence_reference")
    scope_status = export.get("permission_scope_status") or {}
    expiry = export.get("permission_expiry_utc")
    perm_provider = export.get("_permission_provider_id", provider_id)

    storage_decision = evaluate_permission(
        provider_id=str(perm_provider or ""),
        required_scope="signal_storage",
        scope_status=scope_status,
        permission_evidence_reference=evidence,
        permission_expiry_utc=expiry,
        requesting_provider_id=provider_id,
    )
    if storage_decision["decision"] != "ALLOW":
        errors.append("unauthorized_or_unverifiable_permission")
        errors.extend(storage_decision["reasons"])

    provenance = export.get("data_provenance")
    if provenance not in (
        "OWNER_EXPORT",
        "AUTHORIZED_SAMPLE",
        "AUTHORIZED_FORWARD",
        "SYNTHETIC_FIXTURE",
    ):
        errors.append(f"invalid_data_provenance:{provenance}")

    # File integrity
    body = {
        k: v
        for k, v in export.items()
        if k not in ("file_sha256", "declared_file_sha256", "fixture_tag", "_permission_provider_id")
    }
    actual = _sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":")))
    declared = export.get("declared_file_sha256") or export.get("file_sha256")
    if declared != actual:
        errors.append("file_integrity_mismatch")

    records = export.get("records") or []
    seen_ids: set[str] = set()
    for rec in records:
        sid = str(rec.get("signal_id"))
        rec_errors = validate_signal_record(rec)
        if sid in seen_ids:
            rec_errors.append("duplicate_signal_id")
        seen_ids.add(sid)
        if rec.get("provider_id") != provider_id:
            rec_errors.append("record_provider_mismatch")
        if not rec.get("published_at_utc"):
            rec_errors.append("missing_published_at_utc")
        if rec.get("data_provenance") != provenance:
            warnings.append(f"record_provenance_differs:{sid}")
        for field in REQUIRED_FIELDS:
            if field not in rec:
                rec_errors.append(f"missing_field:{field}")
        if rec.get("completeness_status") in ("AMBIGUOUS", "INCOMPLETE"):
            warnings.append(f"ambiguous_or_incomplete:{sid}")
        ok = not rec_errors
        if not ok:
            errors.extend([f"record:{sid}:{e}" for e in rec_errors])
        record_results.append({"signal_id": sid, "ok": ok, "errors": rec_errors})

    accepted = len(errors) == 0
    return {
        "export_id": export.get("export_id"),
        "fixture_tag": export.get("fixture_tag"),
        "provider_id": provider_id,
        "accepted": accepted,
        "decision": "ACCEPT" if accepted else "REJECT",
        "errors": errors,
        "warnings": warnings,
        "record_results": record_results,
        "contract_version": IMPORT_CONTRACT_VERSION,
        "read_only": True,
    }


def validate_all_synthetic_exports() -> dict[str, Any]:
    exports = synthetic_export_fixtures()
    results = [validate_export(exp) for exp in exports]
    return {
        "contract_version": IMPORT_CONTRACT_VERSION,
        "target_schema": TARGET_SIGNAL_SCHEMA,
        "synthetic_only": True,
        "export_count": len(results),
        "accepted_count": sum(1 for r in results if r["accepted"]),
        "rejected_count": sum(1 for r in results if not r["accepted"]),
        "results": results,
    }
