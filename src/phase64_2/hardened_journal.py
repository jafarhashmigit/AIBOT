"""ExecutionIntentJournal subclass — allows Phase64.2 terminal statuses without modifying Phase64."""

from __future__ import annotations

from typing import Any

from phase64.constants import INTENT_STATUSES, JOURNAL_SCHEMA_VERSION, JOURNAL_STAGES, canonical_json, sha256_hex
from phase64.execution_intent import CrashInjected, ExecutionIntentJournal
from phase64_2.constants import STATUS_PAPER_FINALIZED, STATUS_REPAIR_NEEDED, STATUS_WAIT_FINALIZED
from phase64_2.progress import write_json

EXTENDED_STATUSES = frozenset(INTENT_STATUSES) | {
    STATUS_PAPER_FINALIZED,
    STATUS_WAIT_FINALIZED,
    STATUS_REPAIR_NEEDED,
}


class HardenedIntentJournal(ExecutionIntentJournal):
    """Same WAL/append semantics; extended terminal statuses for paper/WAIT finalization."""

    def _apply(self, rec: dict[str, Any]) -> None:
        """Do not let intent_status=None wipe a previously committed status (Phase64 root cause)."""
        self._records.append(rec)
        self._seq = max(self._seq, int(rec.get("seq") or 0))
        intent_id = rec.get("intent_id")
        if intent_id:
            cur = dict(self._intents.get(intent_id) or {})
            prev_status = cur.get("intent_status")
            cur.update({k: v for k, v in rec.items() if k not in ("checksum", "intent_status")})
            if rec.get("intent_status"):
                cur["intent_status"] = rec["intent_status"]
            elif prev_status is not None:
                cur["intent_status"] = prev_status
            self._intents[intent_id] = cur

    def commit(
        self,
        *,
        stage: str,
        decision_id: str,
        intent_id: str | None,
        intent_status: str | None = None,
        payload: dict[str, Any] | None = None,
        crash_gate: str | None = None,
    ) -> dict[str, Any]:
        if stage not in JOURNAL_STAGES:
            raise ValueError(f"bad_stage:{stage}")
        if intent_status is not None and intent_status not in EXTENDED_STATUSES:
            raise ValueError(f"bad_intent_status:{intent_status}")
        if crash_gate and self.crash_at == crash_gate:
            raise CrashInjected(crash_gate)

        import uuid
        from datetime import datetime, timezone

        def _utc() -> str:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._seq += 1
        rec: dict[str, Any] = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "record_id": uuid.uuid4().hex,
            "seq": self._seq,
            "stage": stage,
            "decision_id": decision_id,
            "intent_id": intent_id,
            "intent_status": intent_status,
            "payload": payload or {},
            "broker_order_send": False,
            "automated_orders": "DISABLED",
            "phase64_2_hardened": True,
            "created_utc": _utc(),
        }
        body = {k: v for k, v in rec.items() if k != "checksum"}
        rec["checksum"] = sha256_hex(canonical_json(body))

        wal = self.wal_dir / f"{rec['record_id']}.json"
        write_json(wal, rec)
        if self.crash_at == "after_intent_persistence" and stage == "INTENT_PERSISTED":
            raise CrashInjected("after_intent_persistence")

        self._append_line(rec)
        self._apply(rec)
        wal.unlink(missing_ok=True)
        self._persist_index()
        return rec

    @staticmethod
    def validate_record(rec: dict[str, Any]) -> tuple[bool, str]:
        # Allow extended statuses on reload
        if not isinstance(rec, dict):
            return False, "not_object"
        if rec.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            return False, "bad_schema"
        if rec.get("stage") not in JOURNAL_STAGES:
            return False, "bad_stage"
        if not rec.get("record_id") or not rec.get("decision_id"):
            return False, "missing_ids"
        st = rec.get("intent_status")
        if st is not None and st not in EXTENDED_STATUSES:
            return False, "bad_intent_status"
        body = {k: v for k, v in rec.items() if k != "checksum"}
        if rec.get("checksum") != sha256_hex(canonical_json(body)):
            return False, "bad_checksum"
        return True, "ok"
