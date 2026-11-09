"""Aggregated permission requirements for Phase 15A."""

from __future__ import annotations

from typing import Any

from phase15a.constants import PROVIDERS
from phase15a.telegram_compliance import (
    telegram_compliance_findings,
    written_permission_must_cover,
)


def permission_requirements_report() -> dict[str, Any]:
    compliance = telegram_compliance_findings()
    must_cover = written_permission_must_cover()
    per_provider = []
    for p in PROVIDERS:
        per_provider.append(
            {
                "provider_id": p["provider_id"],
                "handle": p["handle"],
                "written_permission_on_file": False,
                "ai_ml_consent_on_file": False,
                "authorized_export_received": False,
                "status": "PERMISSION_REQUIRED_OR_INSUFFICIENT_ACCESS",
                "required_topics": [t["topic"] for t in must_cover],
            }
        )
    return {
        "default_posture": compliance["default_legal_posture"],
        "scraping_default": compliance["scraping_default"],
        "ai_ml_use_default": compliance["ai_ml_use_default"],
        "written_permission_must_cover": must_cover,
        "telegram_compliance_summary": {
            "sources_reviewed": [s["url"] for s in compliance["sources_reviewed"]],
            "uncertainties": compliance["uncertainties"],
            "phase15a_prohibited_actions": compliance["phase15a_prohibited_actions"],
        },
        "providers": per_provider,
        "any_provider_authorized": False,
    }
