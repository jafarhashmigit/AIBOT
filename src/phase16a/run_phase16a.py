"""Phase 16A runner — preflight, optional controlled 1h MT5 pilot, reports."""

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

from phase16a.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    RECIPE_ID,
    REPORTS_DIR,
    SESSION_DURATION_SECONDS,
)
from phase16a.integrity import integrity_report
from phase16a.preflight import run_preflight
from phase16a.predictor import parity_smoke_cases


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def run(*, start_pilot: bool, duration_seconds: int) -> dict[str, Any]:
    preflight = run_preflight(probe_mt5=True)
    _write_json(REPORTS_DIR / "preflight.json", preflight)

    session_summary: dict[str, Any]
    if not preflight["can_start_session"]:
        session_summary = {
            "status": "not_started",
            "reason": "preflight_failed",
            "critical_failures": preflight["critical_failures"],
        }
    elif not start_pilot:
        session_summary = {
            "status": "not_started",
            "reason": "pilot_not_requested",
            "note": "Preflight PASS; pass --pilot to start the controlled 1h session",
        }
    else:
        from phase16a.session import run_pilot_session

        session_summary = run_pilot_session(duration_seconds=duration_seconds)

    integrity = integrity_report(
        {
            "mt5_connection_status": (preflight.get("mt5_probe") or {}).get("status"),
            "session_status": session_summary.get("status"),
            "broker_order_count": session_summary.get("broker_orders", 0),
        }
    )
    _write_json(REPORTS_DIR / "session_summary.json", session_summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)

    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "16A",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preflight_verdict": preflight["verdict"],
        "h13c_parity_smoke": parity_smoke_cases(),
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "session": {
            "status": session_summary.get("status"),
            "started_at_utc": session_summary.get("started_at_utc"),
            "stopped_at_utc": session_summary.get("stopped_at_utc"),
            "started_at_pkt": session_summary.get("started_at_pkt"),
            "stopped_at_pkt": session_summary.get("stopped_at_pkt"),
            "candles_observed": session_summary.get("candles_observed"),
            "prediction_counts": session_summary.get("prediction_counts"),
            "outcomes": session_summary.get("outcomes"),
        },
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": integrity["github_push"],
        },
        "stop_after_phase16a": True,
    }
    _write_json(REPORTS_DIR / "phase16a_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 16A H13_C shadow pilot")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--pilot", action="store_true", help="Start controlled 1h MT5 RO pilot if preflight passes")
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=SESSION_DURATION_SECONDS,
        help="Pilot duration (default 3600)",
    )
    args = parser.parse_args(argv)
    start_pilot = bool(args.pilot) and not bool(args.preflight_only)
    summary = run(start_pilot=start_pilot, duration_seconds=int(args.duration_seconds))
    print(json.dumps({
        "preflight_verdict": summary["preflight_verdict"],
        "session_status": summary["session"]["status"],
        "champion_status": summary["champion_status"],
        "candidate_status": summary["candidate_status"],
    }, indent=2))
    if summary["preflight_verdict"] != "PASS":
        return 2
    if start_pilot and summary["session"]["status"] not in {"completed"}:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
