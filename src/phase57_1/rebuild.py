"""Deterministic reconstruction of derived experience stores from the journal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase54.constants import HORIZON_BARS
from phase57_1.journal import TradeLifecycleJournal
from phase57_1.outcome import experience_from_exit


def rebuild_experience_from_journal(
    journal: TradeLifecycleJournal,
    *,
    shadow: ExperienceStore,
    hist: ExperienceStore | None = None,
    source: str = "AGENT_SHADOW",
    interrupt_after: int | None = None,
) -> dict[str, Any]:
    """
    Rebuild derived store from EXIT_COMMITTED (+ OUTCOME_DERIVED) evidence.

    Idempotent: deterministic experience_id; duplicates skipped.
    Does not fabricate missing exits. Quarantined journal lines already excluded on load.
    """
    store = shadow if source == "AGENT_SHADOW" else hist
    if store is None:
        raise ValueError("store_required")

    before_ids = {r.get("experience_id") for r in store.all()}
    written = []
    skipped = []
    n = 0

    # Index latest EXIT_COMMITTED and OUTCOME_DERIVED per txn
    exits: dict[str, dict] = {}
    outcomes: dict[str, dict] = {}
    for r in journal.all():
        if r.get("experience_source") and r.get("experience_source") != source:
            continue
        tid = r["txn_id"]
        if r.get("stage") == "EXIT_COMMITTED":
            exits[tid] = r
        elif r.get("stage") == "OUTCOME_DERIVED":
            outcomes[tid] = r

    for tid, exit_rec in exits.items():
        if interrupt_after is not None and n >= interrupt_after:
            return {
                "ok": True,
                "interrupted": True,
                "written": written,
                "skipped": skipped,
                "n_written": len(written),
            }
        payload = exit_rec.get("payload") or {}
        oc_rec = outcomes.get(tid)
        outcome = (oc_rec or {}).get("payload") if oc_rec else None
        if not outcome or not outcome.get("ok", True):
            # Derive from exit payload without inventing prices
            from phase57_1.outcome import derive_outcome

            outcome = derive_outcome(payload)
            if not outcome.get("ok"):
                skipped.append({"txn_id": tid, "reason": "incomplete_outcome", "detail": outcome})
                continue
        rec = experience_from_exit(
            txn_id=tid,
            exit_payload=payload,
            outcome=outcome,
            source=source,
            horizon_bars=HORIZON_BARS,
        )
        existing = {r.get("experience_id") for r in store.all()}
        if rec["experience_id"] in existing:
            skipped.append({"txn_id": tid, "reason": "already_present", "experience_id": rec["experience_id"]})
        else:
            store.append(rec)
            written.append(rec["experience_id"])
            # Mark EXPERIENCE_COMMITTED if missing
            if tid not in journal.experience_committed_txn_ids(source):
                journal.commit(
                    stage="EXPERIENCE_COMMITTED",
                    txn_id=tid,
                    position_id=str(payload.get("position_id") or exit_rec.get("position_id")),
                    experience_source=source,
                    payload={"experience_id": rec["experience_id"], "rebuilt": True},
                )
        n += 1
        store.flush()

    after_ids = {r.get("experience_id") for r in store.all()}
    return {
        "ok": True,
        "interrupted": False,
        "written": written,
        "skipped": skipped,
        "n_written": len(written),
        "before_n": len(before_ids),
        "after_n": len(after_ids),
        "new_ids": sorted(after_ids - before_ids),
    }


def wipe_store(store: ExperienceStore) -> None:
    store.clear()


def corrupt_store_json(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json\ntruncatedtruncated\n", encoding="utf-8")


def truncate_store(path: Path, keep_bytes: int = 20) -> None:
    if path.is_file():
        data = path.read_bytes()[:keep_bytes]
        path.write_bytes(data)
