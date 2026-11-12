"""Phase 28 runner. Readiness/report only by default; live-shadow is explicit."""

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
from phase28.campaign import CampaignStore
from phase28.constants import (
    CAMPAIGN_TARGET_CANDLES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_SESSION_MAX_CANDLES,
    DATA_DIR,
    FROZEN_VOL_PATH,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase28.frozen_vol import build_frozen_vol_artifact, verify_frozen_vol_artifact
from phase28.integrity import integrity_report
from phase28.loop import run_bounded_live_shadow
from phase28.reporting import build_campaign_report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def ensure_frozen_vol(*, rebuild: bool = False) -> dict[str, Any]:
    if FROZEN_VOL_PATH.exists() and not rebuild:
        return verify_frozen_vol_artifact()
    art = build_frozen_vol_artifact()
    return {"built": True, "verify": verify_frozen_vol_artifact(art), "n_train": art.get("n_train")}


def write_ready_report() -> dict[str, Any]:
    vol_build = ensure_frozen_vol(rebuild=False)
    integrity = integrity_report({"frozen_vol_build": vol_build})
    campaign = CampaignStore(DATA_DIR).status_view()
    report = build_campaign_report(
        root=DATA_DIR,
        session={
            "mode": "ready_not_started",
            "mt5_session_started": False,
            "discord_enabled": False,
            "telegram_enabled": False,
        },
        integrity=integrity,
    )
    now = datetime.now(timezone.utc)
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "28",
        "generated_at_utc": storage_utc_iso(now),
        "generated_at_display": display_utc_iso(now),
        "mode": "ready_not_started",
        "mt5_session_started": False,
        "forward_campaign_started": False,
        "discord_message_sent": False,
        "telegram_message_sent": False,
        "broker_orders": 0,
        "campaign": campaign,
        "campaign_target": CAMPAIGN_TARGET_CANDLES,
        "default_session_max_candles": DEFAULT_SESSION_MAX_CANDLES,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": "WAIT",
        "observers_operational": {
            "H13C_BASELINE": True,
            "H13C_HIGH_VOL_RESEARCH": bool(integrity.get("frozen_vol", {}).get("ok")),
        },
        "frozen_artifacts_verified": {
            "phase14_q25_q75": integrity.get("frozen_thresholds_intact"),
            "phase27_high_only_policy": integrity.get("high_only_policy", {}).get("ok"),
            "frozen_vol_model": integrity.get("frozen_vol", {}).get("ok"),
            "phase22_protected_hashes": integrity.get("protected_hashes_phase22", {}).get("all_ok"),
        },
        "evidence": report["evidence"],
        "insufficient_forward_evidence": True,
        "genuinely_new_forward_candles": campaign.get("new_candles_processed") or 0,
        "commands": {
            "status": "python src/phase28/run_phase28.py --campaign-status",
            "ready": "python src/phase28/run_phase28.py",
            "live_shadow": (
                f"python src/phase28/run_phase28.py --run-live-shadow --max-candles {DEFAULT_SESSION_MAX_CANDLES}"
            ),
        },
        "note": (
            "Forward shadow research infrastructure only. Do not start live MT5 observation "
            "unless --run-live-shadow is explicitly provided. No production promotion."
        ),
        "integrity": {
            "protected_hashes_ok": integrity.get("protected_hashes_phase22", {}).get("all_ok"),
            "frozen_thresholds_intact": integrity.get("frozen_thresholds_intact"),
            "holdout_access_count": 0,
            "broker_order_count": 0,
            "discord_messages_sent": 0,
            "telegram_messages_sent": 0,
            "github_push": False,
        },
        "report": report,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "phase28_summary.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "runtime_ready.json", summary)
    _write_json(REPORTS_DIR / "campaign_status.json", campaign)
    _write_json(REPORTS_DIR / "evidence_status.json", report["evidence"])
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 28 forward shadow validation")
    parser.add_argument("--run-live-shadow", action="store_true", help="Explicit MT5 read-only live shadow batch.")
    parser.add_argument("--campaign-status", action="store_true")
    parser.add_argument("--rebuild-frozen-vol", action="store_true")
    parser.add_argument("--max-candles", type=int, default=DEFAULT_SESSION_MAX_CANDLES)
    parser.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args(argv)

    if args.rebuild_frozen_vol:
        built = ensure_frozen_vol(rebuild=True)
        print(json.dumps(built, indent=2, default=str))
        return 0

    if args.campaign_status and not args.run_live_shadow:
        ensure_frozen_vol(rebuild=False)
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
                    "forward_campaign_started": False,
                    "mt5_session_started": False,
                    "observers_operational": summary["observers_operational"],
                    "frozen_artifacts_verified": summary["frozen_artifacts_verified"],
                    "genuinely_new_forward_candles": summary["genuinely_new_forward_candles"],
                    "evidence": summary["evidence"],
                    "production_final_action": summary["production_final_action"],
                    "commands": summary["commands"],
                },
                indent=2,
            )
        )
        return 0

    # Explicit live shadow only.
    ensure_frozen_vol(rebuild=False)
    result = run_bounded_live_shadow(
        max_candles=min(100, int(args.max_candles)),
        poll_interval_seconds=int(args.poll_interval_seconds),
        store_root=DATA_DIR,
    )
    integrity = integrity_report({"mt5_session_started": result.get("mt5_session_started")})
    report = build_campaign_report(
        root=DATA_DIR,
        session={**result, "mode": "live_shadow_batch"},
        integrity=integrity,
    )
    _write_json(REPORTS_DIR / "latest_batch_report.json", report)
    _write_json(REPORTS_DIR / "phase28_summary.json", report)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "campaign_status.json", CampaignStore(DATA_DIR).status_view())
    _write_json(REPORTS_DIR / "evidence_status.json", report["evidence"])
    print(
        json.dumps(
            {
                "mode": "live_shadow_batch",
                "new_candles_processed": result.get("new_candles_processed"),
                "evidence": report["evidence"],
                "high_vol_blocker": result.get("high_vol_blocker"),
                "production_final_action": "WAIT",
                "insufficient_forward_evidence": report["insufficient_forward_evidence"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
