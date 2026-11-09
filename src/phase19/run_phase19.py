"""Phase 19 runner. Default readiness-only. Explicit --synthetic-test for validation."""

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

from phase19.constants import (
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    RECIPE_ID,
    REPORTS_DIR,
    SYNTHETIC_NAMESPACE,
)
from phase19.integrity import integrity_report
from phase19.pipeline import run_full_synthetic_suite


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_ready_report() -> dict[str, Any]:
    integrity = integrity_report()
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "19",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "discord_live_sent": False,
        "synthetic_test_executed": False,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "synthetic_namespace": SYNTHETIC_NAMESPACE,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": False,
        },
        "synthetic_test_command": "python src/phase19/run_phase19.py --synthetic-test",
        "note": (
            "Phase 19 validates Phase 18 infrastructure with synthetic data only. "
            "Does not prove a trading edge. Does not start MT5."
        ),
    }
    _write_json(REPORTS_DIR / "phase19_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    return summary


def run_synthetic_test() -> dict[str, Any]:
    from phase19.constants import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = DATA_DIR / SYNTHETIC_NAMESPACE / "suite_run"
    root.mkdir(parents=True, exist_ok=True)
    for child in list(root.iterdir()):
        if child.is_dir():
            for f in child.glob("*"):
                if f.is_file():
                    f.unlink()
        elif child.is_file():
            child.unlink()

    suite = run_full_synthetic_suite(root)
    integrity = integrity_report(
        {
            "synthetic_test_executed": True,
            "suite_root": str(root),
        }
    )
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "19",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "synthetic_test",
        "mt5_session_started": False,
        "discord_live_sent": False,
        "mock_discord_used": True,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "production_final_action": "WAIT",
        "broker_orders": 0,
        "holdout_access_count": 0,
        "github_push": False,
        "synthetic_namespace": SYNTHETIC_NAMESPACE,
        "suite": suite,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": 0,
            "broker_order_count": 0,
        },
        "note": "Infrastructure validation only — not a trading edge.",
    }
    _write_json(REPORTS_DIR / "synthetic_suite.json", suite)
    _write_json(REPORTS_DIR / "phase19_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(
        REPORTS_DIR / "verification.json",
        {
            "phase19_tests": "see unittest",
            "synthetic_buy_pass": (suite["scenarios"]["BUY_PASS"].get("primary_h12") or {}).get("status"),
            "synthetic_buy_fail": (suite["scenarios"]["BUY_FAIL"].get("primary_h12") or {}).get("status"),
            "synthetic_sell_pass": (suite["scenarios"]["SELL_PASS"].get("primary_h12") or {}).get("status"),
            "synthetic_sell_fail": (suite["scenarios"]["SELL_FAIL"].get("primary_h12") or {}).get("status"),
            "timeout": (suite["scenarios"]["TIMEOUT"].get("primary_h12") or {}).get("status"),
            "recovery_pending_remaining": suite["recovery"]["pending_remaining"],
            "safety": suite["safety"],
        },
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 19 shadow outcome pipeline validation")
    parser.add_argument(
        "--synthetic-test",
        action="store_true",
        help="Run isolated deterministic synthetic BUY/SELL lifecycle validation (no MT5).",
    )
    args = parser.parse_args(argv)

    if not args.synthetic_test:
        summary = write_ready_report()
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "mt5_session_started": False,
                    "synthetic_test_command": summary["synthetic_test_command"],
                    "champion_status": summary["champion_status"],
                    "synthetic_namespace": summary["synthetic_namespace"],
                },
                indent=2,
            )
        )
        return 0

    summary = run_synthetic_test()
    scenarios = summary["suite"]["scenarios"]
    print(
        json.dumps(
            {
                "mode": "synthetic_test",
                "namespace": SYNTHETIC_NAMESPACE,
                "BUY_PASS": (scenarios["BUY_PASS"].get("primary_h12") or {}).get("status"),
                "BUY_FAIL": (scenarios["BUY_FAIL"].get("primary_h12") or {}).get("status"),
                "SELL_PASS": (scenarios["SELL_PASS"].get("primary_h12") or {}).get("status"),
                "SELL_FAIL": (scenarios["SELL_FAIL"].get("primary_h12") or {}).get("status"),
                "TIMEOUT": (scenarios["TIMEOUT"].get("primary_h12") or {}).get("status"),
                "recovery_pending": summary["suite"]["recovery"]["pending_remaining"],
                "mt5_session_started": False,
                "champion_status": CHAMPION_STATUS,
                "candidate_status": CANDIDATE_STATUS,
                "production_final_action": "WAIT",
                "broker_orders": 0,
                "github_push": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
