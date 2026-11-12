"""Independent reconciliation — report discrepancies; do not silently repair."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase50.experience_store import ExperienceStore
from phase54.state import AgentState
from phase57_1.constants import deterministic_experience_id
from phase57_1.journal import TradeLifecycleJournal
from phase57_1.outcome import derive_outcome


def reconcile(
    *,
    journal: TradeLifecycleJournal,
    state: AgentState,
    shadow: ExperienceStore,
    hist: ExperienceStore,
) -> dict[str, Any]:
    """
    Compare journal vs state vs derived stores.
    Never mutates evidence — report only.
    """
    missing_outcomes = []
    duplicate_outcomes = []
    orphans = []
    invalid_checksums = []  # already quarantined on load; count quarantine files
    unrecoverable = []
    inconsistent = []

    exits = {r["txn_id"]: r for r in journal.committed_exits() if r.get("experience_source") != "HISTORICAL_HYPOTHETICAL"}
    # include all AGENT_SHADOW / None
    exits = {}
    for r in journal.committed_exits():
        src = r.get("experience_source") or "AGENT_SHADOW"
        if src != "AGENT_SHADOW":
            continue
        exits[r["txn_id"]] = r

    exp_done = journal.experience_committed_txn_ids("AGENT_SHADOW")
    shadow_by_id = {r.get("experience_id"): r for r in shadow.all() if r.get("source") == "AGENT_SHADOW"}
    shadow_by_txn = {}
    for r in shadow.all():
        tid = (r.get("decision_context") or {}).get("txn_id")
        if tid:
            shadow_by_txn.setdefault(tid, []).append(r)

    closed_ids = list(state.data.get("closed_position_ids") or [])
    open_ids = list((state.data.get("open_positions") or {}).keys())

    for tid, exit_rec in exits.items():
        payload = exit_rec.get("payload") or {}
        pid = payload.get("position_id") or exit_rec.get("position_id")
        exp_id = deterministic_experience_id(tid, "AGENT_SHADOW")
        outcome = derive_outcome(payload)
        if not outcome.get("ok"):
            unrecoverable.append({"txn_id": tid, "reason": "incomplete_exit_payload", "detail": outcome})
            continue
        if tid not in exp_done and exp_id not in shadow_by_id:
            missing_outcomes.append(
                {
                    "txn_id": tid,
                    "position_id": pid,
                    "exit_reason": payload.get("exit_reason"),
                    "note": "EXIT_COMMITTED without experience",
                }
            )
        rows = shadow_by_txn.get(tid) or []
        if len(rows) > 1:
            duplicate_outcomes.append({"txn_id": tid, "n": len(rows), "ids": [x.get("experience_id") for x in rows]})
        if exp_id in shadow_by_id:
            sh = shadow_by_id[exp_id]
            # Compare key fields
            if abs(float(sh.get("actual_costed_outcome_net_r") or 0) - float(outcome.get("net_r") or 0)) > 1e-9:
                inconsistent.append(
                    {
                        "txn_id": tid,
                        "field": "net_r",
                        "journal": outcome.get("net_r"),
                        "shadow": sh.get("actual_costed_outcome_net_r"),
                    }
                )
            ctx = sh.get("decision_context") or {}
            if ctx.get("exit_reason") and ctx.get("exit_reason") != payload.get("exit_reason"):
                inconsistent.append(
                    {
                        "txn_id": tid,
                        "field": "exit_reason",
                        "journal": payload.get("exit_reason"),
                        "shadow": ctx.get("exit_reason"),
                    }
                )

    # Orphan shadow: experience with txn_id not in journal exits
    for r in shadow.all():
        tid = (r.get("decision_context") or {}).get("txn_id")
        if tid and tid not in exits:
            # May be WAIT experiences without exit — only flag journal-marked paper closes
            if (r.get("decision_context") or {}).get("phase57_1_journal"):
                orphans.append({"type": "shadow_without_exit", "experience_id": r.get("experience_id"), "txn_id": tid})

    # closed_ids without journal exit
    journal_pids = { (r.get("payload") or {}).get("position_id") or r.get("position_id") for r in exits.values() }
    for pid in closed_ids:
        if pid not in journal_pids:
            # Pre-durable engine or crash before EXIT_COMMITTED
            inconsistent.append({"type": "closed_id_without_journal_exit", "position_id": pid})

    # open ∩ closed
    for pid in set(open_ids) & set(closed_ids):
        inconsistent.append({"type": "open_and_closed", "position_id": pid})

    # Hist/shadow separation
    hist_ids = {r.get("experience_id") for r in hist.all()}
    sh_ids = {r.get("experience_id") for r in shadow.all()}
    overlap = hist_ids & sh_ids
    if overlap:
        inconsistent.append({"type": "hist_shadow_id_overlap", "ids": list(overlap)[:5]})

    q_n = len(list(journal.quarantine.glob("*"))) if journal.quarantine.exists() else 0

    # Unexplained = missing committed outcomes (recoverable via rebuild) + unrecoverable + overlap
    unexplained = list(missing_outcomes)  # before rebuild these are discrepancies
    # After successful rebuild, caller should re-run; acceptance wants zero unexplained

    dup_exp_ids = [i for i, n in Counter([r.get("experience_id") for r in shadow.all()]).items() if n > 1]
    for i in dup_exp_ids:
        duplicate_outcomes.append({"experience_id": i, "type": "duplicate_experience_id"})

    report = {
        "missing_outcomes": missing_outcomes,
        "duplicate_outcomes": duplicate_outcomes,
        "orphan_records": orphans,
        "invalid_checksums_quarantined": q_n,
        "unrecoverable_transactions": unrecoverable,
        "inconsistent_lifecycle_states": inconsistent,
        "n_journal_exits": len(exits),
        "n_shadow": shadow.n,
        "n_hist": hist.n,
        "n_closed_ids": len(closed_ids),
        "unexplained_discrepancies": len(unexplained) + len(unrecoverable) + len([x for x in inconsistent if x.get("type") != "closed_id_without_journal_exit"]),
        # closed_id without journal may exist if crash before EXIT_COMMITTED — counted separately
        "ok": len(missing_outcomes) == 0
        and len(duplicate_outcomes) == 0
        and len(unrecoverable) == 0
        and len(orphans) == 0
        and len(overlap) == 0
        and not any(x.get("field") for x in inconsistent),
    }
    return report
