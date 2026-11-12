"""Separate observer journals with restart-safe idempotency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ObserverJournal:
    def __init__(self, root: Path, observer_id: str):
        self.root = Path(root)
        self.observer_id = observer_id
        self.path = self.root / f"journal_{observer_id}.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] | None = None

    def _load_seen(self) -> set[str]:
        if self._seen is not None:
            return self._seen
        seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row.get("idempotency_key") or row.get("decision_id")
                if key:
                    seen.add(str(key))
        self._seen = seen
        return seen

    def has(self, idempotency_key: str) -> bool:
        return idempotency_key in self._load_seen()

    def append(self, row: dict[str, Any]) -> bool:
        """Append if new. Returns True if written, False if duplicate."""
        key = str(row["idempotency_key"])
        seen = self._load_seen()
        if key in seen:
            return False
        row = dict(row)
        row["observer_id"] = self.observer_id
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        seen.add(key)
        return True

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


class OutcomeStore:
    """Pending/matured outcomes per observer (separate files)."""

    def __init__(self, root: Path, observer_id: str):
        self.root = Path(root)
        self.observer_id = observer_id
        self.path = self.root / f"outcomes_{observer_id}.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, row: dict[str, Any]) -> bool:
        key = str(row["outcome_event_id"])
        existing = {r["outcome_event_id"] for r in self.read_all()}
        if key in existing:
            return False
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        return True

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def upsert_status(self, outcome_event_id: str, updates: dict[str, Any]) -> None:
        rows = self.read_all()
        found = False
        for r in rows:
            if r["outcome_event_id"] == outcome_event_id:
                r.update(updates)
                found = True
                break
        if not found:
            return
        with self.path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
