"""Append-only trade lifecycle journal — canonical outcome source of truth."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from phase54.timeutil import now_utc_iso
from phase57_1.constants import (
    JOURNAL_DIR,
    JOURNAL_SCHEMA_VERSION,
    QUARANTINE_DIR,
    STAGES,
    WAL_DIR,
    canonical_json,
    sha256_hex,
)
from phase57_1.progress import atomic_write_text, write_json


class JournalError(ValueError):
    pass


class CrashInjected(RuntimeError):
    """Raised / used to simulate crash at persistence boundary."""


class TradeLifecycleJournal:
    def __init__(self, root: Path | None = None, *, crash_at: str | None = None):
        self.root = root or JOURNAL_DIR
        self.path = self.root / "lifecycle_journal.jsonl"
        self.wal_dir = self.root / "wal"
        self.quarantine = self.root / "quarantine"
        self.root.mkdir(parents=True, exist_ok=True)
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine.mkdir(parents=True, exist_ok=True)
        self.crash_at = crash_at
        self._seq = 0
        self._records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        self._records = []
        if self.path.is_file():
            for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    self._quarantine_raw(line, reason="json_decode_error", idx=i)
                    continue
                ok, why = self.validate_record(rec)
                if not ok:
                    self._quarantine_obj(rec, reason=why)
                    continue
                self._records.append(rec)
                self._seq = max(self._seq, int(rec.get("seq") or 0))
        # Replay durable WAL leftovers
        for wal in sorted(self.wal_dir.glob("*.json")):
            try:
                rec = json.loads(wal.read_text(encoding="utf-8"))
            except Exception:
                self._quarantine_raw(wal.read_text(encoding="utf-8", errors="replace"), reason="wal_corrupt")
                wal.unlink(missing_ok=True)
                continue
            ok, why = self.validate_record(rec)
            if not ok:
                self._quarantine_obj(rec, reason=f"wal:{why}")
                wal.unlink(missing_ok=True)
                continue
            if not any(r.get("record_id") == rec.get("record_id") for r in self._records):
                self._append_line(rec)
                self._records.append(rec)
                self._seq = max(self._seq, int(rec.get("seq") or 0))
            wal.unlink(missing_ok=True)

    def _quarantine_raw(self, raw: str, *, reason: str, idx: int | None = None) -> None:
        name = f"q_{now_utc_iso().replace(':', '')}_{uuid.uuid4().hex[:8]}.txt"
        atomic_write_text(self.quarantine / name, f"reason={reason}\nidx={idx}\n{raw}\n")

    def _quarantine_obj(self, obj: dict, *, reason: str) -> None:
        name = f"q_{uuid.uuid4().hex}.json"
        write_json(self.quarantine / name, {"reason": reason, "record": obj})

    @staticmethod
    def validate_record(rec: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(rec, dict):
            return False, "not_object"
        if rec.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            return False, "bad_schema"
        if rec.get("stage") not in STAGES:
            return False, "bad_stage"
        if not rec.get("txn_id") or not rec.get("record_id"):
            return False, "missing_ids"
        body = {k: v for k, v in rec.items() if k != "checksum"}
        expect = sha256_hex(canonical_json(body))
        if rec.get("checksum") != expect:
            return False, "checksum_mismatch"
        return True, "ok"

    def _maybe_crash(self, label: str, *, stage: str | None = None) -> None:
        # Restrict generic journal-write crash to EXIT_COMMITTED so POSITION_OPEN is not aborted.
        if self.crash_at == "during_journal_write" and label == "during_journal_write":
            if stage != "EXIT_COMMITTED":
                return
            raise CrashInjected(label)
        if self.crash_at == label:
            raise CrashInjected(label)

    def _append_line(self, rec: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_json(rec) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

    def commit(
        self,
        *,
        stage: str,
        txn_id: str,
        position_id: str,
        payload: dict[str, Any],
        experience_source: str | None = None,
        provenance: str = "phase57_1",
    ) -> dict[str, Any]:
        if stage not in STAGES:
            raise JournalError(f"bad_stage:{stage}")
        self._maybe_crash(f"before_commit:{stage}", stage=stage)
        self._seq += 1
        body = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "record_id": uuid.uuid4().hex,
            "txn_id": txn_id,
            "position_id": position_id,
            "stage": stage,
            "seq": self._seq,
            "experience_source": experience_source,
            "payload": payload,
            "provenance": provenance,
            "created_iso": now_utc_iso(),
        }
        body["checksum"] = sha256_hex(canonical_json(body))

        # WAL first (atomic file)
        self._maybe_crash("during_journal_write", stage=stage)
        wal_path = self.wal_dir / f"{body['record_id']}.json"
        atomic_write_text(wal_path, canonical_json(body) + "\n")
        self._maybe_crash(f"after_wal:{stage}", stage=stage)

        # Append to journal
        self._append_line(body)
        self._records.append(body)
        wal_path.unlink(missing_ok=True)
        self._maybe_crash(f"after_commit:{stage}", stage=stage)
        return body

    def all(self) -> list[dict[str, Any]]:
        return list(self._records)

    def by_txn(self, txn_id: str) -> list[dict[str, Any]]:
        return [r for r in self._records if r.get("txn_id") == txn_id]

    def latest_stage(self, txn_id: str) -> str | None:
        rows = self.by_txn(txn_id)
        if not rows:
            return None
        return rows[-1].get("stage")

    def committed_exits(self) -> list[dict[str, Any]]:
        """EXIT_COMMITTED records — durable closed-trade evidence."""
        return [r for r in self._records if r.get("stage") == "EXIT_COMMITTED"]

    def experience_committed_txn_ids(self, source: str | None = None) -> set[str]:
        out = set()
        for r in self._records:
            if r.get("stage") != "EXPERIENCE_COMMITTED":
                continue
            if source and r.get("experience_source") != source:
                continue
            out.add(r["txn_id"])
        return out

    def pending_experience(self, source: str = "AGENT_SHADOW") -> list[dict[str, Any]]:
        """EXIT_COMMITTED (or OUTCOME_DERIVED) without EXPERIENCE_COMMITTED."""
        done = self.experience_committed_txn_ids(source)
        pending = []
        seen = set()
        for r in self._records:
            if r.get("experience_source") and r.get("experience_source") != source:
                continue
            if r.get("stage") not in ("EXIT_COMMITTED", "OUTCOME_DERIVED"):
                continue
            tid = r["txn_id"]
            if tid in done or tid in seen:
                continue
            # Prefer OUTCOME_DERIVED payload if present
            outcome = None
            exit_rec = None
            for x in self.by_txn(tid):
                if x.get("stage") == "EXIT_COMMITTED":
                    exit_rec = x
                if x.get("stage") == "OUTCOME_DERIVED":
                    outcome = x
            if exit_rec is None:
                continue
            seen.add(tid)
            pending.append({"exit": exit_rec, "outcome": outcome})
        return pending
