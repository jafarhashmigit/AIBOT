"""Phase 22 runner. Readiness-only by default; explicit bounded sessions."""

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
from phase22.campaign import CampaignStore
from phase22.constants import (
    CAMPAIGN_TARGET_CANDLES,
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    DATA_DIR,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_SESSION_MAX_CANDLES,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase22.diagnostics import DiagnosticJournal
from phase22.integrity import integrity_report
from phase22.loop import run_bounded_campaign_session
from phase22.reporting import build_campaign_report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def write_ready_report() -> dict[str, Any]:
    integrity = integrity_report()
    config = safe_config_status()
    campaign = CampaignStore(DATA_DIR).status_view()
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "22",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "discord_message_sent": False,
        "campaign": campaign,
        "campaign_target": CAMPAIGN_TARGET_CANDLES,
        "default_session_max_candles": DEFAULT_SESSION_MAX_CANDLES,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "webhook_configured": config["configured"],
        "webhook_value_revealed": False,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "frozen_thresholds_intact": integrity["frozen_thresholds_intact"],
            "holdout_access_count": 0,
            "broker_order_count": 0,
            "github_push": False,
        },
        "commands": {
            "status": "python src/phase22/run_phase22.py --campaign-status",
            "bounded": (
                f"python src/phase22/run_phase22.py --run-bounded --max-candles {DEFAULT_SESSION_MAX_CANDLES}"
            ),
            "bounded_discord_live": (
                f"python src/phase22/run_phase22.py --run-bounded --max-candles {DEFAULT_SESSION_MAX_CANDLES} "
                "--discord-live"
            ),
        },
        "note": "Forward shadow observation infrastructure only — no trading edge claimed.",
    }
    _write_json(REPORTS_DIR / "phase22_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    _write_json(REPORTS_DIR / "campaign_status.json", campaign)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 22 extended forward shadow observation")
    parser.add_argument("--run-bounded", action="store_true")
    parser.add_argument("--campaign-status", action="store_true", help="Show campaign progress without MT5.")
    parser.add_argument("--max-candles", type=int, default=DEFAULT_SESSION_MAX_CANDLES)
    parser.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--dry-run-discord", action="store_true")
    parser.add_argument("--discord-live", action="store_true")
    args = parser.parse_args(argv)

    if args.campaign_status and not args.run_bounded:
        status = CampaignStore(DATA_DIR).status_view()
        integrity = integrity_report()
        _write_json(REPORTS_DIR / "campaign_status.json", status)
        _write_json(REPORTS_DIR / "integrity.json", integrity)
        print(json.dumps(status, indent=2))
        return 0

    if not args.run_bounded:
        summary = write_ready_report()
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "campaign_target": summary["campaign_target"],
                    "default_session_max_candles": summary["default_session_max_candles"],
                    "campaign": summary["campaign"],
                    "mt5_session_started": False,
                    "commands": summary["commands"],
                },
                indent=2,
            )
        )
        return 0

    dry_run = not bool(args.discord_live) or bool(args.dry_run_discord)
    if args.discord_live and args.dry_run_discord:
        dry_run = True

    result = run_bounded_campaign_session(
        max_candles=int(args.max_candles),
        poll_interval_seconds=int(args.poll_interval_seconds),
        enable_discord=True,
        dry_run_discord=dry_run,
        store_root=DATA_DIR,
    )
    store = Phase18Store(DATA_DIR)
    experience = ExperienceStore(DATA_DIR)
    campaign_state = CampaignStore(DATA_DIR).load() if CampaignStore(DATA_DIR).exists() else {}
    report = build_campaign_report(
        campaign_state=campaign_state or result.get("campaign_state") or {},
        store=store,
        experience=experience,
        diagnostics=DiagnosticJournal(DATA_DIR),
        session=result,
    )
    integrity = integrity_report({"mt5_session_started": result.get("mt5_session_started")})
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "22",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "bounded_session",
        "session": result,
        "campaign_report": report,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "production_final_action": "WAIT",
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "frozen_thresholds_intact": integrity["frozen_thresholds_intact"],
            "holdout_access_count": 0,
            "broker_order_count": 0,
            "github_push": False,
        },
        "note": "Forward shadow observation infrastructure only — no trading edge claimed.",
    }
    _write_json(REPORTS_DIR / "session_summary.json", result)
    _write_json(REPORTS_DIR / "campaign_report.json", report)
    _write_json(REPORTS_DIR / "campaign_status.json", CampaignStore(DATA_DIR).status_view())
    _write_json(REPORTS_DIR / "phase22_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    print(
        json.dumps(
            {
                "mode": "bounded_session",
                "campaign_id": result.get("campaign_id"),
                "candles_processed": result.get("candles_processed"),
                "prediction_counts": result.get("prediction_counts"),
                "campaign_state": result.get("campaign_state"),
                "discord_signals_sent": result.get("discord_signals_sent"),
                "mt5_session_started": result.get("mt5_session_started"),
                "champion_status": CHAMPION_STATUS,
                "broker_orders": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
