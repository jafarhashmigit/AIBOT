# Phase 15C — Data Import Contract

**Contract version:** `provider_export_import_contract_v1`  
**Target signal schema:** `phase15a_signal_schema_v1`

## Interface

Read-only validation for future provider-supplied CSV/JSON exports. Phase 15C ships **synthetic fixtures only**.

### Required export metadata

- `provider_id`
- `schema_version` (must equal `phase15a_signal_schema_v1`)
- `permission_evidence_reference`
- `data_provenance`
- `export_id`
- `file_sha256` / declared integrity digest
- `records[]`

### Record validation

Each record must satisfy Phase 15A required fields, including:

- Provider identity match with export
- Publication timestamps (`published_at_utc`)
- Provenance alignment
- Schema enums / completeness markers
- Unique `signal_id` within the export

### Rejection rules

Exports are **REJECT**ed when:

- Permission evidence missing, expired, revoked, or not GRANTED for storage
- Schema version mismatch
- File integrity digest mismatch
- Duplicate signal IDs
- Provider identity mismatch / cross-provider permission attempt
- Unverifiable or unauthorized records

Incomplete or ambiguous records may be accepted only inside an otherwise authorized export, and are flagged as warnings (not silently upgraded).

## Provenance values

`OWNER_EXPORT` · `AUTHORIZED_SAMPLE` · `AUTHORIZED_FORWARD` · `SYNTHETIC_FIXTURE`

## Machine-readable results

See `reports/phase15c/import_validation.json`.
