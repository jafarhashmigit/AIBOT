"""Secure Exness demo account metadata intake — no credentials."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase62.constants import (
    BROKER,
    ENVIRONMENT,
    FORBIDDEN_INTAKE_KEYS,
    FIELD_STATUSES,
    INTAKE_DIR,
    canonical_json_sha256,
)

REQUIRED_FIELDS = [
    "broker",
    "environment",
    "account_type",
    "account_currency",
    "platform",
    "exact_broker_symbol",
    "contract_size",
    "tick_size",
    "tick_value",
    "volume_minimum",
    "volume_step",
    "execution_mode",
    "applicable_commission_schedule",
    "swap_configuration",
    "verification_source",
    "verification_timestamp_utc",
]


def intake_schema() -> dict[str, Any]:
    out = {
        "schema_version": "phase62_account_metadata_intake_v1",
        "required_fields": REQUIRED_FIELDS,
        "field_status_enum": list(FIELD_STATUSES),
        "forbidden_keys": sorted(FORBIDDEN_INTAKE_KEYS),
        "rules": [
            "Accept manually supplied non-secret metadata only",
            "Do not infer account type from symbol suffix alone",
            "Do not activate commission from generic public documentation",
            "Preserve UNKNOWN when evidence unavailable",
            "Never store passwords, investor passwords, API secrets, or tokens",
        ],
        "example_path": "src/data/phase62/intake/account_metadata.json",
        "defaults_when_absent": {f: "UNKNOWN" for f in REQUIRED_FIELDS},
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def _field_entry(value: Any, status: str) -> dict[str, Any]:
    if status not in FIELD_STATUSES:
        raise ValueError(f"bad_field_status:{status}")
    return {"value": value, "status": status}


def load_intake_file(path: Path | None = None) -> dict[str, Any] | None:
    path = path or (INTAKE_DIR / "account_metadata.json")
    if not path.is_file():
        return None
    obj = json.loads(path.read_text(encoding="utf-8"))
    # Reject credential keys
    lower_keys = {str(k).lower() for k in obj.keys()}
    for bad in FORBIDDEN_INTAKE_KEYS:
        if bad in lower_keys or any(bad in k for k in lower_keys):
            raise ValueError(f"forbidden_credential_key_present:{bad}")
    return obj


def build_identity_status(intake: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = intake if intake is not None else load_intake_file()
    fields: dict[str, Any] = {}
    missing = []
    if raw is None:
        for f in REQUIRED_FIELDS:
            fields[f] = _field_entry("UNKNOWN" if f not in ("broker", "environment") else (BROKER if f == "broker" else ENVIRONMENT), "UNKNOWN" if f not in ("broker", "environment") else "USER_PROVIDED_UNVERIFIED")
        # broker/environment known as project target
        fields["broker"] = _field_entry(BROKER, "USER_PROVIDED_UNVERIFIED")
        fields["environment"] = _field_entry(ENVIRONMENT, "USER_PROVIDED_UNVERIFIED")
        missing = [f for f in REQUIRED_FIELDS if f not in ("broker", "environment")]
        source = None
    else:
        source = str(raw.get("_intake_path") or "intake_file")
        for f in REQUIRED_FIELDS:
            if f not in raw or raw[f] in (None, "", "UNKNOWN"):
                fields[f] = _field_entry("UNKNOWN", "UNKNOWN")
                missing.append(f)
            else:
                st = raw.get(f"{f}__status") or "USER_PROVIDED_UNVERIFIED"
                if st not in FIELD_STATUSES:
                    st = "USER_PROVIDED_UNVERIFIED"
                # Never treat suffix-only as VERIFIED account_type
                if f == "account_type" and st == "VERIFIED" and raw.get("verified_via_suffix_only"):
                    st = "USER_PROVIDED_UNVERIFIED"
                    fields[f] = _field_entry(raw[f], st)
                    fields[f]["note"] = "suffix_alone_not_definitive"
                else:
                    fields[f] = _field_entry(raw[f], st)

    account_type = fields["account_type"]["value"]
    platform = fields["platform"]["value"]
    symbol = fields["exact_broker_symbol"]["value"]
    verified_core = all(
        fields[f]["status"] == "VERIFIED"
        for f in ("account_type", "account_currency", "platform", "exact_broker_symbol")
    )

    out = {
        "broker": BROKER,
        "environment": ENVIRONMENT,
        "fields": fields,
        "missing_or_unknown_fields": missing,
        "account_type": account_type,
        "platform": platform,
        "exact_broker_symbol": symbol,
        "suffix_inference_used": False,
        "commission_activated_from_public_docs": False,
        "intake_file_present": raw is not None,
        "intake_source": source,
        "core_identity_verified": verified_core,
        "pseudonymous_account_ref": raw.get("pseudonymous_account_ref") if raw else None,
        "credentials_persisted": False,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limitations": [
            "Without Personal Area / terminal-confirmed metadata, identity remains incomplete",
            "Published Exness docs are not account-specific verification",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
