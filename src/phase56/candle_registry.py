"""Durable candle-level idempotency (timestamp + content hash)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from phase56.constants import STATE_DIR
from phase56.progress import write_json


def candle_hash(bar: dict[str, Any]) -> str:
    payload = {
        "timestamp_utc": str(bar.get("timestamp_utc")),
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CandleRegistry:
    def __init__(self, path=None):
        self.path = path or (STATE_DIR / "candle_registry.json")
        self.data: dict[str, Any] = {
            "by_ts": {},  # ts -> hash
            "last_ts": None,
            "last_hash": None,
            "rejected": [],
        }
        if self.path.is_file():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self) -> None:
        write_json(self.path, self.data)

    def evaluate(self, bar: dict[str, Any], *, policy_version: str) -> dict[str, Any]:
        ts = str(bar.get("timestamp_utc"))
        h = candle_hash(bar)
        key = f"{ts}|{policy_version}"
        prev = (self.data.get("by_ts") or {}).get(ts)
        if prev is not None:
            if prev == h:
                return {
                    "accept": False,
                    "reason": "DUPLICATE_CANDLE_TIMESTAMP",
                    "timestamp_utc": ts,
                    "hash": h,
                    "decision_key": key,
                }
            return {
                "accept": False,
                "reason": "CONFLICTING_DUPLICATE_HASH",
                "timestamp_utc": ts,
                "hash": h,
                "prior_hash": prev,
                "decision_key": key,
            }
        last = self.data.get("last_ts")
        if last is not None and ts <= str(last):
            return {
                "accept": False,
                "reason": "NON_CHRONOLOGICAL_OR_REPLAYED",
                "timestamp_utc": ts,
                "last_ts": last,
                "hash": h,
                "decision_key": key,
            }
        return {"accept": True, "reason": "NEW_CANDLE", "timestamp_utc": ts, "hash": h, "decision_key": key}

    def commit(self, bar: dict[str, Any], *, policy_version: str) -> None:
        ts = str(bar["timestamp_utc"])
        h = candle_hash(bar)
        by = dict(self.data.get("by_ts") or {})
        by[ts] = h
        self.data["by_ts"] = by
        self.data["last_ts"] = ts
        self.data["last_hash"] = h
        self.data["last_policy_version"] = policy_version
        self.save()

    def reject(self, reason: str, ts: str, detail: dict | None = None) -> None:
        rows = list(self.data.get("rejected") or [])
        rows.append({"reason": reason, "timestamp_utc": ts, **(detail or {})})
        self.data["rejected"] = rows[-200:]
        self.save()
