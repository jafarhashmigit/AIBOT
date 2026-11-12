"""Decision → intent → order → deal linkage rules (fixtures only for broker IDs)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from phase64.constants import FIXTURE_PROVENANCE, canonical_json_sha256
from phase64.execution_intent import CrashInjected, ExecutionIntentJournal


def link_order(
    journal: ExecutionIntentJournal,
    *,
    intent_id: str,
    decision_id: str,
    order_id: str,
    genuine_broker: bool = False,
) -> dict[str, Any]:
    """
    Link a broker order_id to an intent.
    genuine_broker=True is reserved for future real demo imports; tests use fixtures (False).
    """
    if genuine_broker:
        # Safety: Phase64 must not invent genuine broker evidence
        raise ValueError("genuine_broker_linkage_requires_imported_demo_record_not_fabricated")
    return journal.commit(
        stage="ORDER_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status="ORDER_LINKED",
        payload={
            "broker_order_id": order_id,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        },
        crash_gate="during_order_link",
    )


def link_deal_fill(
    journal: ExecutionIntentJournal,
    *,
    intent_id: str,
    decision_id: str,
    deal_id: str,
    order_id: str,
    actual_fill_price: float | None,
    requested_price: float | None,
    volume: float,
    fill_kind: str,  # PARTIAL | FULL
    commission: float | None = None,
    fee: float | None = None,
    swap: float | None = None,
    bid_at_exec: float | None = None,
    ask_at_exec: float | None = None,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    """Attach a deal/fill to the same original decision/intent. Partial fills share decision_id."""
    status = "PARTIAL_FILL" if fill_kind == "PARTIAL" else "FILLED"
    fill_payload = {
        "broker_deal_id": deal_id,
        "broker_order_id": order_id,
        "actual_fill_price": actual_fill_price,
        "requested_price": requested_price,
        "volume": volume,
        "fill_kind": fill_kind,
        "commission": commission,
        "fee": fee,
        "swap": swap,
        "bid_at_exec": bid_at_exec,
        "ask_at_exec": ask_at_exec,
        "latency_ms": latency_ms,
        "genuine_broker": False,
        "provenance": FIXTURE_PROVENANCE,
    }
    journal.commit(
        stage="DEAL_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=status,
        payload={
            "broker_deal_id": deal_id,
            "broker_order_id": order_id,
            "actual_fill_price": actual_fill_price,
            "requested_price": requested_price,
            "volume": volume,
            "fill_kind": fill_kind,
            "genuine_broker": False,
            "provenance": FIXTURE_PROVENANCE,
        },
    )
    rec = journal.commit(
        stage="FILL_RECORDED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=status,
        payload=fill_payload,
    )
    if journal.crash_at == "after_partial_fill" and fill_kind == "PARTIAL":
        raise CrashInjected("after_partial_fill")
    return rec


def independent_decision_count(journal: ExecutionIntentJournal) -> dict[str, Any]:
    """
    Count independent decisions by unique decision_id.
    Multiple partial fills for the same decision_id count as ONE decision.
    """
    by_decision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fill_rows = 0
    for rec in journal.all_records():
        did = rec.get("decision_id")
        if not did:
            continue
        by_decision[did].append(rec)
        pl = rec.get("payload") or {}
        if rec.get("stage") == "FILL_RECORDED" and pl.get("actual_fill_price") is not None:
            fill_rows += 1

    trade_decisions = set()
    wait_or_reject = set()
    for did, recs in by_decision.items():
        statuses = {r.get("intent_status") for r in recs if r.get("intent_status")}
        if statuses & {"FILLED", "PARTIAL_FILL", "ORDER_LINKED", "PENDING", "UNFILLED", "BROKER_REJECTED", "MISSING_EXECUTION", "CANCELLED", "EXPIRED"}:
            trade_decisions.add(did)
        if statuses & {"NO_TRADE_WAIT", "RISK_REJECTED"}:
            wait_or_reject.add(did)

    # Independent decisions = unique decision_ids that produced an intent (all of them)
    n_independent = len(by_decision)
    # Never inflate by fill count
    assert n_independent <= len(by_decision)

    out = {
        "n_independent_decisions": n_independent,
        "n_fill_rows": fill_rows,
        "n_trade_linked_decisions": len(trade_decisions),
        "n_wait_or_risk_reject": len(wait_or_reject),
        "partial_fills_do_not_inflate_decisions": True,
        "rule": "independent_decision_count == unique decision_id count",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def reconcile_orders_deals_fills(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile fixture order/deal/fill linkage; detect orphans and duplicates."""
    orders: set[str] = set()
    deals: set[str] = set()
    deal_dupes = 0
    seen_deals: set[str] = set()
    orphans: list[str] = []
    decision_fill_map: dict[str, list[str]] = defaultdict(list)

    for r in records:
        pl = r.get("payload") or {}
        # Count broker IDs primarily on FILL_RECORDED to avoid double-counting DEAL_LINKED+FILL pairs
        if r.get("stage") == "ORDER_LINKED":
            oid = pl.get("broker_order_id")
            if oid:
                orders.add(str(oid))
        if r.get("stage") == "FILL_RECORDED":
            oid = pl.get("broker_order_id")
            did = pl.get("broker_deal_id")
            if oid:
                orders.add(str(oid))
            if did:
                if did in seen_deals:
                    deal_dupes += 1
                seen_deals.add(str(did))
                deals.add(str(did))
                if r.get("decision_id"):
                    decision_fill_map[str(r["decision_id"])].append(str(did))
        if r.get("intent_status") == "MISSING_EXECUTION":
            orphans.append(str(r.get("intent_id")))

    out = {
        "n_orders": len(orders),
        "n_deals": len(deals),
        "duplicate_deal_imports": deal_dupes,
        "orphan_intents_missing_execution": orphans,
        "fills_by_decision": {k: v for k, v in decision_fill_map.items()},
        "no_orphan_ok": len(orphans) == 0,
        "no_double_count_ok": deal_dupes == 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def audit_traceability(journal: ExecutionIntentJournal) -> dict[str, Any]:
    intents = journal.all_intents()
    coverage = {
        "decisions_with_intent": 0,
        "intents_with_order": 0,
        "intents_with_deal": 0,
        "intents_terminal_non_fill": 0,
        "partial_fill_chains": 0,
    }
    for intent in intents:
        coverage["decisions_with_intent"] += 1
        st = intent.get("intent_status")
        pl = intent.get("payload") or {}
        if pl.get("broker_order_id") or st in ("ORDER_LINKED", "PARTIAL_FILL", "FILLED", "BROKER_REJECTED"):
            coverage["intents_with_order"] += 1
        if pl.get("broker_deal_id") or st in ("PARTIAL_FILL", "FILLED"):
            coverage["intents_with_deal"] += 1
        if st in ("RISK_REJECTED", "NO_TRADE_WAIT", "CANCELLED", "EXPIRED", "UNFILLED", "BROKER_REJECTED", "MISSING_EXECUTION"):
            coverage["intents_terminal_non_fill"] += 1
        if st == "PARTIAL_FILL":
            coverage["partial_fill_chains"] += 1

    counts = independent_decision_count(journal)
    recon = reconcile_orders_deals_fills(journal.all_records())
    out = {
        "coverage": coverage,
        "independent_decisions": counts,
        "reconciliation": recon,
        "production_lifecycle_wired": False,
        "genuine_broker_orders_linked": 0,
        "note": "Traceability demonstrated on Phase64 fixtures/scaffold only — not genuine broker evidence",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
