"""Versioned permission registry for external signal providers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from phase15c.constants import (
    PERMISSION_SCOPES,
    PERMISSION_STATUSES,
    PROVIDERS,
    REGISTRY_VERSION,
)


def _empty_scope_status() -> dict[str, str]:
    return {scope: "NOT_REQUESTED" for scope in PERMISSION_SCOPES}


def empty_provider_permission(provider: dict[str, str]) -> dict[str, Any]:
    return {
        "provider_id": provider["provider_id"],
        "display_name": provider["display_name"],
        "handle": provider["handle"],
        "identity_verification": {
            "status": "NOT_VERIFIED",
            "method": None,
            "verified_at_utc": None,
            "notes": "Public handle visibility is not identity verification.",
        },
        "scope_status": _empty_scope_status(),
        "permission_expiry_utc": None,
        "permission_evidence_reference": None,
        "review_status": "NOT_REQUESTED",
        "overall_status": "NOT_REQUESTED",
        "inferred_from_public_availability": False,
        "notes": (
            "Default fail-closed posture. Never infer permission from public "
            "channel availability or promotional statements."
        ),
    }


def build_default_registry() -> dict[str, Any]:
    """Initial registry: all five providers NOT_REQUESTED."""
    providers = [empty_provider_permission(p) for p in PROVIDERS]
    return {
        "registry_version": REGISTRY_VERSION,
        "allowed_statuses": list(PERMISSION_STATUSES),
        "tracked_scopes": list(PERMISSION_SCOPES),
        "inference_from_public_channel_forbidden": True,
        "providers": providers,
        "any_provider_granted": False,
        "cross_provider_authorization_forbidden": True,
    }


def compute_overall_status(scope_status: dict[str, str]) -> str:
    values = list(scope_status.values())
    if any(v == "REVOKED" for v in values):
        return "REVOKED"
    if any(v == "EXPIRED" for v in values):
        # Only overall EXPIRED if something was granted/expired and nothing active
        if all(v in ("EXPIRED", "NOT_REQUESTED", "REJECTED") for v in values):
            return "EXPIRED"
    if any(v == "REJECTED" for v in values) and all(
        v in ("REJECTED", "NOT_REQUESTED") for v in values
    ):
        return "REJECTED"
    granted = [v for v in values if v == "GRANTED"]
    partial = [v for v in values if v == "PARTIALLY_GRANTED"]
    requested = [v for v in values if v == "REQUESTED"]
    if granted and len(granted) == len(values):
        return "GRANTED"
    if granted or partial:
        return "PARTIALLY_GRANTED"
    if requested:
        return "REQUESTED"
    if any(v == "REJECTED" for v in values):
        return "PARTIALLY_GRANTED" if granted or partial or requested else "REJECTED"
    return "NOT_REQUESTED"


def apply_synthetic_scenarios(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach synthetic scenario overlays for enforcement testing only.

    Does not claim real provider grants. Scenario records are clearly marked.
    """
    reg = deepcopy(registry or build_default_registry())
    scenarios = {
        "no_evidence": {
            "description": "No permission evidence present → reject all uses",
            "provider_id": "vasilytrader",
            "scope_status": _empty_scope_status(),
            "permission_evidence_reference": None,
            "permission_expiry_utc": None,
            "expected_enforcement": "REJECT",
        },
        "storage_only": {
            "description": "Storage granted does not authorize backtesting or AI/ML",
            "provider_id": "anabelsignals",
            "scope_status": {
                "historical_message_access": "GRANTED",
                "signal_storage": "GRANTED",
                "backtesting_evaluation": "NOT_REQUESTED",
                "data_retention": "GRANTED",
                "ai_ml_training": "NOT_REQUESTED",
            },
            "permission_evidence_reference": "SYN-EVIDENCE-STORAGE-ONLY",
            "permission_expiry_utc": "2099-01-01T00:00:00Z",
            "expected_backtest": "REJECT",
            "expected_ai_ml": "REJECT",
            "expected_storage": "ALLOW",
        },
        "backtest_without_ai": {
            "description": "Backtesting grant does not authorize AI/ML",
            "provider_id": "goldtradersunny",
            "scope_status": {
                "historical_message_access": "GRANTED",
                "signal_storage": "GRANTED",
                "backtesting_evaluation": "GRANTED",
                "data_retention": "GRANTED",
                "ai_ml_training": "NOT_REQUESTED",
            },
            "permission_evidence_reference": "SYN-EVIDENCE-BACKTEST-ONLY",
            "permission_expiry_utc": "2099-01-01T00:00:00Z",
            "expected_backtest": "ALLOW",
            "expected_ai_ml": "REJECT",
        },
        "expired": {
            "description": "Expired permission → reject",
            "provider_id": "fxpremiere",
            "scope_status": {
                "historical_message_access": "EXPIRED",
                "signal_storage": "EXPIRED",
                "backtesting_evaluation": "EXPIRED",
                "data_retention": "EXPIRED",
                "ai_ml_training": "EXPIRED",
            },
            "permission_evidence_reference": "SYN-EVIDENCE-EXPIRED",
            "permission_expiry_utc": "2020-01-01T00:00:00Z",
            "expected_enforcement": "REJECT",
        },
        "revoked": {
            "description": "Revoked permission → reject",
            "provider_id": "unitedkings",
            "scope_status": {
                "historical_message_access": "REVOKED",
                "signal_storage": "REVOKED",
                "backtesting_evaluation": "REVOKED",
                "data_retention": "REVOKED",
                "ai_ml_training": "REVOKED",
            },
            "permission_evidence_reference": "SYN-EVIDENCE-REVOKED",
            "permission_expiry_utc": "2099-01-01T00:00:00Z",
            "expected_enforcement": "REJECT",
        },
    }
    reg["synthetic_enforcement_scenarios"] = scenarios
    # Live registry remains NOT_REQUESTED for all real providers
    for p in reg["providers"]:
        p["overall_status"] = compute_overall_status(p["scope_status"])
        p["review_status"] = p["overall_status"]
    reg["any_provider_granted"] = False
    reg["note"] = (
        "Live provider entries remain NOT_REQUESTED. Synthetic scenarios are "
        "for enforcement unit tests only and do not constitute real grants."
    )
    return reg


def provider_statuses(registry: dict[str, Any] | None = None) -> dict[str, str]:
    reg = registry or build_default_registry()
    return {p["provider_id"]: p["overall_status"] for p in reg["providers"]}
