"""Phase 15A runner — feasibility & permission audit only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure src on path when run as script
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase15a.access_options import access_feasibility_report
from phase15a.backtest_design import backtest_design
from phase15a.boundaries import assert_boundaries, integration_boundaries
from phase15a.constants import (
    CHAMPION,
    CHAMPION_STATUS,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
)
from phase15a.integrity import integrity_report
from phase15a.permission_requirements import permission_requirements_report
from phase15a.provider_inventory import build_provider_inventory, inventory_summary
from phase15a.schema import schema_document, synthetic_signal_fixtures, validate_signal_record
from phase15a.telegram_compliance import telegram_compliance_findings


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def overall_conclusion(inventory: list[dict[str, Any]]) -> str:
    outcomes = {r["phase15a_outcome"] for r in inventory}
    if "AUTHORIZED_RESEARCH_PATH_IDENTIFIED" in outcomes and len(outcomes) == 1:
        return "AUTHORIZED_RESEARCH_PATH_IDENTIFIED"
    if "REJECTED" in outcomes and outcomes <= {"REJECTED"}:
        return "REJECTED"
    if outcomes <= {"INSUFFICIENT_ACCESS"}:
        return "INSUFFICIENT_ACCESS"
    # Mixed or all permission-gated without authorization
    if "PERMISSION_REQUIRED" in outcomes or "INSUFFICIENT_ACCESS" in outcomes:
        return "PERMISSION_REQUIRED"
    return "PERMISSION_REQUIRED"


def run() -> dict[str, Any]:
    assert_boundaries()
    inventory = build_provider_inventory()
    inv_summary = inventory_summary(inventory)
    access = access_feasibility_report()
    permissions = permission_requirements_report()
    schema = schema_document()
    fixtures = synthetic_signal_fixtures()
    fixture_errors = {f["signal_id"]: validate_signal_record(f) for f in fixtures}
    design = backtest_design()
    integrity = integrity_report()
    compliance = telegram_compliance_findings()
    bounds = integration_boundaries()
    conclusion = overall_conclusion(inventory)

    provider_outcomes = {
        r["provider_id"]: r["phase15a_outcome"] for r in inventory
    }

    summary = {
        "recipe_id": RECIPE_ID,
        "seed": SEED,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": "15A",
        "conclusion": conclusion,
        "provider_outcomes": provider_outcomes,
        "authorized_research_path_identified": False,
        "permission_established": False,
        "stop_at_feasibility_and_schema": True,
        "inventory_summary": inv_summary,
        "schema_version": schema["schema_version"],
        "synthetic_fixture_count": schema["synthetic_fixture_count"],
        "fixture_validation_errors": fixture_errors,
        "backtest_executed": design["executed"],
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "integration_boundaries": bounds,
        "integrity": {
            "phase14_hashes_ok": integrity["phase14_protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "mt5_connection_count": integrity["mt5_connection_count"],
            "broker_order_count": integrity["broker_order_count"],
            "telegram_scrape_attempts": integrity["telegram_scrape_attempts"],
            "telegram_messages_stored": integrity["telegram_messages_stored"],
            "github_push": integrity["github_push"],
        },
        "compliance_default_posture": compliance["default_legal_posture"],
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "provider_inventory.json", {"providers": inventory, "summary": inv_summary})
    _write_json(REPORTS_DIR / "access_feasibility.json", access)
    _write_json(REPORTS_DIR / "permission_requirements.json", permissions)
    _write_json(REPORTS_DIR / "backtest_design.json", design)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "phase15a_summary.json", summary)
    _write_json(
        REPORTS_DIR / "schema_fixtures_synthetic.json",
        {"schema": schema, "fixtures": fixtures, "validation_errors": fixture_errors},
    )

    return summary


def main() -> None:
    summary = run()
    print(json.dumps({"conclusion": summary["conclusion"], "provider_outcomes": summary["provider_outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
