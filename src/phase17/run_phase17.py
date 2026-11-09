"""Phase 17 runner. Does NOT auto-start MT5 or Discord live sends."""

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
from phase17.constants import (
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    DEFAULT_MAX_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase17.integrity import integrity_report
from phase17.loop import run_bounded_shadow_loop


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def write_ready_report() -> dict[str, Any]:
    integrity = integrity_report()
    config = safe_config_status()
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "17",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "discord_message_sent": False,
        "experimental_buy_sell_generated": False,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
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
            f"python src/phase17/run_phase17.py --run-bounded --max-candles {DEFAULT_MAX_CANDLES} "
            "--discord-live"
        ),
        "safe_offline_command": (
            f"python src/phase17/run_phase17.py --run-bounded --max-candles {DEFAULT_MAX_CANDLES} "
            "--dry-run-discord"
        ),
        "note": "No MT5/Discord loop was started by default.",
    }
    _write_json(REPORTS_DIR / "phase17_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 17 Discord shadow signal loop")
    parser.add_argument(
        "--run-bounded",
        action="store_true",
        help="Explicitly start a bounded read-only shadow run (not default).",
    )
    parser.add_argument(
        "--max-candles",
        type=int,
        default=DEFAULT_MAX_CANDLES,
        help=f"Max newly completed M5 candles to process (default {DEFAULT_MAX_CANDLES}).",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--dry-run-discord",
        action="store_true",
        help="Journal decisions but do not POST to Discord.",
    )
    parser.add_argument(
        "--discord-live",
        action="store_true",
        help="After journaling, deliver shadow messages via configured webhook.",
    )
    args = parser.parse_args(argv)

    if not args.run_bounded:
        summary = write_ready_report()
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "default_max_candles": summary["default_max_candles"],
                    "mt5_session_started": False,
                    "discord_message_sent": False,
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

    result = run_bounded_shadow_loop(
        max_candles=int(args.max_candles),
        poll_interval_seconds=int(args.poll_interval_seconds),
        enable_discord=True,
        dry_run_discord=dry_run,
    )
    integrity = integrity_report(
        {
            "mt5_session_started": result.get("mt5_session_started"),
            "session_id": result.get("session_id"),
        }
    )
    discord_sent = any(
        (p.get("delivery") or {}).get("status") == "SENT" for p in result.get("processed", [])
    )
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "17",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "bounded_run",
        "session": result,
        "mt5_session_started": result.get("mt5_session_started"),
        "discord_message_sent": discord_sent,
        "experimental_counts": result.get("prediction_counts"),
        "any_final_non_wait": result.get("any_final_non_wait"),
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": False,
        },
    }
    _write_json(REPORTS_DIR / "session_summary.json", result)
    _write_json(REPORTS_DIR / "phase17_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    print(
        json.dumps(
            {
                "mode": "bounded_run",
                "candles_processed": result.get("candles_processed"),
                "prediction_counts": result.get("prediction_counts"),
                "mt5_session_started": result.get("mt5_session_started"),
                "discord_message_sent": discord_sent,
                "any_final_non_wait": result.get("any_final_non_wait"),
                "champion_status": CHAMPION_STATUS,
                "lock_remaining": result.get("lock_remaining"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
