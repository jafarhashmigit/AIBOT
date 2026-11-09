"""Strict separation of historical hypothetical vs agent shadow experience."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase18.constants import (
    EXPERIENCE_VERSION,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
    STRATEGY_ID,
)


EXPERIENCE_FIELDS = [
    "experience_id",
    "source",
    "event_id",
    "decision_id",
    "outcome_event_id",
    "decision_timestamp_utc",
    "symbol",
    "side",
    "horizon_id",
    "horizon_label",
    "selected_horizon",
    "feature_context_ref",
    "model_strategy_version",
    "action",
    "outcome",
    "realized_r",
    "outcome_timestamp_utc",
    "experience_version",
]


class ExperienceStore:
    """Append-only JSONL stores with source separation."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.shadow_path = self.root / "agent_shadow_experience.jsonl"
        self.historical_path = self.root / "historical_hypothetical_experience.jsonl"
        self._shadow_ids: set[str] = set()
        self._hist_ids: set[str] = set()
        self._load_ids()

    def _load_ids(self) -> None:
        for path, bucket in (
            (self.shadow_path, self._shadow_ids),
            (self.historical_path, self._hist_ids),
        ):
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = row.get("experience_id")
                if eid:
                    bucket.add(str(eid))

    @staticmethod
    def experience_id(*, source: str, outcome_event_id: str) -> str:
        return f"{source}:{outcome_event_id}"

    def _append(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def add_shadow_from_outcome(
        self,
        outcome: dict[str, Any],
        *,
        feature_context_ref: str = "",
        selected_horizon: str = "NOT ESTABLISHED",
    ) -> dict[str, Any] | None:
        status = str(outcome.get("status", "")).upper()
        if status not in {"PASS", "FAIL", "TIMEOUT"}:
            return None
        side = str(outcome.get("side", "")).upper()
        if side not in {"BUY", "SELL"}:
            return None
        eid = self.experience_id(source=SOURCE_SHADOW, outcome_event_id=outcome["outcome_event_id"])
        if eid in self._shadow_ids:
            return None
        row = {
            "experience_id": eid,
            "source": SOURCE_SHADOW,
            "event_id": outcome.get("decision_id", ""),
            "decision_id": outcome.get("decision_id", ""),
            "outcome_event_id": outcome.get("outcome_event_id", ""),
            "decision_timestamp_utc": outcome.get("decision_timestamp_utc", ""),
            "symbol": outcome.get("symbol", "XAUUSD"),
            "side": side,
            "horizon_id": outcome.get("horizon_id", ""),
            "horizon_label": outcome.get("horizon_label", ""),
            "selected_horizon": selected_horizon,
            "feature_context_ref": feature_context_ref or outcome.get("decision_id", ""),
            "model_strategy_version": STRATEGY_ID,
            "action": side,
            "outcome": status,
            "realized_r": outcome.get("realized_r", ""),
            "outcome_timestamp_utc": outcome.get("outcome_timestamp_utc", ""),
            "experience_version": EXPERIENCE_VERSION,
        }
        self._append(self.shadow_path, row)
        self._shadow_ids.add(eid)
        return row

    def add_historical(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Record historical hypothetical experience (never merged into shadow store)."""
        outcome_event_id = record.get("outcome_event_id") or record.get("event_id")
        if not outcome_event_id:
            raise ValueError("historical experience requires outcome_event_id")
        eid = self.experience_id(source=SOURCE_HISTORICAL, outcome_event_id=str(outcome_event_id))
        if eid in self._hist_ids:
            return None
        row = {
            "experience_id": eid,
            "source": SOURCE_HISTORICAL,
            "event_id": record.get("event_id", outcome_event_id),
            "decision_id": record.get("decision_id", ""),
            "outcome_event_id": str(outcome_event_id),
            "decision_timestamp_utc": record.get("decision_timestamp_utc", ""),
            "symbol": record.get("symbol", "XAUUSD"),
            "side": str(record.get("side", "")).upper(),
            "horizon_id": record.get("horizon_id", "H12"),
            "horizon_label": record.get("horizon_label", "60M"),
            "selected_horizon": record.get("selected_horizon", "NOT ESTABLISHED"),
            "feature_context_ref": record.get("feature_context_ref", ""),
            "model_strategy_version": record.get("model_strategy_version", "HISTORICAL"),
            "action": str(record.get("action", record.get("side", ""))).upper(),
            "outcome": str(record.get("outcome", "")).upper(),
            "realized_r": record.get("realized_r", ""),
            "outcome_timestamp_utc": record.get("outcome_timestamp_utc", ""),
            "experience_version": EXPERIENCE_VERSION,
        }
        self._append(self.historical_path, row)
        self._hist_ids.add(eid)
        return row

    def list_shadow(self) -> list[dict[str, Any]]:
        return self._read_all(self.shadow_path)

    def list_historical(self) -> list[dict[str, Any]]:
        return self._read_all(self.historical_path)

    @staticmethod
    def _read_all(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def counts(self) -> dict[str, int]:
        return {
            "agent_shadow": len(self._shadow_ids),
            "historical_hypothetical": len(self._hist_ids),
        }
