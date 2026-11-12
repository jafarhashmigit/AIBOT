"""Immutable MarketSnapshot persistence — deterministic hash; UNKNOWN stays explicit."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_1.constants import SNAPSHOT_DIR, SNAPSHOT_SCHEMA_VERSION, canonical_json, canonical_json_sha256, sha256_hex
from phase64_1.progress import write_json


class SnapshotError(ValueError):
    pass


class CrashInjected(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unknown(v: Any) -> Any:
    return "UNKNOWN" if v is None else v


def build_snapshot_from_observation(
    obs: dict[str, Any],
    *,
    account_profile: dict[str, Any] | None = None,
    source_domain: str = "AGENT_SHADOW",
) -> dict[str, Any]:
    """Build snapshot body from observation. Missing fields → UNKNOWN; never invent prices."""
    profile = account_profile or {}
    bid = obs.get("bid")
    ask = obs.get("ask")
    spread = obs.get("spread")
    if spread is None and bid is not None and ask is not None:
        try:
            spread = float(ask) - float(bid)
        except (TypeError, ValueError):
            spread = None
    digits = profile.get("digits")
    body = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "symbol": obs.get("symbol") or profile.get("symbol") or "UNKNOWN",
        "active_broker_profile": {
            "broker": _unknown(profile.get("broker")),
            "environment": _unknown(profile.get("environment")),
            "platform": _unknown(profile.get("platform")),
            "symbol": _unknown(profile.get("symbol") or obs.get("symbol")),
            "verification_status": _unknown(profile.get("verification_status")),
        },
        "timeframe": obs.get("timeframe") or "UNKNOWN",
        "bar_timestamp_utc": obs.get("bar_timestamp_utc") or "UNKNOWN",
        "observation_timestamp_utc": obs.get("created_iso") or obs.get("observation_timestamp_utc") or "UNKNOWN",
        "source_timestamp_utc": obs.get("bar_timestamp_utc") or "UNKNOWN",
        "timezone": "UTC",
        "bid": _unknown(bid),
        "ask": _unknown(ask),
        "spread": _unknown(spread),
        "price_precision_digits": _unknown(digits),
        "observation_id": obs.get("observation_id") or "UNKNOWN",
        "market_state_id": obs.get("market_state_id") or "UNKNOWN",
        "candle_hash": obs.get("candle_hash") or "UNKNOWN",
        "tick_path_ref": obs.get("tick_path_status") or obs.get("tick_ref") or "UNKNOWN",
        "data_quality_status": obs.get("data_quality_status") or ("OK" if obs.get("accepted") else "REJECTED"),
        "source_domain": source_domain,
        "source_data_reference": {
            "day": obs.get("day") or "UNKNOWN",
            "decision_idx": obs.get("decision_idx") if obs.get("decision_idx") is not None else "UNKNOWN",
            "feature_version": obs.get("feature_version") or "UNKNOWN",
        },
    }
    # Hash excludes mutable ids assigned at commit
    snapshot_hash = sha256_hex(canonical_json(body))
    body["snapshot_hash"] = snapshot_hash
    return body


class MarketSnapshotStore:
    """Append-only immutable snapshots. Same hash → reuse; conflicting body → error."""

    def __init__(self, root: Path | None = None, *, crash_at: str | None = None):
        self.root = root or SNAPSHOT_DIR
        self.path = self.root / "snapshots.jsonl"
        self.index_path = self.root / "snapshot_index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.crash_at = crash_at
        self._by_hash: dict[str, dict[str, Any]] = {}
        self._by_id: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        self._by_hash = {}
        self._by_id = {}
        if not self.path.is_file():
            self._persist_index()
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            h = rec.get("snapshot_hash")
            sid = rec.get("snapshot_id")
            if h and sid:
                self._by_hash[h] = rec
                self._by_id[sid] = rec
        self._persist_index()

    def _persist_index(self) -> None:
        write_json(
            self.index_path,
            {
                "n": len(self._by_id),
                "ids": sorted(self._by_id.keys()),
                "updated_utc": _utc(),
            },
        )

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        return self._by_id.get(snapshot_id)

    def get_by_hash(self, snapshot_hash: str) -> dict[str, Any] | None:
        return self._by_hash.get(snapshot_hash)

    def verify(self, snapshot_id: str) -> tuple[bool, str]:
        rec = self._by_id.get(snapshot_id)
        if not rec:
            return False, "missing_snapshot"
        body = {k: v for k, v in rec.items() if k not in ("snapshot_id", "committed_utc", "immutable")}
        # Recompute hash from content fields excluding snapshot_id/committed
        # Stored snapshot_hash was computed before snapshot_id assignment
        stored = rec.get("snapshot_hash")
        # Rebuild pre-id body: drop snapshot_id, committed_utc, immutable
        pre = {k: v for k, v in rec.items() if k not in ("snapshot_id", "committed_utc", "immutable")}
        # snapshot_hash is inside pre — remove it for recompute then compare
        pre2 = {k: v for k, v in pre.items() if k != "snapshot_hash"}
        recomputed = sha256_hex(canonical_json(pre2))
        if recomputed != stored:
            return False, "corrupt_snapshot_hash"
        return True, "ok"

    def commit(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotError("bad_schema")
        pre = {k: v for k, v in body.items() if k not in ("snapshot_id", "committed_utc", "immutable", "snapshot_hash")}
        snapshot_hash = sha256_hex(canonical_json(pre))
        if body.get("snapshot_hash") and body["snapshot_hash"] != snapshot_hash:
            raise SnapshotError("hash_mismatch_before_commit")
        existing = self._by_hash.get(snapshot_hash)
        if existing:
            return existing
        rec = dict(pre)
        rec["snapshot_hash"] = snapshot_hash
        rec["snapshot_id"] = uuid.uuid4().hex
        rec["committed_utc"] = _utc()
        rec["immutable"] = True
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._by_hash[snapshot_hash] = rec
        self._by_id[rec["snapshot_id"]] = rec
        self._persist_index()
        if self.crash_at == "after_snapshot_persistence":
            raise CrashInjected("after_snapshot_persistence")
        return rec


def commit_observation_snapshot(
    store: MarketSnapshotStore,
    obs: dict[str, Any],
    *,
    account_profile: dict[str, Any] | None = None,
    source_domain: str = "AGENT_SHADOW",
) -> dict[str, Any]:
    body = build_snapshot_from_observation(obs, account_profile=account_profile, source_domain=source_domain)
    return store.commit(body)
