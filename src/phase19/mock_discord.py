"""Mock Discord delivery for Phase 19 — never posts unless explicit live flag."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MockDiscordClient:
    """In-memory + optional JSONL capture. No network I/O."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.sent: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def dedupe_key(event: dict[str, Any]) -> str:
        msg = event.get("message_type") or "UNKNOWN"
        eid = event.get("event_id") or event.get("decision_id")
        if not eid:
            raise ValueError("event requires event_id")
        return f"{msg}:{eid}"

    def already_sent(self, event: dict[str, Any]) -> bool:
        return self.dedupe_key(event) in self._seen

    def deliver(self, event: dict[str, Any], payload: dict[str, str]) -> dict[str, Any]:
        key = self.dedupe_key(event)
        if key in self._seen:
            return {"status": "SKIPPED_DUPLICATE", "dedupe_key": key, "http_status": None}
        row = {
            "dedupe_key": key,
            "event_id": event.get("event_id"),
            "decision_id": event.get("decision_id"),
            "message_type": event.get("message_type"),
            "status": "MOCK_SENT",
            "http_status": 204,
            "attempts": 1,
            "content": payload.get("content", ""),
        }
        self.sent.append(row)
        self._seen.add(key)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        return {"status": "MOCK_SENT", "dedupe_key": key, "http_status": 204, "attempts": 1}
