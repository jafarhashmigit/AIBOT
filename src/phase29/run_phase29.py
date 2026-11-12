"""Phase 29 runner. Readiness by default; live-shadow is explicit."""

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

from aibot_time import display_utc_iso, storage_utc_iso
from phase16b.secrets import redact_secrets, safe_config_status
from phase28.frozen_vol import build_frozen_vol_artifact, verify_frozen_vol_artifact
from phase28.constants import FROZEN_VOL_PATH
from phase29.campaign import CampaignStore
from phase29.constants import (
    DATA_DIR,
    DEFAULT_DISCORD_WAIT,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_SESSION_MAX_CANDLES,
    MIN_BUY_SELL_DECISIONS,
    MIN_FORWARD_CANDLES,
    MIN_MATURED_OUTCOMES,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase29.integrity import integrity_report
from phase29.loop import run_bounded_live_shadow
from phase29.reporting import build_campaign_report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def ensure_frozen_vol() -> dict[str, Any]:
    if not FROZEN_VOL_PATH.exists():
        art = build_frozen_vol_artifact()
        return {"built": True, "n_train": art.get("n_train"), "verify": verify_frozen_vol_artifact(art)}
    return verify_frozen_vol_artifact()


def write_ready_report() -> dict[str, Any]:
    vol = ensure_frozen_vol()
    integrity = integrity_report({"frozen_vol_build": vol})
    campaign = CampaignStore(DATA_DIR).status_view()
    config = safe_config_status()
    report = build_campaign_report(
        root=DATA_DIR,
        session={
            "mode": "ready_not_started",
            "mt5_session_started": False,
            "discord_enabled": False,
        },
        integrity=integrity,
    )
    now = datetime.now(timezone.utc)
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "29",
        "generated_at_utc": storage_utc_iso(now),
        "generated_at_display": display_utc_iso(now),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "forward_campaign_started": bool(campaign.get("forward_observation_start_utc")),
        "discord_message_sent": False,
        "broker_orders": 0,
        "holdout_accessed": False,
        "campaign": campaign,
        "targets": {
            "min_forward_candles": MIN_FORWARD_CANDLES,
            "min_buy_sell_decisions": MIN_BUY_SELL_DECISIONS,
            "min_matured_outcomes": MIN_MATURED_OUTCOMES,
        },
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": "WAIT",
        "webhook_configured": config["configured"],
        "webhook_value_revealed": False,
        "evidence": report["evidence"],
        "insufficient_forward_evidence": True,
        "commands": {
            "status": "python src/phase29/run_phase29.py --campaign-status",
            "ready": "python src/phase29/run_phase29.py",
            "live_shadow_dry": (
                "python src/phase29/run_phase29.py --run-live-shadow --max-candles 100 --discord-live --dry-run-discord"
            ),
            "live_shadow": (
                "python src/phase29/run_phase29.py --run-live-shadow --discord-live"
            ),
        },
        "note": (
            "Forward shadow continuation. Live MT5 only with --run-live-shadow. "
            "Discord notification-only; production remains WAIT."
        ),
        "integrity": {
            "protected_hashes_ok": integrity.get("protected_hashes_phase22", {}).get("all_ok"),
            "frozen_thresholds_intact": integrity.get("frozen_thresholds_intact"),
            "holdout_access_count": 0,
            "broker_order_count": 0,
        },
        "report": report,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "phase29_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    _write_json(REPORTS_DIR / "campaign_status.json", campaign)
    _write_json(REPORTS_DIR / "evidence_status.json", report["evidence"])
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 29 forward shadow continuation")
    parser.add_argument("--run-live-shadow", action="store_true")
    parser.add_argument("--campaign-status", action="store_true")
    parser.add_argument(
        "--max-candles",
        type=int,
        default=None,
        help="Optional session candle cap. Omit to continue until campaign targets (live MT5).",
    )
    parser.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--discord-live", action="store_true", help="Enable Discord webhook posts.")
    parser.add_argument("--dry-run-discord", action="store_true", help="Journal Discord payloads without sending.")
    parser.add_argument(
        "--discord-wait",
        action="store_true",
        default=DEFAULT_DISCORD_WAIT,
        help="Also notify WAIT (default off to avoid spam).",
    )
    args = parser.parse_args(argv)

    if args.campaign_status and not args.run_live_shadow:
        ensure_frozen_vol()
        status = CampaignStore(DATA_DIR).status_view()
        integrity = integrity_report()
        report = build_campaign_report(root=DATA_DIR, session={"mode": "campaign_status"}, integrity=integrity)
        _write_json(REPORTS_DIR / "campaign_status.json", status)
        _write_json(REPORTS_DIR / "integrity.json", integrity)
        _write_json(REPORTS_DIR / "latest_batch_report.json", report)
        print(json.dumps({"campaign": status, "evidence": report["evidence"]}, indent=2))
        return 0

    if not args.run_live_shadow:
        summary = write_ready_report()
        print(
            json.dumps(
                {
                    "mode": summary["mode"],
                    "forward_campaign_started": summary["forward_campaign_started"],
                    "mt5_session_started": False,
                    "targets": summary["targets"],
                    "evidence": summary["evidence"],
                    "production_final_action": "WAIT",
                    "commands": summary["commands"],
                },
                indent=2,
            )
        )
        return 0

    ensure_frozen_vol()
    dry_run = (not bool(args.discord_live)) or bool(args.dry_run_discord)
    if args.discord_live and args.dry_run_discord:
        dry_run = True
    discord_enabled = bool(args.discord_live) or bool(args.dry_run_discord)

    result = run_bounded_live_shadow(
        max_candles=args.max_candles if args.max_candles is not None else DEFAULT_SESSION_MAX_CANDLES,
        poll_interval_seconds=int(args.poll_interval_seconds),
        store_root=DATA_DIR,
        discord_enabled=discord_enabled,
        dry_run_discord=dry_run,
        notify_wait=bool(args.discord_wait),
    )
    integrity = integrity_report({"mt5_session_started": result.get("mt5_session_started")})
    report = build_campaign_report(
        root=DATA_DIR,
        session={**result, "mode": "live_shadow_batch"},
        integrity=integrity,
    )
    _write_json(REPORTS_DIR / "latest_batch_report.json", report)
    _write_json(REPORTS_DIR / "phase29_summary.json", report)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "campaign_status.json", CampaignStore(DATA_DIR).status_view())
    _write_json(REPORTS_DIR / "evidence_status.json", report["evidence"])
    print(
        json.dumps(
            {
                "mode": "live_shadow_batch",
                "new_candles_processed": result.get("new_candles_processed"),
                "forward_observation_start_utc": result.get("forward_observation_start_utc"),
                "n_buy_sell_baseline": result.get("n_buy_sell_baseline"),
                "n_high_only_accepted": result.get("n_high_only_accepted"),
                "n_matured_outcomes": result.get("n_matured_outcomes"),
                "evidence": report["evidence"],
                "production_final_action": "WAIT",
                "broker_orders": 0,
                "insufficient_forward_evidence": report["insufficient_forward_evidence"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
