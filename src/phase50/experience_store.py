"""Separate HISTORICAL_HYPOTHETICAL and AGENT_SHADOW stores — never merge."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase50.availability import experience_available_at
from phase50.constants import (
    DATA_DIR,
    EXPERIENCE_SCHEMA_VERSION,
    LEARNER_VERSION,
    MARKET_STATE_VERSION,
    POLICY_VERSION,
)
from phase50.schemas import validate_experience

UTC = timezone.utc


class ExperienceStore:
    def __init__(self, source: str, root: Path | None = None):
        if source not in ("HISTORICAL_HYPOTHETICAL", "AGENT_SHADOW"):
            raise ValueError(source)
        self.source = source
        self.root = root or (DATA_DIR / source)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "experiences.jsonl"
        self._records: list[dict[str, Any]] = []
        if self.path.is_file():
            self._records = [
                json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()
            ]

    def clear(self) -> None:
        self._records = []
        if self.path.is_file():
            self.path.write_text("", encoding="utf-8")

    def all(self) -> list[dict[str, Any]]:
        return list(self._records)

    def available_at(self, decision_timestamp_utc: str) -> list[dict[str, Any]]:
        return experience_available_at(self._records, decision_timestamp_utc)

    def append(self, rec: dict[str, Any]) -> None:
        if rec.get("source") != self.source:
            raise ValueError(f"refusing cross-store append: {rec.get('source')} into {self.source}")
        errs = validate_experience(rec)
        if errs:
            raise ValueError(f"invalid experience: {errs}")
        self._records.append(rec)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for r in self._records:
                f.write(json.dumps(r, sort_keys=True, separators=(",", ":"), default=str) + "\n")

    @property
    def n(self) -> int:
        return len(self._records)


def new_experience(
    *,
    source: str,
    decision_timestamp_utc: str,
    market_state_id: str,
    action: str,
    decision_context: dict[str, Any],
    actual_costed_outcome_net_r: float,
    outcome_horizon_bars: int,
    outcome_timestamp_utc: str,
    regime_context: dict[str, Any],
    policy_version: str = POLICY_VERSION,
    expected_value: float | None = None,
    decision_reason: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec: dict[str, Any] = {
        "experience_id": uuid.uuid4().hex,
        "source": source,
        "decision_timestamp_utc": decision_timestamp_utc,
        "market_state_id": market_state_id,
        "action": action,
        "decision_context": decision_context,
        "expected_value": expected_value,
        "actual_costed_outcome_net_r": float(actual_costed_outcome_net_r),
        "outcome_horizon_bars": int(outcome_horizon_bars),
        "outcome_timestamp_utc": outcome_timestamp_utc,
        "regime_context": regime_context,
        "feature_representation_version": MARKET_STATE_VERSION,
        "policy_version": policy_version,
        "learner_version": LEARNER_VERSION,
        "creation_timestamp_utc": now,
        "experience_schema_version": EXPERIENCE_SCHEMA_VERSION,
        "confidence": confidence,
    }
    if source == "AGENT_SHADOW":
        rec["decision_reason"] = decision_reason or "unspecified"
    return rec


def dual_query(
    hist: ExperienceStore,
    shadow: ExperienceStore,
    decision_timestamp_utc: str,
    *,
    mode: str,
) -> dict[str, list[dict[str, Any]]]:
    """mode: historical | shadow | dual | none — stores remain separate dict keys."""
    h = hist.available_at(decision_timestamp_utc) if mode in ("historical", "dual") else []
    s = shadow.available_at(decision_timestamp_utc) if mode in ("shadow", "dual") else []
    return {"HISTORICAL_HYPOTHETICAL": h, "AGENT_SHADOW": s}
