"""Phase 21 runner — historical reachability research only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase21.analysis import run_full_research
from phase21.constants import CANDIDATE_STATUS, CHAMPION_STATUS, RECIPE_ID, REPORTS_DIR
from phase21.integrity import integrity_report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 21 H13_C threshold reachability research")
    parser.add_argument(
        "--run-research",
        action="store_true",
        help="Run historical reachability research (default is readiness-only).",
    )
    args = parser.parse_args(argv)

    if not args.run_research:
        integrity = integrity_report()
        summary = {
            "recipe_id": RECIPE_ID,
            "phase": "21",
            "mode": "ready_not_started",
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mt5_started": False,
            "discord_sent": False,
            "champion_status": CHAMPION_STATUS,
            "candidate_status": CANDIDATE_STATUS,
            "command": "python src/phase21/run_phase21.py --run-research",
            "integrity": {
                "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
                "holdout_access_count": 0,
                "github_push": False,
            },
            "note": "Research only — no trading edge established.",
        }
        _write_json(REPORTS_DIR / "phase21_summary.json", summary)
        _write_json(REPORTS_DIR / "integrity.json", integrity)
        print(json.dumps({"mode": summary["mode"], "command": summary["command"]}, indent=2))
        return 0

    result = run_full_research()
    integrity = integrity_report({"research_executed": True})
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "21",
        "mode": "research_complete",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conclusion": result["conclusion"],
        "reachability": result["frozen_reachability"]["reachability_frozen"],
        "frozen_cuts": result["frozen_reachability"]["frozen_cuts"],
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": 0,
            "broker_order_count": 0,
            "github_push": False,
            "thresholds_modified": False,
        },
        "explicit": "Research only — no trading edge established.",
    }
    _write_json(REPORTS_DIR / "phase21_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "verification.json", {
        "BUY_matches": result["conclusion"]["BUY_reachability"]["matches"],
        "BUY_rate": result["conclusion"]["BUY_reachability"]["rate"],
        "SELL_matches": result["conclusion"]["SELL_reachability"]["matches"],
        "SELL_rate": result["conclusion"]["SELL_reachability"]["rate"],
        "restrictiveness_label": result["conclusion"]["restrictiveness_label"],
        "future_research_hypothesis_justified": result["conclusion"]["future_research_hypothesis_justified"],
        "explicit": "Research only — no trading edge established.",
    })
    print(
        json.dumps(
            {
                "mode": "research_complete",
                "BUY_matches": summary["conclusion"]["BUY_reachability"]["matches"],
                "BUY_rate": summary["conclusion"]["BUY_reachability"]["rate"],
                "SELL_matches": summary["conclusion"]["SELL_reachability"]["matches"],
                "SELL_rate": summary["conclusion"]["SELL_reachability"]["rate"],
                "restrictiveness_label": summary["conclusion"]["restrictiveness_label"],
                "explicit": summary["explicit"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
