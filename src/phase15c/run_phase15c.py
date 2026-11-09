"""Phase 15C runner — permission registry & import readiness only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase15c.constants import (
    CHAMPION,
    CHAMPION_STATUS,
    RECIPE_ID,
    REGISTRY_VERSION,
    REPORTS_DIR,
    SEED,
)
from phase15c.enforcement import run_enforcement_suite
from phase15c.import_validation import validate_all_synthetic_exports
from phase15c.integrity import integrity_report
from phase15c.isolation import assert_isolation, isolation_boundaries
from phase15c.registry import apply_synthetic_scenarios, build_default_registry, provider_statuses
from phase15c.templates import all_request_templates


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run() -> dict[str, Any]:
    assert_isolation()
    live_registry = build_default_registry()
    registry = apply_synthetic_scenarios(live_registry)
    templates = all_request_templates()
    enforcement = run_enforcement_suite(registry["synthetic_enforcement_scenarios"])
    import_report = validate_all_synthetic_exports()
    integrity = integrity_report()
    bounds = isolation_boundaries()

    statuses = provider_statuses(live_registry)

    summary = {
        "recipe_id": RECIPE_ID,
        "seed": SEED,
        "phase": "15C",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry_version": REGISTRY_VERSION,
        "conclusion": "PERMISSION_READINESS_LAYER_READY",
        "live_provider_statuses": statuses,
        "any_live_permission_granted": False,
        "templates_sent": templates["templates_sent"],
        "provider_contact_attempted": False,
        "import_validation": {
            "export_count": import_report["export_count"],
            "accepted_count": import_report["accepted_count"],
            "rejected_count": import_report["rejected_count"],
        },
        "enforcement_fail_closed": enforcement["fail_closed"],
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "isolation": bounds,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "mt5_connection_count": integrity["mt5_connection_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": integrity["github_push"],
        },
        "stop_after_phase15c": True,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(
        REPORTS_DIR / "permission_registry.json",
        {
            "live_registry": live_registry,
            "registry_with_synthetic_scenarios": registry,
            "request_templates_meta": {
                "templates_sent": False,
                "provider_count": len(templates["templates"]),
                "required_asks": templates["required_asks"],
            },
        },
    )
    _write_json(
        REPORTS_DIR / "import_validation.json",
        {
            "import_report": import_report,
            "enforcement_suite": enforcement,
        },
    )
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "phase15c_summary.json", summary)
    _write_json(REPORTS_DIR / "permission_request_templates.json", templates)
    return summary


def main() -> None:
    summary = run()
    print(
        json.dumps(
            {
                "conclusion": summary["conclusion"],
                "live_provider_statuses": summary["live_provider_statuses"],
                "champion_status": summary["champion_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
