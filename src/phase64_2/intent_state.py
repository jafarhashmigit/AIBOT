"""Intent terminal-state consistency — repair incomplete PENDING after durable close."""

from __future__ import annotations

from typing import Any

from phase64_2.constants import (
    OPEN_OK_PENDING,
    STATUS_PAPER_FINALIZED,
    STATUS_REPAIR_NEEDED,
    STATUS_WAIT_FINALIZED,
    canonical_json_sha256,
)
from phase64_2.hardened_journal import HardenedIntentJournal


class CrashInjected(RuntimeError):
    pass


def stages_for_intent(journal: HardenedIntentJournal, intent_id: str) -> set[str]:
    return {r.get("stage") for r in journal.all_records() if r.get("intent_id") == intent_id}


def finalize_paper_intent(
    journal: HardenedIntentJournal,
    *,
    decision_id: str,
    intent_id: str,
    position_id: str | None,
    txn_id: str | None,
    net_r: float | None,
    exit_reason: str | None,
    experience_id: str | None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """
    PENDING → OUTCOME_RECORDED → EXPERIENCE_LINKED → PAPER_FINALIZED.
    Idempotent if already PAPER_FINALIZED.
    """
    cur = journal.get_intent(intent_id)
    if cur and cur.get("intent_status") == STATUS_PAPER_FINALIZED:
        return {"intent_id": intent_id, "intent_status": STATUS_PAPER_FINALIZED, "reused": True}

    journal.commit(
        stage="OUTCOME_RECORDED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=None,  # keep prior until finalize
        payload={
            "position_id": position_id,
            "txn_id": txn_id,
            "net_r": net_r,
            "exit_reason": exit_reason,
            "broker_order_send": False,
        },
    )
    if crash_at == "after_durable_outcome_before_intent_status":
        raise CrashInjected("after_durable_outcome_before_intent_status")

    journal.commit(
        stage="EXPERIENCE_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=None,
        payload={"experience_id": experience_id, "broker_order_send": False},
    )
    if crash_at == "after_intent_outcome_before_experience_link":
        raise CrashInjected("after_intent_outcome_before_experience_link")

    rec = journal.commit(
        stage="EXPERIENCE_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=STATUS_PAPER_FINALIZED,
        payload={
            "experience_id": experience_id,
            "terminal": True,
            "broker_order_send": False,
            "note": "paper_position_closed_intent_finalized",
        },
        crash_gate="during_intent_status_repair",
    )
    return {"intent_id": intent_id, "intent_status": STATUS_PAPER_FINALIZED, "reused": False, "record": rec}


def finalize_wait_intent(
    journal: HardenedIntentJournal,
    *,
    decision_id: str,
    intent_id: str,
    experience_id: str,
    crash_at: str | None = None,
) -> dict[str, Any]:
    cur = journal.get_intent(intent_id)
    if cur and cur.get("intent_status") == STATUS_WAIT_FINALIZED:
        return {"intent_id": intent_id, "intent_status": STATUS_WAIT_FINALIZED, "reused": True}

    journal.commit(
        stage="OUTCOME_RECORDED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=None,
        payload={"exit_reason": "WAIT", "net_r": 0.0, "broker_order_send": False},
    )
    journal.commit(
        stage="EXPERIENCE_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=None,
        payload={"experience_id": experience_id, "broker_order_send": False},
    )
    if crash_at == "after_wait_experience_before_intent_finalize":
        raise CrashInjected("after_wait_experience_before_intent_finalize")

    rec = journal.commit(
        stage="EXPERIENCE_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=STATUS_WAIT_FINALIZED,
        payload={"experience_id": experience_id, "terminal": True, "broker_order_send": False},
    )
    return {"intent_id": intent_id, "intent_status": STATUS_WAIT_FINALIZED, "reused": False, "record": rec}


def audit_intent_consistency(
    journal: HardenedIntentJournal,
    *,
    open_position_ids: set[str],
    closed_position_ids: set[str],
) -> dict[str, Any]:
    """Detect illegal PENDING-after-close and other inconsistencies."""
    issues: list[dict[str, Any]] = []
    for intent in journal.all_intents():
        iid = intent.get("intent_id")
        st = intent.get("intent_status")
        stages = stages_for_intent(journal, str(iid))
        pl = intent.get("payload") or {}
        pid = pl.get("position_id")
        # Also scan outcome payloads for position_id
        for r in journal.all_records():
            if r.get("intent_id") == iid and r.get("stage") == "OUTCOME_RECORDED":
                pid = pid or (r.get("payload") or {}).get("position_id")

        if st in OPEN_OK_PENDING and pid and pid in closed_position_ids:
            issues.append(
                {
                    "type": "closed_position_still_pending",
                    "intent_id": iid,
                    "position_id": pid,
                    "intent_status": st,
                }
            )
        if st == STATUS_PAPER_FINALIZED and pid and pid in open_position_ids:
            issues.append(
                {
                    "type": "finalized_but_still_open",
                    "intent_id": iid,
                    "position_id": pid,
                }
            )
        if "EXPERIENCE_LINKED" in stages and "OUTCOME_RECORDED" not in stages:
            issues.append({"type": "experience_linked_without_outcome", "intent_id": iid})
        if "OUTCOME_RECORDED" in stages and st in OPEN_OK_PENDING:
            issues.append(
                {
                    "type": "durable_outcome_missing_intent_status_update",
                    "intent_id": iid,
                    "intent_status": st,
                }
            )
        if st in OPEN_OK_PENDING and not pid and "OUTCOME_RECORDED" not in stages:
            # Legitimate open/pending without position yet, or WAIT not finalized
            pass

    out = {
        "n_intents": len(journal.all_intents()),
        "n_issues": len(issues),
        "issues": issues,
        "consistent": len(issues) == 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def repair_incomplete_intents(
    journal: HardenedIntentJournal,
    *,
    closed_position_ids: set[str],
    decision_by_position: dict[str, str],
    intent_by_decision: dict[str, str],
    experience_by_decision: dict[str, str] | None = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Idempotent recovery: PENDING + closed position / OUTCOME without status → PAPER_FINALIZED."""
    if crash_at == "during_intent_status_repair":
        journal.crash_at = "during_intent_status_repair"
    repaired = []
    exp_map = dict(experience_by_decision or {})
    # Infer WAIT experience ids from journal EXPERIENCE_LINKED payloads
    for r in journal.all_records():
        if r.get("stage") == "EXPERIENCE_LINKED":
            did = r.get("decision_id")
            eid = (r.get("payload") or {}).get("experience_id")
            if did and eid:
                exp_map.setdefault(str(did), str(eid))

    for intent in list(journal.all_intents()):
        iid = str(intent.get("intent_id"))
        did = str(intent.get("decision_id"))
        st = intent.get("intent_status")
        stages = stages_for_intent(journal, iid)
        pid = None
        net_r = None
        exit_reason = None
        txn_id = None
        for r in journal.all_records():
            if r.get("intent_id") != iid:
                continue
            pl = r.get("payload") or {}
            if r.get("stage") == "OUTCOME_RECORDED":
                pid = pl.get("position_id") or pid
                net_r = pl.get("net_r") if pl.get("net_r") is not None else net_r
                exit_reason = pl.get("exit_reason") or exit_reason
                txn_id = pl.get("txn_id") or txn_id
        if pid is None:
            for p, d in decision_by_position.items():
                if d == did and p in closed_position_ids:
                    pid = p
                    break

        # WAIT repair: non-final WAIT/NO_TRADE with outcome WAIT or known experience
        if st not in (STATUS_WAIT_FINALIZED, STATUS_PAPER_FINALIZED, STATUS_REPAIR_NEEDED):
            if exit_reason == "WAIT" or (
                st in ("NO_TRADE_WAIT", "RISK_REJECTED") and did in exp_map
            ):
                try:
                    finalize_wait_intent(
                        journal,
                        decision_id=did,
                        intent_id=iid,
                        experience_id=exp_map.get(did) or f"recovered_wait:{did}",
                        crash_at=None,
                    )
                    repaired.append({"intent_id": iid, "to": STATUS_WAIT_FINALIZED})
                except CrashInjected:
                    raise
                continue

        needs_paper = (st in OPEN_OK_PENDING or st is None) and (
            (pid and pid in closed_position_ids)
            or ("OUTCOME_RECORDED" in stages and exit_reason not in (None, "WAIT"))
        )
        if needs_paper and st != STATUS_PAPER_FINALIZED:
            try:
                finalize_paper_intent(
                    journal,
                    decision_id=did,
                    intent_id=iid,
                    position_id=pid,
                    txn_id=txn_id,
                    net_r=net_r,
                    exit_reason=exit_reason or "RECOVERED_CLOSE",
                    experience_id=exp_map.get(did),
                    crash_at=crash_at if crash_at == "during_intent_status_repair" else None,
                )
                repaired.append({"intent_id": iid, "to": STATUS_PAPER_FINALIZED})
            except CrashInjected:
                raise

        # EXPERIENCE without OUTCOME → mark repair needed (do not fabricate outcome)
        if (
            "EXPERIENCE_LINKED" in stages
            and "OUTCOME_RECORDED" not in stages
            and st != STATUS_REPAIR_NEEDED
        ):
            journal.commit(
                stage="EXPERIENCE_LINKED",
                decision_id=did,
                intent_id=iid,
                intent_status=STATUS_REPAIR_NEEDED,
                payload={"error": "experience_linked_without_outcome", "broker_order_send": False},
            )
            repaired.append({"intent_id": iid, "to": STATUS_REPAIR_NEEDED})

    return {"repaired": repaired, "n_repaired": len(repaired)}
