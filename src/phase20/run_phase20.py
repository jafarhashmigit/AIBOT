"""Phase 20 runner. Default readiness-only. Explicit --run-bounded for real MT5 shadow."""

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

from phase16b.secrets import redact_secrets, safe_config_status
from phase18.experience import ExperienceStore
from phase18.store import Phase18Store
from phase20.constants import (
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_MAX_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    RECIPE_ID,
    REPORTS_DIR,
    SELECTED_HORIZON_DISPLAY,
)
from phase20.integrity import integrity_report
from phase20.loop import run_bounded_real_shadow_loop
from phase20.reporting import build_activity_summary


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def write_ready_report() -> dict[str, Any]:
    integrity = integrity_report()
    config = safe_config_status()
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "20",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "discord_message_sent": False,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "selected_horizon": SELECTED_HORIZON_DISPLAY,
        "default_max_candles": DEFAULT_MAX_CANDLES,
        "webhook_configured": config["configured"],
        "webhook_value_revealed": False,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": False,
        },
        "first_bounded_run_command": (
            f"python src/phase20/run_phase20.py --run-bounded --max-candles {DEFAULT_MAX_CANDLES} "
            "--discord-live"
        ),
        "safe_offline_command": (
            f"python src/phase20/run_phase20.py --run-bounded --max-candles {DEFAULT_MAX_CANDLES} "
            "--dry-run-discord"
        ),
        "note": (
            "No MT5/Discord loop started by default. "
            "Infrastructure/shadow validation only — no trading edge claimed."
        ),
    }
    _write_json(REPORTS_DIR / "phase20_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 20 real MT5 shadow observation")
    parser.add_argument("--run-bounded", action="store_true", help="Explicit bounded read-only MT5 shadow run.")
    parser.add_argument("--max-candles", type=int, default=DEFAULT_MAX_CANDLES)
    parser.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--dry-run-discord", action="store_true")
    parser.add_argument("--discord-live", action="store_true")
    args = parser.parse_args(argv)

    if not args.run_bounded:
        summary = write_ready_report()
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "default_max_candles": summary["default_max_candles"],
                    "mt5_session_started": False,
                    "champion_status": summary["champion_status"],
                    "first_bounded_run_command": summary["first_bounded_run_command"],
                },
                indent=2,
            )
        )
        return 0

    dry_run = not bool(args.discord_live) or bool(args.dry_run_discord)
    if args.discord_live and args.dry_run_discord:
        dry_run = True

    result = run_bounded_real_shadow_loop(
        max_candles=int(args.max_candles),
        poll_interval_seconds=int(args.poll_interval_seconds),
        enable_discord=True,
        dry_run_discord=dry_run,
        store_root=DATA_DIR,
    )
    store = Phase18Store(DATA_DIR)
    experience = ExperienceStore(DATA_DIR)
    activity = build_activity_summary(store=store, experience=experience, session=result)
    integrity = integrity_report(
        {
            "mt5_session_started": result.get("mt5_session_started"),
            "session_id": result.get("session_id"),
        }
    )
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "20",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "bounded_run",
        "session": result,
        "activity_summary": activity,
        "mt5_session_started": result.get("mt5_session_started"),
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "production_final_action": "WAIT",
        "any_final_non_wait": result.get("any_final_non_wait"),
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": False,
        },
        "note": "Infrastructure/shadow validation only — no trading edge claimed.",
    }
    _write_json(REPORTS_DIR / "session_summary.json", result)
    _write_json(REPORTS_DIR / "activity_summary.json", activity)
    _write_json(REPORTS_DIR / "phase20_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    print(
        json.dumps(
            {
                "mode": "bounded_run",
                "candles_processed": result.get("candles_processed"),
                "prediction_counts": result.get("prediction_counts"),
                "discord_signals_sent": result.get("discord_signals_sent"),
                "outcomes": result.get("outcomes"),
                "pending_outcomes": result.get("pending_outcomes"),
                "experience_counts": result.get("experience_counts"),
                "mt5_session_started": result.get("mt5_session_started"),
                "champion_status": CHAMPION_STATUS,
                "candidate_status": CANDIDATE_STATUS,
                "any_final_non_wait": result.get("any_final_non_wait"),
                "broker_orders": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
