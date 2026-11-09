"""Duplicate prevention for Discord delivery events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase16b.constants import DATA_DIR


class DeliveryLedger:
    """Append-only delivery ledger keyed by event_id / decision_id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DATA_DIR / "discord_delivery_ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Only successful deliveries suppress retries.
            if row.get("status") != "SENT":
                continue
            key = row.get("dedupe_key")
            if key:
                self._seen.add(str(key))

    @staticmethod
    def dedupe_key(event: dict[str, Any]) -> str:
        from phase16b.formatter import resolve_message_type

        event_id = event.get("event_id") or event.get("decision_id")
        if not event_id:
            raise ValueError("event requires event_id or decision_id for dedupe")
        msg_type = resolve_message_type(event)
        return f"{msg_type}:{event_id}"

    def already_sent(self, event: dict[str, Any]) -> bool:
        return self.dedupe_key(event) in self._seen

    def record(self, event: dict[str, Any], result: dict[str, Any]) -> None:
        key = self.dedupe_key(event)
        # Only mark as sent on success to allow retry after failure
        if result.get("status") == "SENT":
            self._seen.add(key)
        row = {
            "dedupe_key": key,
            "event_id": event.get("event_id"),
            "decision_id": event.get("decision_id"),
            "message_type": event.get("message_type"),
            "status": result.get("status"),
            "attempts": result.get("attempts"),
            # Never store webhook URL
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
