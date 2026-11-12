"""Notification-only Discord delivery with idempotent ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase16b.client import post_webhook
from phase16b.secrets import load_webhook_url, redact_secrets, webhook_configured
from phase29.messages import assert_concise_payload, build_signal_payload


class Phase29DeliveryLedger:
    """Append-only ledger; SENT and DRY_RUN both suppress duplicates."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") in {"SENT", "DRY_RUN"}:
                key = row.get("dedupe_key")
                if key:
                    self._seen.add(str(key))

    @staticmethod
    def dedupe_key(decision_id: str, action: str) -> str:
        return f"P29_SHADOW_{action}:{decision_id}"

    def already_sent(self, decision_id: str, action: str) -> bool:
        return self.dedupe_key(decision_id, action) in self._seen

    def record(self, decision_id: str, action: str, result: dict[str, Any]) -> None:
        key = self.dedupe_key(decision_id, action)
        if result.get("status") in {"SENT", "DRY_RUN"}:
            self._seen.add(key)
        row = {
            "dedupe_key": key,
            "decision_id": decision_id,
            "message_type": f"P29_SHADOW_{action}",
            "status": result.get("status"),
            "attempts": result.get("attempts"),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def deliver_decision(
    *,
    decision: dict[str, Any],
    ledger: Phase29DeliveryLedger,
    discord_enabled: bool,
    dry_run: bool,
    notify_wait: bool,
    transport=None,
) -> dict[str, Any]:
    """Send concise Discord for baseline BUY/SELL (WAIT only if notify_wait)."""
    action = str(decision.get("experimental_action", "WAIT")).upper()
    if action == "WAIT" and not notify_wait:
        return {"status": "SKIPPED_WAIT", "journaled_before_discord": True}
    if action not in {"BUY", "SELL", "WAIT"}:
        return {"status": "SKIPPED_UNSUPPORTED", "journaled_before_discord": True}
    if not discord_enabled:
        return {"status": "SKIPPED_DISABLED", "journaled_before_discord": True}

    dec_id = decision["decision_id"]
    if ledger.already_sent(dec_id, action):
        return {"status": "SKIPPED_DUPLICATE", "journaled_before_discord": True}

    payload = build_signal_payload(decision)
    assert_concise_payload(payload["content"])

    if dry_run or not webhook_configured():
        delivery = {
            "status": "DRY_RUN" if dry_run else "FAILED_CONFIG",
            "journaled_before_discord": True,
            "http_status": None,
        }
        ledger.record(dec_id, action, delivery)
        return delivery

    url = load_webhook_url()
    assert url is not None
    result = post_webhook(url, payload, transport=transport)
    result["journaled_before_discord"] = True
    if result.get("error"):
        result["error"] = redact_secrets(str(result["error"]))
    ledger.record(dec_id, action, result)
    return result


def make_ledger(root: Path) -> Phase29DeliveryLedger:
    return Phase29DeliveryLedger(Path(root) / "discord_delivery_ledger.jsonl")
