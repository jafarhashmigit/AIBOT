"""Phase 16B runner — Discord notification layer. Default is dry-run / no send."""

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

from phase16b.adapter import DiscordNotifier, decision_to_event
from phase16b.constants import (
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    DISCORD_CHANNEL_ID,
    DISCORD_SERVER_ID,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase16b.dedupe import DeliveryLedger
from phase16b.formatter import build_payload
from phase16b.integrity import integrity_report
from phase16b.secrets import redact_secrets, safe_config_status, webhook_configured


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def sample_events() -> list[dict[str, Any]]:
    """Offline dry-run samples (includes experimental shapes for formatter coverage)."""
    return [
        decision_to_event(
            {
                "decision_id": "phase16b_sample_wait",
                "experimental_action": "WAIT",
                "final_action": "WAIT",
                "risk_gate_result": "ALLOW",
                "decision_reason": "sample_wait",
                "decision_timestamp_utc": "2026-11-09 12:00:00",
                "model_status": "NO_MODEL",
                "candidate_status": "EXPERIMENTAL",
            }
        ),
        decision_to_event(
            {
                "decision_id": "phase16b_sample_exp_buy",
                "experimental_action": "BUY",
                "final_action": "WAIT",
                "risk_gate_result": "BLOCK",
                "decision_reason": "sample_experimental_buy",
                "decision_timestamp_utc": "2026-11-09 12:05:00",
                "model_status": "NO_MODEL",
                "candidate_status": "EXPERIMENTAL",
            }
        ),
        decision_to_event(
            {
                "decision_id": "phase16b_sample_exp_sell",
                "experimental_action": "SELL",
                "final_action": "WAIT",
                "risk_gate_result": "BLOCK",
                "decision_reason": "sample_experimental_sell",
                "decision_timestamp_utc": "2026-11-09 12:10:00",
                "model_status": "NO_MODEL",
                "candidate_status": "EXPERIMENTAL",
            }
        ),
        {
            "event_id": "phase16b_sample_pilot",
            "decision_id": "phase16b_sample_pilot",
            "message_type": "PILOT_STATUS",
            "status": "READY",
            "session_id": "n/a",
            "detail": "Phase 16B dry-run sample; no live Discord send",
            "champion_status": CHAMPION_STATUS,
            "candidate_status": CANDIDATE_STATUS,
            "decision_timestamp_utc": "2026-11-09 12:15:00",
        },
    ]


def live_send_test_event() -> dict[str, Any]:
    """Single safe live test event. No BUY/SELL."""
    return {
        "event_id": "phase16b_live_send_test",
        "decision_id": "phase16b_live_send_test",
        "message_type": "PILOT_STATUS",
        "status": "TEST",
        "session_id": "n/a",
        "detail": "AIBOT TEST — NOT A TRADING SIGNAL",
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "decision_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "experimental_action": "WAIT",
        "final_action": "WAIT",
    }


def run(*, mode: str, send_test: bool) -> dict[str, Any]:
    config = safe_config_status()
    integrity = integrity_report({"webhook_configured": config["configured"]})
    dry_run = not send_test
    if send_test and not config["configured"]:
        summary = {
            "recipe_id": RECIPE_ID,
            "phase": "16B",
            "mode": "send_test_blocked",
            "error": "DISCORD_WEBHOOK_URL_not_configured",
            "real_discord_message_sent": False,
            "webhook_configured": False,
            "champion_status": CHAMPION_STATUS,
            "champion_id": CHAMPION,
            "destination": {
                "server_id": DISCORD_SERVER_ID,
                "channel_id": DISCORD_CHANNEL_ID,
            },
            "integrity": {
                "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
                "holdout_access_count": integrity["holdout_access_count"],
                "mt5_connection_count": integrity["mt5_connection_count"],
                "broker_order_count": integrity["broker_order_count"],
            },
        }
        _write_json(REPORTS_DIR / "discord_delivery_audit.json", summary)
        _write_json(REPORTS_DIR / "integrity.json", integrity)
        _write_json(REPORTS_DIR / "phase16b_summary.json", summary)
        return summary

    ledger = DeliveryLedger()
    notifier = DiscordNotifier(ledger=ledger, dry_run=dry_run)
    results = []
    events = [live_send_test_event()] if send_test else sample_events()
    for event in events:
        # Live --send-test: only the safe TEST event (no BUY/SELL).
        if send_test:
            exp = str(event.get("experimental_action", "WAIT")).upper()
            if exp in {"BUY", "SELL"} or event.get("message_type") in {
                "EXPERIMENTAL_BUY",
                "EXPERIMENTAL_SELL",
            }:
                raise RuntimeError("HARD FAILURE: --send-test must not send BUY/SELL")
        payload = build_payload(event)
        if send_test and "AIBOT TEST — NOT A TRADING SIGNAL" not in payload["content"]:
            raise RuntimeError("HARD FAILURE: live test payload missing required label")
        delivery = notifier.notify(event)
        results.append(
            {
                "event_id": event.get("event_id") or event.get("decision_id"),
                "message_type": event.get("message_type") or delivery.get("message_type"),
                "delivery_status": delivery.get("status"),
                "http_status": delivery.get("http_status"),
                "changed_decision": delivery.get("changed_decision"),
                "payload_has_disclaimer_if_exp": (
                    "EXPERIMENTAL — NOT A LIVE TRADING SIGNAL" in payload["content"]
                    if (
                        event.get("experimental_action") in {"BUY", "SELL"}
                        or event.get("message_type") in {"EXPERIMENTAL_BUY", "EXPERIMENTAL_SELL"}
                    )
                    else None
                ),
                "payload_has_test_label": (
                    "AIBOT TEST — NOT A TRADING SIGNAL" in payload["content"] if send_test else None
                ),
            }
        )

    real_sent = any(r["delivery_status"] == "SENT" for r in results)
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "16B",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "send_test" if send_test else mode,
        "dry_run": dry_run,
        "webhook_configured": config["configured"],
        "webhook_value_revealed": False,
        "real_discord_message_sent": real_sent,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "destination": {
            "server_id": DISCORD_SERVER_ID,
            "channel_id": DISCORD_CHANNEL_ID,
        },
        "sample_delivery_results": results,
        "integrity": {
            "protected_hashes_ok": integrity["protected_hashes"]["all_ok"],
            "holdout_access_count": integrity["holdout_access_count"],
            "mt5_connection_count": integrity["mt5_connection_count"],
            "broker_order_count": integrity["broker_order_count"],
            "github_push": False,
        },
        "next_safe_test_step": (
            "Set DISCORD_WEBHOOK_URL in a gitignored .env (do not commit), then run: "
            "python src/phase16b/run_phase16b.py --send-test"
            if not config["configured"]
            else "Configuration present. Explicitly run: python src/phase16b/run_phase16b.py --send-test"
        ),
    }
    _write_json(REPORTS_DIR / "discord_delivery_audit.json", summary)
    _write_json(REPORTS_DIR / "integrity.json", integrity)
    _write_json(REPORTS_DIR / "phase16b_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 16B Discord notification layer")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Format/dedupe only (default)")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="EXPLICIT live webhook test. Disabled unless DISCORD_WEBHOOK_URL is configured.",
    )
    args = parser.parse_args(argv)
    # Default dry-run always unless --send-test
    summary = run(mode="dry_run", send_test=bool(args.send_test))
    print(
        json.dumps(
            {
                "mode": summary.get("mode"),
                "webhook_configured": summary.get("webhook_configured"),
                "real_discord_message_sent": summary.get("real_discord_message_sent"),
                "champion_status": summary.get("champion_status"),
                "protected_hashes_ok": summary.get("integrity", {}).get("protected_hashes_ok"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
