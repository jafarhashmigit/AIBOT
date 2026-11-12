"""Hardened execution-intent state machine — durable, idempotent, no blind retry."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_9.constants import (
    BROKER_ACCEPTED,
    BROKER_REJECTED,
    INTENT_CREATED,
    INTENT_FSM_VERSION,
    INTENT_STATES,
    PREFLIGHT_REJECTED_STATE,
    RECONCILED,
    RECONCILIATION_PENDING,
    SUBMISSION_PENDING,
    SUBMISSION_UNKNOWN,
    canonical_json_sha256,
    sha256_hex,
)

ALLOWED: dict[str, frozenset[str]] = {
    INTENT_CREATED: frozenset({PREFLIGHT_REJECTED_STATE, SUBMISSION_PENDING}),
    PREFLIGHT_REJECTED_STATE: frozenset(),  # terminal for this intent
    SUBMISSION_PENDING: frozenset({BROKER_ACCEPTED, BROKER_REJECTED, SUBMISSION_UNKNOWN}),
    SUBMISSION_UNKNOWN: frozenset({RECONCILIATION_PENDING}),
    RECONCILIATION_PENDING: frozenset({BROKER_ACCEPTED, BROKER_REJECTED, RECONCILED, RECONCILIATION_PENDING}),
    BROKER_ACCEPTED: frozenset({RECONCILIATION_PENDING, RECONCILED}),
    BROKER_REJECTED: frozenset(),
    RECONCILED: frozenset(),
}


class IntentStateError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecutionIntentStore:
    """Durable intent store: one canonical decision → at most one intent."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "intents.jsonl"
        self.index_path = root / "intent_index.json"
        self.wal_dir = root / "wal"
        self.root.mkdir(parents=True, exist_ok=True)
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        self._by_decision: dict[str, str] = {}
        self._by_intent: dict[str, dict[str, Any]] = {}
        self._load()

    def _write_json_atomic(self, path: Path, obj: Any) -> None:
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

    def _load(self) -> None:
        self._by_decision = {}
        self._by_intent = {}
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._apply(rec)
        for wal in sorted(self.wal_dir.glob("*.json")):
            try:
                rec = json.loads(wal.read_text(encoding="utf-8"))
            except Exception:
                wal.unlink(missing_ok=True)
                continue
            if rec.get("intent_id") not in self._by_intent or rec.get("seq", 0) >= self._by_intent.get(
                rec.get("intent_id"), {}
            ).get("seq", -1):
                if not any(
                    True
                    for line in (self.path.read_text(encoding="utf-8").splitlines() if self.path.is_file() else [])
                    if line.strip() and json.loads(line).get("record_id") == rec.get("record_id")
                ):
                    self._append(rec)
                    self._apply(rec)
            wal.unlink(missing_ok=True)
        self._persist_index()

    def _apply(self, rec: dict[str, Any]) -> None:
        iid = rec.get("intent_id")
        did = rec.get("decision_id")
        if not iid or not did:
            return
        cur = dict(self._by_intent.get(iid) or {})
        cur.update(rec)
        self._by_intent[iid] = cur
        self._by_decision[did] = iid

    def _append(self, rec: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _persist_index(self) -> None:
        self._write_json_atomic(
            self.index_path,
            {
                "by_decision": self._by_decision,
                "n_intents": len(self._by_intent),
                "version": INTENT_FSM_VERSION,
            },
        )

    def create_intent(
        self,
        *,
        decision_id: str,
        direction: str,
        volume: float,
        symbol: str,
        crash_after_wal: bool = False,
    ) -> dict[str, Any]:
        if decision_id in self._by_decision:
            existing = self._by_intent[self._by_decision[decision_id]]
            return {
                "status": "DUPLICATE_REJECTED",
                "intent_id": existing.get("intent_id"),
                "state": existing.get("state"),
                "reason": "canonical_decision_already_has_intent",
            }
        intent_id = sha256_hex(f"{INTENT_FSM_VERSION}:intent:{decision_id}")
        rec = {
            "record_id": uuid.uuid4().hex,
            "seq": 0,
            "intent_id": intent_id,
            "decision_id": decision_id,
            "direction": direction,
            "volume": volume,
            "symbol": symbol,
            "state": INTENT_CREATED,
            "created_utc": _utc(),
            "version": INTENT_FSM_VERSION,
            "submission_attempted": False,
            "broker_order_id": None,
            "broker_deal_ids": [],
        }
        wal = self.wal_dir / f"{rec['record_id']}.json"
        wal.write_text(json.dumps(rec, sort_keys=True), encoding="utf-8")
        if crash_after_wal:
            raise RuntimeError("CrashInjected:after_intent_wal")
        self._append(rec)
        self._apply(rec)
        wal.unlink(missing_ok=True)
        self._persist_index()
        return {"status": "CREATED", "intent_id": intent_id, "state": INTENT_CREATED, "record": rec}

    def transition(
        self,
        intent_id: str,
        new_state: str,
        *,
        extra: dict[str, Any] | None = None,
        crash_after_wal: bool = False,
    ) -> dict[str, Any]:
        if intent_id not in self._by_intent:
            raise IntentStateError(f"unknown_intent:{intent_id}")
        cur = self._by_intent[intent_id]
        old = cur["state"]
        if new_state not in INTENT_STATES:
            raise IntentStateError(f"bad_state:{new_state}")
        if new_state not in ALLOWED.get(old, frozenset()):
            raise IntentStateError(f"illegal_transition:{old}->{new_state}")
        # Critical: no transition into SUBMISSION_PENDING from UNKNOWN via retry shortcut
        rec = {
            "record_id": uuid.uuid4().hex,
            "seq": int(cur.get("seq") or 0) + 1,
            "intent_id": intent_id,
            "decision_id": cur["decision_id"],
            "state": new_state,
            "prior_state": old,
            "transitioned_utc": _utc(),
            "version": INTENT_FSM_VERSION,
            **(extra or {}),
        }
        wal = self.wal_dir / f"{rec['record_id']}.json"
        wal.write_text(json.dumps(rec, sort_keys=True, default=str), encoding="utf-8")
        if crash_after_wal:
            raise RuntimeError("CrashInjected:after_transition_wal")
        self._append(rec)
        self._apply(rec)
        wal.unlink(missing_ok=True)
        self._persist_index()
        return {"status": "TRANSITIONED", "intent_id": intent_id, "state": new_state, "prior": old}

    def get(self, intent_id: str) -> dict[str, Any] | None:
        return self._by_intent.get(intent_id)

    def get_by_decision(self, decision_id: str) -> dict[str, Any] | None:
        iid = self._by_decision.get(decision_id)
        return self._by_intent.get(iid) if iid else None

    def may_submit(self, intent_id: str) -> tuple[bool, str]:
        cur = self._by_intent.get(intent_id)
        if not cur:
            return False, "unknown_intent"
        if cur["state"] != INTENT_CREATED:
            return False, f"not_submittable_from:{cur['state']}"
        # Never submit from UNKNOWN/RECON without recon first — those states aren't INTENT_CREATED
        return True, "ok"

    def may_retry_submit(self, intent_id: str) -> tuple[bool, str]:
        """Blind retry is always forbidden after any submission attempt / unknown."""
        cur = self._by_intent.get(intent_id)
        if not cur:
            return False, "unknown_intent"
        if cur["state"] in (SUBMISSION_UNKNOWN, RECONCILIATION_PENDING, SUBMISSION_PENDING):
            return False, "must_reconcile_before_any_retry"
        if cur.get("submission_attempted"):
            return False, "submission_already_attempted"
        return False, "retry_forbidden_until_reconciled"


def intent_fsm_spec() -> dict[str, Any]:
    return {
        "version": INTENT_FSM_VERSION,
        "states": list(INTENT_STATES),
        "allowed_transitions": {k: sorted(v) for k, v in ALLOWED.items()},
        "rules": [
            "One canonical decision → at most one execution intent",
            "Persist intent before submission",
            "Timeout/crash after submit → SUBMISSION_UNKNOWN → RECONCILIATION_PENDING",
            "Never blind retry before broker evidence reconciliation",
        ],
        "sha256": None,
    }
