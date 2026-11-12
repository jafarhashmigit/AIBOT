"""Phase64-owned execution-intent journal — architecture scaffold; never sends broker orders."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64.constants import (
    FIXTURE_PROVENANCE,
    INTENT_DIR,
    INTENT_STATUSES,
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_STAGES,
    canonical_json,
    sha256_hex,
)
from phase64.progress import write_json


class CrashInjected(RuntimeError):
    """Simulate crash at a persistence boundary."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecutionIntentJournal:
    """Append-only intent journal with WAL recovery. No order_send."""

    def __init__(self, root: Path | None = None, *, crash_at: str | None = None):
        self.root = root or INTENT_DIR
        self.path = self.root / "intent_journal.jsonl"
        self.wal_dir = self.root / "wal"
        self.quarantine = self.root / "quarantine"
        self.index_path = self.root / "intent_index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine.mkdir(parents=True, exist_ok=True)
        self.crash_at = crash_at
        self._seq = 0
        self._records: list[dict[str, Any]] = []
        self._intents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        self._records = []
        self._intents = {}
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
                self._apply(rec)
        for wal in sorted(self.wal_dir.glob("*.json")):
            try:
                rec = json.loads(wal.read_text(encoding="utf-8"))
            except Exception:
                wal.unlink(missing_ok=True)
                continue
            ok, why = self.validate_record(rec)
            if not ok:
                self._quarantine_obj(rec, reason=f"wal:{why}")
                wal.unlink(missing_ok=True)
                continue
            if not any(r.get("record_id") == rec.get("record_id") for r in self._records):
                self._append_line(rec)
                self._apply(rec)
            wal.unlink(missing_ok=True)
        self._persist_index()

    def _quarantine_raw(self, raw: str, *, reason: str, idx: int | None = None) -> None:
        name = f"q_{uuid.uuid4().hex}.txt"
        (self.quarantine / name).write_text(f"reason={reason}\nidx={idx}\n{raw}\n", encoding="utf-8")

    def _quarantine_obj(self, obj: dict, *, reason: str) -> None:
        write_json(self.quarantine / f"q_{uuid.uuid4().hex}.json", {"reason": reason, "record": obj})

    @staticmethod
    def validate_record(rec: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(rec, dict):
            return False, "not_object"
        if rec.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            return False, "bad_schema"
        if rec.get("stage") not in JOURNAL_STAGES:
            return False, "bad_stage"
        if not rec.get("record_id") or not rec.get("decision_id"):
            return False, "missing_ids"
        body = {k: v for k, v in rec.items() if k != "checksum"}
        if rec.get("checksum") != sha256_hex(canonical_json(body)):
            return False, "bad_checksum"
        return True, "ok"

    def _apply(self, rec: dict[str, Any]) -> None:
        self._records.append(rec)
        self._seq = max(self._seq, int(rec.get("seq") or 0))
        intent_id = rec.get("intent_id")
        if intent_id:
            cur = dict(self._intents.get(intent_id) or {})
            cur.update({k: v for k, v in rec.items() if k not in ("checksum",)})
            if rec.get("intent_status"):
                cur["intent_status"] = rec["intent_status"]
            self._intents[intent_id] = cur

    def _append_line(self, rec: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _persist_index(self) -> None:
        write_json(
            self.index_path,
            {
                "n_records": len(self._records),
                "n_intents": len(self._intents),
                "intent_ids": sorted(self._intents.keys()),
                "updated_utc": _utc(),
            },
        )

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
        if intent_status is not None and intent_status not in INTENT_STATUSES:
            raise ValueError(f"bad_intent_status:{intent_status}")
        if self.crash_at == "between_decision_and_intent" and stage == "INTENT_PERSISTED":
            raise CrashInjected("between_decision_and_intent")
        if crash_gate and self.crash_at == crash_gate:
            raise CrashInjected(crash_gate)

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
            "created_utc": _utc(),
        }
        body = {k: v for k, v in rec.items() if k != "checksum"}
        rec["checksum"] = sha256_hex(canonical_json(body))

        wal = self.wal_dir / f"{rec['record_id']}.json"
        write_json(wal, rec)
        if self.crash_at == "after_intent_persistence" and stage == "INTENT_PERSISTED":
            # WAL written; crash before journal append → recoverable
            raise CrashInjected("after_intent_persistence")
        if self.crash_at == "during_order_link" and stage == "ORDER_LINKED":
            raise CrashInjected("during_order_link")

        self._append_line(rec)
        self._apply(rec)
        wal.unlink(missing_ok=True)
        self._persist_index()
        return rec

    def get_intent(self, intent_id: str) -> dict[str, Any] | None:
        return self._intents.get(intent_id)

    def intents_for_decision(self, decision_id: str) -> list[dict[str, Any]]:
        return [v for v in self._intents.values() if v.get("decision_id") == decision_id]

    def all_intents(self) -> list[dict[str, Any]]:
        return list(self._intents.values())

    def all_records(self) -> list[dict[str, Any]]:
        return list(self._records)


def create_execution_intent(
    journal: ExecutionIntentJournal,
    *,
    decision: dict[str, Any],
    risk: dict[str, Any],
    account_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a durable execution intent linked to decision_id.
    Never places a broker order. WAIT / risk-reject produce terminal non-trade statuses.
    """
    decision_id = str(decision["decision_id"])
    journal.commit(
        stage="DECISION_RECORDED",
        decision_id=decision_id,
        intent_id=None,
        payload={
            "decision_action": decision.get("action"),
            "proposed_action": decision.get("proposed_action"),
            "timestamp_utc": decision.get("timestamp_utc"),
            "market_state_id": decision.get("market_state_id"),
            "observation_id": decision.get("observation_id"),
            "instrument": decision.get("instrument"),
            "symbol_active_profile": (account_profile or {}).get("symbol"),
        },
    )

    allowed = bool(risk.get("allowed", True))
    final_action = str(risk.get("final_action") or decision.get("action") or "WAIT")
    intent_id = uuid.uuid4().hex

    if not allowed or final_action == "WAIT" or decision.get("action") == "WAIT":
        status = "RISK_REJECTED" if not allowed and final_action == "WAIT" and decision.get("proposed_action") in (
            "BUY",
            "SELL",
        ) else "NO_TRADE_WAIT"
        if not allowed:
            status = "RISK_REJECTED"
        elif final_action == "WAIT":
            status = "NO_TRADE_WAIT"
        rec = journal.commit(
            stage="INTENT_PERSISTED",
            decision_id=decision_id,
            intent_id=intent_id,
            intent_status=status,
            payload={
                "side": final_action,
                "risk_reasons": list(risk.get("reasons") or []),
                "account_profile": account_profile or {},
                "requested_price": None,
                "broker_submission": "DISABLED",
                "provenance": FIXTURE_PROVENANCE if (account_profile or {}).get("fixture") else "PHASE64_INTENT_SCAFFOLD",
            },
        )
        return {"intent_id": intent_id, "decision_id": decision_id, "intent_status": status, "record": rec}

    bid = decision.get("execution_assumptions", {}).get("bid_ref")
    ask = decision.get("execution_assumptions", {}).get("ask_ref")
    # Prefer explicit refs if present on decision risk_estimate/spread context
    requested = None
    if final_action == "BUY":
        requested = ask if ask is not None else None
    elif final_action == "SELL":
        requested = bid if bid is not None else None

    rec = journal.commit(
        stage="INTENT_PERSISTED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="PENDING",
        payload={
            "side": final_action,
            "risk_reasons": list(risk.get("reasons") or []),
            "account_profile": account_profile or {},
            "requested_price": requested,
            "bid_at_decision": bid,
            "ask_at_decision": ask,
            "broker_submission": "DISABLED",
            "provenance": FIXTURE_PROVENANCE if (account_profile or {}).get("fixture") else "PHASE64_INTENT_SCAFFOLD",
        },
    )
    return {"intent_id": intent_id, "decision_id": decision_id, "intent_status": "PENDING", "record": rec}


def mark_cancelled(journal: ExecutionIntentJournal, *, intent_id: str, decision_id: str) -> dict[str, Any]:
    return journal.commit(
        stage="INTENT_PERSISTED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="CANCELLED",
        payload={"reason": "cancelled_before_broker_submission"},
    )


def mark_expired(journal: ExecutionIntentJournal, *, intent_id: str, decision_id: str) -> dict[str, Any]:
    return journal.commit(
        stage="INTENT_PERSISTED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="EXPIRED",
        payload={"reason": "intent_expired_unfilled"},
    )


def mark_broker_rejected(journal: ExecutionIntentJournal, *, intent_id: str, decision_id: str, reason: str) -> dict[str, Any]:
    return journal.commit(
        stage="ORDER_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="BROKER_REJECTED",
        payload={"rejection_reason": reason, "genuine_broker": False},
        crash_gate="during_order_link",
    )


def mark_missing_execution(journal: ExecutionIntentJournal, *, intent_id: str, decision_id: str) -> dict[str, Any]:
    return journal.commit(
        stage="FILL_RECORDED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="MISSING_EXECUTION",
        payload={"note": "No broker execution record after intent; remains UNKNOWN outcome"},
    )
