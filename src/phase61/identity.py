"""Exness account identification — preserve UNKNOWN when unverified."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase61.adapters import scan_repo_broker_hints
from phase61.constants import INTENDED_INSTRUMENT, canonical_json_sha256


def build_account_identity() -> dict[str, Any]:
    hints = scan_repo_broker_hints()
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Historical research substrate is MetaQuotes-Demo — not Exness account confirmation
    has_exness_config = any("exness" in k.lower() for k in hints.get("env_keys_present") or [])
    has_exness_docs = bool(hints.get("exness_string_hits"))

    identity = {
        "broker_target": "Exness",
        "account_type": "UNKNOWN",
        "account_currency": "UNKNOWN",
        "trading_platform": "UNKNOWN",
        "account_server_identifier": "UNKNOWN",
        "account_login_stored": False,
        "credentials_policy": "Do not request or store passwords, investor passwords, API secrets, or tokens",
        "instrument_intended": INTENDED_INSTRUMENT,
        "broker_symbol": "UNKNOWN",
        "symbol_suffix": "UNKNOWN",
        "contract_size": "UNKNOWN",
        "min_volume": "UNKNOWN",
        "volume_step": "UNKNOWN",
        "tick_size": "UNKNOWN",
        "tick_value": "UNKNOWN",
        "execution_mode": "UNKNOWN",
        "trading_commission_status": "UNKNOWN",
        "swap_conditions": "UNKNOWN",
        "trading_sessions": "UNKNOWN",
        "suffix_ambiguity_note": (
            "Official Exness suffix table: Pro, Raw Spread, and Zero may all present as XAUUSD "
            "with no suffix. Suffix alone is not definitive account identification."
        ),
        "repo_evidence": {
            "retrieval_utc": retrieved,
            "historical_archive_server_label": "MetaQuotes-Demo",
            "exness_env_keys_found": has_exness_config,
            "exness_doc_hits": hints.get("exness_string_hits") or [],
            "env_keys_nonsecret": hints.get("env_keys_present") or [],
            "source_server_labels": hints.get("source_server_labels") or [],
            "terminal_path_hints": hints.get("terminal_path_hints") or [],
        },
        "verification_status": "UNVERIFIED",
        "account_specific_confirmation_required": True,
        "personal_area_contract_specs_available": False,
        "limitations": [
            "No Exness account metadata in repository configuration",
            "Historical MT5 archives labeled MetaQuotes-Demo — not transferable as Exness economics",
            "Public documentation does not establish this user's account conditions",
            "Jurisdiction-specific conditions may differ",
        ],
    }
    if has_exness_docs and not has_exness_config:
        identity["limitations"].append("Prior docs may mention brokers generically; not account proof")
    identity["sha256"] = canonical_json_sha256({k: v for k, v in identity.items() if k != "sha256"})
    return identity
