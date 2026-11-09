"""Phase 15B runner — schema compatibility audit only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase15b.compatibility import compatibility_report, field_mapping_anabelsignals_style, field_mapping_vasilytrader_style
from phase15b.constants import (
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    TARGET_SCHEMA,
)
from phase15b.fixtures import fixture_catalog
from phase15b.integrity import integrity_report
from phase15b.mappers import map_all_fixtures, validate_mapped


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run() -> dict[str, Any]:
    catalog = fixture_catalog()
    mapped = map_all_fixtures()
    validation = validate_mapped(mapped)
    compat = compatibility_report()
    integrity = integrity_report()

    field_mapping_doc = {
        "target_schema": TARGET_SCHEMA,
        "vasilytrader_style": field_mapping_vasilytrader_style(),
        "anabelsignals_style": field_mapping_anabelsignals_style(),
    }

    summary = {
        "recipe_id": RECIPE_ID,
        "seed": SEED,
        "phase": "15B",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conclusion": compat["compatibility_verdict"],
        "target_schema": TARGET_SCHEMA,
        "styles_audited": compat["styles_audited"],
        "mapped_record_count": len(mapped),
        "validation_all_ok": validation["all_ok"],
        "raw_fixture_count": catalog["total_raw_fixtures"],
        "real_provider_content_used": False,
        "telegram_accessed": False,
        "backtest_executed": False,
        "model_training": False,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "buy_sell_enabled": BUY_SELL_ENABLED,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "mt5_connection_count": integrity["mt5_connection_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": integrity["github_push"],
        },
        "stop_after_audit": True,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "schema_compatibility.json", compat)
    _write_json(REPORTS_DIR / "field_mapping.json", field_mapping_doc)
    _write_json(REPORTS_DIR / "synthetic_fixtures.json", catalog)
    _write_json(
        REPORTS_DIR / "mapped_signals_synthetic.json",
        {"target_schema": TARGET_SCHEMA, "records": mapped, "validation": validation},
    )
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "phase15b_summary.json", summary)
    return summary


def main() -> None:
    summary = run()
    print(
        json.dumps(
            {
                "conclusion": summary["conclusion"],
                "mapped_record_count": summary["mapped_record_count"],
                "champion_status": summary["champion_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
