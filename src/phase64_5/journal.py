"""Append-only broker evidence journal with crash-safe recovery."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from phase64_5.constants import (
    FORBIDDEN_KEYS,
    JOURNAL_SCHEMA_VERSION,
    SIMULATED_LABEL,
    bytes_sha256,
    canonical_json_sha256,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reject_forbidden(obj: dict[str, Any]) -> None:
    for k in obj:
        if str(k).lower() in FORBIDDEN_KEYS:
            raise ValueError(f"forbidden_key:{k}")


class BrokerEvidenceJournal:
    """
    Durable genuine/fixture-aware journal.
    Set allow_synthetic=False (default) for genuine store — rejects synthetic rows.
    """

    def __init__(self, root: Path, *, allow_synthetic: bool = False, store_label: str = "GENUINE"):
        self.root = root
        self.allow_synthetic = allow_synthetic
        self.store_label = store_label
        self.raw_dir = root / "raw"
        self.events_path = root / "events.jsonl"
        self.index_path = root / "dedup_index.json"
        self.quarantine_path = root / "quarantine.jsonl"
        self.incidents_path = root / "reconciliation_incidents.jsonl"
        self.batches_path = root / "import_batches.jsonl"
        self.wal_dir = root / "wal"
        self.meta_path = root / "journal_meta.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.is_file():
            self._write_json_atomic(self.index_path, {"keys": {}, "n": 0, "schema_version": JOURNAL_SCHEMA_VERSION})
        if not self.meta_path.is_file():
            self._write_json_atomic(
                self.meta_path,
                {
                    "created_utc": _utc(),
                    "schema_version": JOURNAL_SCHEMA_VERSION,
                    "store_label": store_label,
                    "allow_synthetic": allow_synthetic,
                    "n_events": 0,
                    "n_quarantine": 0,
                    "n_raw": 0,
                },
            )
        self._recover_wal()

    @staticmethod
    def _write_json_atomic(path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _recover_wal(self) -> None:
        for wal in sorted(self.wal_dir.glob("*.json")):
            try:
                rec = json.loads(wal.read_text(encoding="utf-8"))
            except Exception:
                q = self.root / "quarantine_wal"
                q.mkdir(exist_ok=True)
                wal.replace(q / f"corrupt_{wal.name}")
                continue
            if not any(e.get("event_id") == rec.get("event_id") for e in self.all_events()):
                self._append_event_line(rec)
                self._index_apply(rec)
            wal.unlink(missing_ok=True)

    def _load_index(self) -> dict[str, Any]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"keys": {}, "n": 0, "corrupt": True}

    def save_raw_bytes(self, *, source_name: str, content: bytes, provenance: str) -> dict[str, Any]:
        h = bytes_sha256(content)
        dest = self.raw_dir / f"{h[:16]}_{Path(source_name).name}"
        if not dest.is_file():
            dest.write_bytes(content)
        meta = {
            "source_name": source_name,
            "path": str(dest),
            "sha256": h,
            "provenance": provenance,
            "saved_utc": _utc(),
            "size_bytes": len(content),
            "store_label": self.store_label,
        }
        sm = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sm["n_raw"] = len(list(self.raw_dir.glob("*")))
        sm["updated_utc"] = _utc()
        self._write_json_atomic(self.meta_path, sm)
        return meta

    def begin_batch(self, *, source_file: str, source_sha256: str, parser_version: str) -> str:
        batch_id = f"batch_{uuid.uuid4().hex}"
        rec = {
            "batch_id": batch_id,
            "source_file": source_file,
            "source_sha256": source_sha256,
            "parser_version": parser_version,
            "started_utc": _utc(),
            "store_label": self.store_label,
        }
        with self.batches_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return batch_id

    def quarantine(self, row: dict[str, Any], reason: str) -> None:
        entry = {**row, "quarantine_reason": reason, "quarantined_utc": _utc()}
        with self.quarantine_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        sm = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sm["n_quarantine"] = int(sm.get("n_quarantine") or 0) + 1
        sm["updated_utc"] = _utc()
        self._write_json_atomic(self.meta_path, sm)

    def raise_incident(self, incident: dict[str, Any]) -> None:
        incident = {**incident, "incident_utc": _utc(), "store_label": self.store_label}
        with self.incidents_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(incident, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _append_event_line(self, rec: dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _is_incomplete_m5(record: dict[str, Any]) -> bool:
        """True if record is a forming/incomplete M5 (must not lock market identity forever)."""
        if record.get("kind") != "M5_BAR":
            return False
        if record.get("evidence_provenance") == "LIVE_INCOMPLETE_OR_FORMING_M5":
            return True
        try:
            ts = record.get("server_timestamp_utc")
            coll = record.get("collection_timestamp_utc") or record.get("ingested_utc")
            if not ts or not coll:
                return False
            srv = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            cot = datetime.fromisoformat(str(coll).replace("Z", "+00:00"))
            if srv.tzinfo is None:
                srv = srv.replace(tzinfo=timezone.utc)
            if cot.tzinfo is None:
                cot = cot.replace(tzinfo=timezone.utc)
            return (srv + timedelta(minutes=5)) > cot
        except Exception:
            return False

    @staticmethod
    def market_identity_key(record: dict[str, Any]) -> str | None:
        """Canonical market identity independent of stable_key schema version / content hash."""
        kind = record.get("kind")
        symbol = record.get("symbol")
        ts = record.get("server_timestamp_utc")
        if not kind or not symbol or not ts:
            return None
        tf = record.get("timeframe") or ("M5" if kind == "M5_BAR" else "TICK_SNAPSHOT")
        return f"{kind}|{symbol}|{tf}|{ts}"

    @staticmethod
    def canonical_market_hash(record: dict[str, Any]) -> str | None:
        """Recompute market-only hash from OHLC/quote fields (ignores legacy polluted body_hash)."""
        kind = record.get("kind")
        symbol = record.get("symbol")
        ts = record.get("server_timestamp_utc")
        if not kind or not symbol or not ts:
            return None
        if kind == "M5_BAR":
            payload: dict[str, Any] = {
                "kind": "M5_BAR",
                "symbol": symbol,
                "timeframe": "M5",
                "server_timestamp_utc": ts,
                "open": record.get("open"),
                "high": record.get("high"),
                "low": record.get("low"),
                "close": record.get("close"),
                "tick_volume": record.get("tick_volume"),
            }
            if record.get("spread_points_bar") is not None:
                payload["spread_points_bar"] = record.get("spread_points_bar")
            rv = record.get("real_volume")
            if rv is not None and float(rv) != 0.0:
                payload["real_volume"] = rv
            return canonical_json_sha256(payload)
        if kind == "QUOTE_SNAPSHOT":
            payload = {
                "kind": "QUOTE_SNAPSHOT",
                "symbol": symbol,
                "timeframe": "TICK_SNAPSHOT",
                "server_timestamp_utc": ts,
                "bid": record.get("bid"),
                "ask": record.get("ask"),
                "spread": record.get("spread"),
            }
            return canonical_json_sha256(payload)
        return record.get("body_hash")

    def _index_apply(self, rec: dict[str, Any]) -> None:
        idx = self._load_index()
        keys = idx.setdefault("keys", {})
        keys[rec["stable_key"]] = {
            "body_hash": rec.get("body_hash"),
            "event_id": rec.get("event_id"),
            "ingested_utc": rec.get("ingested_utc"),
        }
        mid = self.market_identity_key(rec)
        if mid:
            mids = idx.setdefault("market_ids", {})
            mids[mid] = {
                "body_hash": self.canonical_market_hash(rec) or rec.get("body_hash"),
                "event_id": rec.get("event_id"),
                "stable_key": rec.get("stable_key"),
                "ingested_utc": rec.get("ingested_utc"),
            }
            idx["n_market_ids"] = len(mids)
        idx["n"] = len(keys)
        idx["schema_version"] = JOURNAL_SCHEMA_VERSION
        self._write_json_atomic(self.index_path, idx)

    def append_event(
        self,
        record: dict[str, Any],
        *,
        import_batch_id: str,
        crash_after_wal: bool = False,
    ) -> dict[str, Any]:
        _reject_forbidden(record)
        if record.get("synthetic") and not self.allow_synthetic:
            self.quarantine(record, "synthetic_forbidden_in_genuine_store")
            return {"status": "QUARANTINED", "reason": "synthetic_forbidden_in_genuine_store"}
        if record.get("evidence_label") == SIMULATED_LABEL and not self.allow_synthetic:
            self.quarantine(record, "simulated_fixture_forbidden_in_genuine_store")
            return {"status": "QUARANTINED", "reason": "simulated_fixture_forbidden_in_genuine_store"}

        stable_key = record.get("stable_key")
        body_hash = record.get("body_hash")
        if not stable_key or not body_hash or not record.get("event_id"):
            self.quarantine(record, "missing_stable_identity")
            return {"status": "QUARANTINED", "reason": "missing_stable_identity"}

        idx = self._load_index()
        keys = idx.setdefault("keys", {})
        mids = idx.setdefault("market_ids", {})
        # Ensure market_ids populated for legacy journals (lazy rebuild once if empty)
        if not mids and keys:
            self.reconstruct_index()
            idx = self._load_index()
            keys = idx.setdefault("keys", {})
            mids = idx.setdefault("market_ids", {})

        if stable_key in keys:
            prev = keys[stable_key]
            if prev.get("body_hash") == body_hash:
                return {"status": "DUPLICATE_SUPPRESSED", "key": stable_key, "event_id": prev.get("event_id")}
            # Schema migration: stored body_hash may include obsolete real_volume=0; compare market-only hash
            prior_row = None
            for e in self.all_events():
                if e.get("event_id") == prev.get("event_id") or e.get("stable_key") == stable_key:
                    prior_row = e
                    break
            incoming_mhash = self.canonical_market_hash(record)
            prior_mhash = self.canonical_market_hash(prior_row) if prior_row else None
            if incoming_mhash and prior_mhash and incoming_mhash == prior_mhash:
                return {
                    "status": "DUPLICATE_SUPPRESSED",
                    "key": stable_key,
                    "event_id": prev.get("event_id"),
                    "via": "canonical_market_hash",
                }
            incident = {
                "type": "CONFLICTING_EVIDENCE",
                "stable_key": stable_key,
                "prior": prev,
                "incoming_event_id": record.get("event_id"),
                "incoming_body_hash": body_hash,
                "incoming_market_hash": incoming_mhash,
                "prior_market_hash": prior_mhash,
            }
            self.raise_incident(incident)
            self.quarantine({**record, "prior": prev}, "conflicting_broker_evidence")
            return {"status": "QUARANTINED", "reason": "conflicting_broker_evidence", "key": stable_key}

        mid = self.market_identity_key(record)
        if mid and mid in mids:
            prev = mids[mid]
            incoming_mhash = self.canonical_market_hash(record) or body_hash
            prior_mhash = prev.get("body_hash")
            if prior_mhash == incoming_mhash or prior_mhash == body_hash:
                return {
                    "status": "DUPLICATE_SUPPRESSED",
                    "key": stable_key,
                    "market_identity_key": mid,
                    "event_id": prev.get("event_id"),
                    "via": "market_identity",
                }
            # Closed bar may supersede a previously journalled forming bar (legacy pollution)
            prior_row = None
            for e in self.all_events():
                if e.get("event_id") == prev.get("event_id") or self.market_identity_key(e) == mid:
                    prior_row = e
                    break
            incoming_closed = not self._is_incomplete_m5(record)
            if prior_row is not None and self._is_incomplete_m5(prior_row) and incoming_closed:
                self.raise_incident(
                    {
                        "type": "FORMING_BAR_SUPERSEDED_BY_CLOSED",
                        "market_identity_key": mid,
                        "prior_event_id": prev.get("event_id"),
                        "incoming_event_id": record.get("event_id"),
                    }
                )
                # Fall through to ingest closed bar; index will point at closed OHLC
            else:
                incident = {
                    "type": "CONFLICTING_EVIDENCE",
                    "market_identity_key": mid,
                    "stable_key": stable_key,
                    "prior": prev,
                    "incoming_event_id": record.get("event_id"),
                    "incoming_body_hash": body_hash,
                    "incoming_market_hash": incoming_mhash,
                }
                self.raise_incident(incident)
                self.quarantine({**record, "prior": prev}, "conflicting_broker_evidence")
                return {
                    "status": "QUARANTINED",
                    "reason": "conflicting_broker_evidence",
                    "key": stable_key,
                    "market_identity_key": mid,
                }

        rec = {
            **record,
            "journal_schema_version": JOURNAL_SCHEMA_VERSION,
            "import_batch_id": import_batch_id,
            "ingested_utc": _utc(),
            "store_label": self.store_label,
        }
        # WAL then commit
        wal = self.wal_dir / f"{rec['event_id']}.json"
        wal.write_text(json.dumps(rec, sort_keys=True, default=str), encoding="utf-8")
        if crash_after_wal:
            raise RuntimeError("CrashInjected:after_wal_before_commit")
        self._append_event_line(rec)
        self._index_apply(rec)
        wal.unlink(missing_ok=True)
        sm = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sm["n_events"] = int(sm.get("n_events") or 0) + 1
        sm["updated_utc"] = _utc()
        self._write_json_atomic(self.meta_path, sm)
        return {"status": "INGESTED", "key": stable_key, "event_id": rec["event_id"]}

    def all_events(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        out = []
        for i, line in enumerate(self.events_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                self.quarantine({"raw_line": line, "line_no": i}, "corrupt_journal_line")
        return out

    def quarantine_rows(self) -> list[dict[str, Any]]:
        if not self.quarantine_path.is_file():
            return []
        return [json.loads(l) for l in self.quarantine_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def incidents(self) -> list[dict[str, Any]]:
        if not self.incidents_path.is_file():
            return []
        return [json.loads(l) for l in self.incidents_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def reconstruct_index(self) -> dict[str, Any]:
        keys: dict[str, Any] = {}
        mids: dict[str, Any] = {}
        for row in self.all_events():
            k = row.get("stable_key")
            if k:
                # First-seen wins for inflated legacy duplicates (same market, many keys)
                if k not in keys:
                    keys[k] = {
                        "body_hash": row.get("body_hash"),
                        "event_id": row.get("event_id"),
                        "ingested_utc": row.get("ingested_utc"),
                    }
            mid = self.market_identity_key(row)
            if mid and not self._is_incomplete_m5(row):
                # Prefer closed bars; overwrite forming placeholders
                mids[mid] = {
                    "body_hash": self.canonical_market_hash(row) or row.get("body_hash"),
                    "event_id": row.get("event_id"),
                    "stable_key": row.get("stable_key"),
                    "ingested_utc": row.get("ingested_utc"),
                }
        idx = {
            "keys": keys,
            "market_ids": mids,
            "n": len(keys),
            "n_market_ids": len(mids),
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "reconstructed_utc": _utc(),
        }
        self._write_json_atomic(self.index_path, idx)
        return idx

    def integrity_report(self) -> dict[str, Any]:
        events = self.all_events()
        idx = self._load_index()
        mids = idx.get("market_ids") or {}
        out = {
            "n_events": len(events),
            "n_quarantine": len(self.quarantine_rows()),
            "n_incidents": len(self.incidents()),
            "n_index_keys": int(idx.get("n") or 0),
            "n_market_ids": int(idx.get("n_market_ids") or len(mids)),
            "index_matches": int(idx.get("n") or 0) == len({e.get("stable_key") for e in events}),
            "n_raw": len(list(self.raw_dir.glob("*"))),
            "append_only": True,
            "overwrite": False,
            "store_label": self.store_label,
            "allow_synthetic": self.allow_synthetic,
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out
