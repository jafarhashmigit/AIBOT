"""Append-only Exness demo execution store with recovery & dedup."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase62.constants import STORE_ROOT, canonical_json_sha256


class ExecutionStore:
    """Raw + normalized append-only store. Idempotent ingest. No overwrite of genuine history."""

    def __init__(self, root: Path | None = None):
        self.root = root or STORE_ROOT
        self.raw_dir = self.root / "raw"
        self.norm_path = self.root / "normalized.jsonl"
        self.index_path = self.root / "dedup_index.json"
        self.quarantine_path = self.root / "quarantine.jsonl"
        self.meta_path = self.root / "store_meta.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.is_file():
            self._write_json_atomic(self.index_path, {"keys": {}, "n": 0})
        if not self.meta_path.is_file():
            self._write_json_atomic(
                self.meta_path,
                {"created_utc": _utc(), "n_normalized": 0, "n_quarantine": 0, "n_raw_files": 0},
            )

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

    def _load_index(self) -> dict[str, Any]:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def stable_key(self, record: dict[str, Any]) -> str | None:
        deal = record.get("deal_id")
        order = record.get("order_id")
        kind = record.get("record_kind")
        if deal:
            return f"deal:{deal}"
        if order and kind == "ORDER":
            return f"order:{order}"
        if order and kind == "DEAL" and record.get("actual_fill_price") is not None:
            # deal without deal_id — weak key
            ts = record.get("fill_timestamp_utc")
            return f"weak:{order}:{ts}:{record.get('actual_fill_price')}:{record.get('volume')}"
        return None

    def save_raw(self, *, source_name: str, content: bytes | str, provenance: str) -> dict[str, Any]:
        import hashlib

        content_b = content.encode("utf-8") if isinstance(content, str) else content
        h = hashlib.sha256(content_b).hexdigest()
        dest = self.raw_dir / f"{h[:16]}_{Path(source_name).name}"
        if not dest.is_file():
            dest.write_bytes(content_b)
        meta = {
            "source_name": source_name,
            "path": str(dest),
            "sha256": h,
            "provenance": provenance,
            "saved_utc": _utc(),
            "synthetic": False,
        }
        sm = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sm["n_raw_files"] = len(list(self.raw_dir.glob("*")))
        sm["updated_utc"] = _utc()
        self._write_json_atomic(self.meta_path, sm)
        return meta

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

    def ingest_normalized(self, record: dict[str, Any], *, allow_synthetic: bool = False) -> dict[str, Any]:
        if record.get("synthetic") and not allow_synthetic:
            self.quarantine(record, "synthetic_forbidden_in_genuine_store")
            return {"status": "QUARANTINED", "reason": "synthetic_forbidden_in_genuine_store"}
        if record.get("environment") not in ("DEMO", None) and record.get("broker") == "Exness":
            # Live blocked
            if record.get("environment") == "LIVE":
                self.quarantine(record, "live_environment_forbidden")
                return {"status": "QUARANTINED", "reason": "live_environment_forbidden"}

        key = self.stable_key(record)
        if key is None:
            self.quarantine(record, "missing_stable_identity")
            return {"status": "QUARANTINED", "reason": "missing_stable_identity"}

        idx = self._load_index()
        keys = idx.setdefault("keys", {})
        body_hash = canonical_json_sha256({k: v for k, v in record.items() if k != "collection_timestamp_utc"})
        if key in keys:
            prev = keys[key]
            if prev.get("body_hash") == body_hash:
                return {"status": "DUPLICATE_SUPPRESSED", "key": key}
            self.quarantine({**record, "prior": prev}, "conflicting_deal_or_order_id")
            return {"status": "QUARANTINED", "reason": "conflicting_deal_or_order_id", "key": key}

        # Append normalized
        row = {**record, "stable_key": key, "body_hash": body_hash, "collection_timestamp_utc": _utc()}
        with self.norm_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

        keys[key] = {"body_hash": body_hash, "ingested_utc": _utc()}
        idx["n"] = len(keys)
        self._write_json_atomic(self.index_path, idx)
        sm = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sm["n_normalized"] = int(sm.get("n_normalized") or 0) + 1
        sm["updated_utc"] = _utc()
        self._write_json_atomic(self.meta_path, sm)
        return {"status": "INGESTED", "key": key, "body_hash": body_hash}

    def all_normalized(self) -> list[dict[str, Any]]:
        if not self.norm_path.is_file():
            return []
        rows = []
        for line in self.norm_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def quarantine_rows(self) -> list[dict[str, Any]]:
        if not self.quarantine_path.is_file():
            return []
        return [json.loads(l) for l in self.quarantine_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def reconstruct_index_from_normalized(self) -> dict[str, Any]:
        """Deterministic reconstruction after interrupted index write."""
        keys: dict[str, Any] = {}
        for row in self.all_normalized():
            k = row.get("stable_key") or self.stable_key(row)
            if not k:
                continue
            keys[k] = {"body_hash": row.get("body_hash"), "ingested_utc": row.get("collection_timestamp_utc")}
        idx = {"keys": keys, "n": len(keys), "reconstructed_utc": _utc()}
        self._write_json_atomic(self.index_path, idx)
        return idx

    def integrity_report(self) -> dict[str, Any]:
        rows = self.all_normalized()
        q = self.quarantine_rows()
        idx = self._load_index()
        out = {
            "n_normalized": len(rows),
            "n_quarantine": len(q),
            "n_index_keys": int(idx.get("n") or 0),
            "index_matches_normalized": int(idx.get("n") or 0) == len({r.get("stable_key") for r in rows}),
            "raw_files": len(list(self.raw_dir.glob("*"))),
            "norm_path": str(self.norm_path),
            "append_only": True,
            "overwrite_genuine_history": False,
            "store_root": str(self.root),
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recovery_audit(store: ExecutionStore) -> dict[str, Any]:
    """Exercise recovery boundaries with synthetic temp store — labeled."""
    import tempfile
    from pathlib import Path as P

    results = []
    with tempfile.TemporaryDirectory() as td:
        s = ExecutionStore(root=P(td) / "store")
        # 1) normal ingest
        r1 = s.ingest_normalized(
            {
                "broker": "Exness",
                "environment": "DEMO",
                "deal_id": "D1",
                "order_id": "O1",
                "record_kind": "DEAL",
                "side": "BUY",
                "volume": 0.01,
                "actual_fill_price": 2000.1,
                "fill_timestamp_utc": "2026-01-01 12:00:00",
                "commission": None,
                "source_provenance": "recovery_test",
                "synthetic": False,
            }
        )
        results.append({"step": "ingest", "status": r1["status"]})
        # 2) duplicate
        r2 = s.ingest_normalized(
            {
                "broker": "Exness",
                "environment": "DEMO",
                "deal_id": "D1",
                "order_id": "O1",
                "record_kind": "DEAL",
                "side": "BUY",
                "volume": 0.01,
                "actual_fill_price": 2000.1,
                "fill_timestamp_utc": "2026-01-01 12:00:00",
                "commission": None,
                "source_provenance": "recovery_test",
                "synthetic": False,
            }
        )
        results.append({"step": "duplicate", "status": r2["status"]})
        # 3) conflict
        r3 = s.ingest_normalized(
            {
                "broker": "Exness",
                "environment": "DEMO",
                "deal_id": "D1",
                "order_id": "O1",
                "record_kind": "DEAL",
                "side": "BUY",
                "volume": 0.02,
                "actual_fill_price": 2000.5,
                "fill_timestamp_utc": "2026-01-01 12:00:00",
                "commission": None,
                "source_provenance": "recovery_test",
                "synthetic": False,
            }
        )
        results.append({"step": "conflict", "status": r3["status"]})
        # 4) reconstruct index after wipe
        s.index_path.write_text("{}", encoding="utf-8")
        rebuilt = s.reconstruct_index_from_normalized()
        results.append({"step": "reconstruct", "n": rebuilt.get("n")})
        # 5) synthetic quarantine
        r5 = s.ingest_normalized(
            {
                "broker": "Exness",
                "environment": "DEMO",
                "deal_id": "SYN1",
                "record_kind": "DEAL",
                "synthetic": True,
                "source_provenance": "fixture",
            },
            allow_synthetic=False,
        )
        results.append({"step": "synthetic_block", "status": r5["status"]})

    out = {
        "recovery_steps": results,
        "pass": all(
            [
                results[0]["status"] == "INGESTED",
                results[1]["status"] == "DUPLICATE_SUPPRESSED",
                results[2]["status"] == "QUARANTINED",
                results[3]["n"] == 1,
                results[4]["status"] == "QUARANTINED",
            ]
        ),
        "label": "SYNTHETIC_TEMP_STORE_NOT_GENUINE_EVIDENCE",
        "production_store_integrity": store.integrity_report(),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
