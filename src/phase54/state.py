"""Persistent agent state — restart recovery / idempotency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase54.constants import STATE_DIR
from phase54.progress import write_json
from phase54.timeutil import now_utc_iso


class AgentState:
    def __init__(self, path: Path | None = None):
        self.path = path or (STATE_DIR / "agent_state.json")
        self.data: dict[str, Any] = {
            "processed_decision_keys": [],
            "processed_observation_ids": [],
            "open_positions": {},
            "closed_position_ids": [],
            "risk_snapshot": {},
            "last_success_iso": None,
            "errors": [],
            "cursor": {"day": None, "decision_idx": None},
            "counts": {"observations": 0, "decisions": 0, "buy": 0, "sell": 0, "wait": 0, "opens": 0, "closes": 0, "dq_reject": 0},
        }
        if self.path.is_file():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.data["saved_iso"] = now_utc_iso()
        write_json(self.path, self.data)

    def decision_key(self, day: str, decision_idx: int) -> str:
        return f"{day}:{decision_idx}"

    def already_processed(self, day: str, decision_idx: int) -> bool:
        return self.decision_key(day, decision_idx) in set(self.data.get("processed_decision_keys") or [])

    def mark_processed(self, day: str, decision_idx: int, observation_id: str | None = None) -> None:
        key = self.decision_key(day, decision_idx)
        keys = list(self.data.get("processed_decision_keys") or [])
        if key not in keys:
            keys.append(key)
        self.data["processed_decision_keys"] = keys
        if observation_id:
            oids = list(self.data.get("processed_observation_ids") or [])
            if observation_id not in oids:
                oids.append(observation_id)
            self.data["processed_observation_ids"] = oids
        self.data["cursor"] = {"day": day, "decision_idx": decision_idx}
        self.data["last_success_iso"] = now_utc_iso()

    def bump(self, field: str, n: int = 1) -> None:
        c = dict(self.data.get("counts") or {})
        c[field] = int(c.get(field) or 0) + n
        self.data["counts"] = c

    def record_error(self, msg: str) -> None:
        errs = list(self.data.get("errors") or [])
        errs.append({"iso": now_utc_iso(), "message": msg})
        self.data["errors"] = errs[-100:]
