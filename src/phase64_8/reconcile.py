"""
Deterministic reconciliation state machine.

canonical decision → execution intent → broker order → broker deal →
position → close deal → realized outcome

Never match solely by timestamp, price, or volume.
Never fabricate broker deals from paper decisions.
Never mark paper as broker-executed without sufficient identifier evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from phase64_8.constants import (
    RECON_VERSION,
    STATE_CONFLICTING_BROKER_EVIDENCE,
    STATE_DUPLICATE_BROKER_EVIDENCE,
    STATE_MISSING_BROKER_EVIDENCE,
    STATE_OBSERVED,
    STATE_ORPHAN_BROKER_EVIDENCE,
    STATE_RECONCILED,
    STATE_UNKNOWN,
    STATE_UNRESOLVED,
    STORE_BROKER_EVIDENCE,
    STORE_PAPER,
    UNKNOWN,
    canonical_json_sha256,
    sha256_hex,
)


def _rid(*parts: str) -> str:
    return sha256_hex(f"{RECON_VERSION}:" + "|".join(str(p) for p in parts))


def _link_by_identifiers(
    intent: dict[str, Any],
    order: dict[str, Any] | None,
    deal: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer explicit broker + intent identifiers. Refuse time/price/volume-only matches."""
    evidence: list[str] = []
    missing: list[str] = []

    intent_id = intent.get("execution_intent_id") or intent.get("intent_id")
    if not intent_id:
        missing.append("execution_intent_id")

    order_match = False
    if order is not None:
        if intent.get("broker_order_id") and intent.get("broker_order_id") == order.get("broker_order_id"):
            order_match = True
            evidence.append("intent.broker_order_id==order.broker_order_id")
        elif intent.get("client_order_tag") and intent.get("client_order_tag") == order.get("comment"):
            order_match = True
            evidence.append("intent.client_order_tag==order.comment")
        else:
            missing.append("order_identifier_link")

    deal_match = False
    if deal is not None:
        if order is not None and deal.get("broker_order_id") and deal.get("broker_order_id") == order.get(
            "broker_order_id"
        ):
            deal_match = True
            evidence.append("deal.broker_order_id==order.broker_order_id")
        elif intent.get("broker_deal_id") and intent.get("broker_deal_id") == deal.get("broker_deal_id"):
            deal_match = True
            evidence.append("intent.broker_deal_id==deal.broker_deal_id")
        else:
            missing.append("deal_identifier_link")

    # Explicitly reject sole timestamp/price/volume coincidence
    rejected_heuristics = []
    if intent.get("timestamp") and order and intent.get("timestamp") == order.get("observation_timestamp"):
        rejected_heuristics.append("timestamp_alone_insufficient")
    if intent.get("price") and deal and intent.get("price") == deal.get("execution_price"):
        rejected_heuristics.append("price_alone_insufficient")
    if intent.get("volume") and deal and intent.get("volume") == deal.get("volume"):
        rejected_heuristics.append("volume_alone_insufficient")

    sufficient = bool(intent_id) and (
        (order_match and (deal is None or deal_match))
        or (deal_match and order is None and intent.get("broker_deal_id"))
    )
    return {
        "sufficient": sufficient,
        "order_match": order_match,
        "deal_match": deal_match,
        "evidence": evidence,
        "missing": missing,
        "rejected_heuristics": rejected_heuristics,
    }


def reconcile_lifecycle(
    *,
    events: list[dict[str, Any]],
    intents: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intents = intents or []
    decisions = decisions or []

    # Experience separation guard
    for e in events:
        if e.get("store_label") in (STORE_PAPER, "HISTORICAL_HYPOTHETICAL"):
            raise ValueError("broker_reconcile_refuses_non_broker_store_events")

    deals = [e for e in events if e.get("record_kind") == "BROKER_DEAL"]
    balances = [e for e in events if e.get("record_kind") == "BROKER_BALANCE_OPERATION"]
    orders = [e for e in events if e.get("record_kind") == "BROKER_ORDER"]
    positions = [e for e in events if e.get("record_kind") == "BROKER_POSITION"]
    accounts = [e for e in events if e.get("record_kind") == "BROKER_ACCOUNT"]

    findings: list[dict[str, Any]] = []
    lifecycles: list[dict[str, Any]] = []

    # Duplicate detection by stable_key (within event list — journal already dedups ingest)
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_key[str(e.get("stable_key"))].append(e)
    for k, rows in by_key.items():
        if len(rows) > 1:
            hashes = {r.get("body_hash") for r in rows}
            state = STATE_DUPLICATE_BROKER_EVIDENCE if len(hashes) == 1 else STATE_CONFLICTING_BROKER_EVIDENCE
            findings.append(
                {
                    "reconciliation_id": _rid("dup_or_conflict", k),
                    "state": state,
                    "stable_key": k,
                    "n": len(rows),
                    "note": "Never auto-resolve conflict by timestamp proximity",
                }
            )

    deals_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in deals:
        oid = d.get("broker_order_id") or UNKNOWN
        deals_by_order[str(oid)].append(d)

    orders_by_id = {str(o.get("broker_order_id")): o for o in orders if o.get("broker_order_id")}

    # Orders without deals
    for oid, o in orders_by_id.items():
        linked = deals_by_order.get(oid) or []
        if not linked and not o.get("historical"):
            # open order may legitimately have no deal yet → OBSERVED
            findings.append(
                {
                    "reconciliation_id": _rid("order_observed", oid),
                    "state": STATE_OBSERVED,
                    "broker_order_id": oid,
                    "note": "open_or_pending_order_without_deal",
                }
            )
        elif not linked and o.get("historical"):
            findings.append(
                {
                    "reconciliation_id": _rid("order_missing_deal", oid),
                    "state": STATE_MISSING_BROKER_EVIDENCE,
                    "broker_order_id": oid,
                    "missing": ["broker_deal"],
                }
            )

    # Deals without orders
    for d in deals:
        oid = d.get("broker_order_id")
        if not oid:
            findings.append(
                {
                    "reconciliation_id": _rid("deal_orphan_order", d.get("broker_deal_id")),
                    "state": STATE_ORPHAN_BROKER_EVIDENCE,
                    "broker_deal_id": d.get("broker_deal_id"),
                    "missing": ["broker_order_id"],
                }
            )
        elif oid not in orders_by_id and oid != UNKNOWN:
            findings.append(
                {
                    "reconciliation_id": _rid("deal_missing_order", d.get("broker_deal_id")),
                    "state": STATE_MISSING_BROKER_EVIDENCE,
                    "broker_deal_id": d.get("broker_deal_id"),
                    "broker_order_id": oid,
                    "missing": ["broker_order_record"],
                }
            )

    # Partial fills — multiple deals per order (preserve one-to-many)
    for oid, ds in deals_by_order.items():
        if oid == UNKNOWN:
            continue
        if len(ds) > 1:
            findings.append(
                {
                    "reconciliation_id": _rid("partial_fills", oid),
                    "state": STATE_OBSERVED,
                    "broker_order_id": oid,
                    "n_deals": len(ds),
                    "deal_ids": [d.get("broker_deal_id") for d in ds],
                    "relationship": "one_order_to_many_deals",
                }
            )

    # Conflicting price/volume on same deal id
    deals_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in deals:
        if d.get("broker_deal_id"):
            deals_by_id[str(d["broker_deal_id"])].append(d)
    for did, rows in deals_by_id.items():
        if len(rows) < 2:
            continue
        prices = {r.get("execution_price") for r in rows}
        vols = {r.get("volume") for r in rows}
        if len(prices) > 1:
            findings.append(
                {
                    "reconciliation_id": _rid("conflict_price", did),
                    "state": STATE_CONFLICTING_BROKER_EVIDENCE,
                    "broker_deal_id": did,
                    "field": "execution_price",
                    "values": sorted(prices, key=lambda x: str(x)),
                }
            )
        if len(vols) > 1:
            findings.append(
                {
                    "reconciliation_id": _rid("conflict_volume", did),
                    "state": STATE_CONFLICTING_BROKER_EVIDENCE,
                    "broker_deal_id": did,
                    "field": "volume",
                    "values": sorted(vols, key=lambda x: str(x)),
                }
            )

    # Intent linkage
    for intent in intents:
        # Paper cannot become broker-executed without identifiers
        linked_order = None
        if intent.get("broker_order_id"):
            linked_order = orders_by_id.get(str(intent["broker_order_id"]))
        linked_deal = None
        if intent.get("broker_deal_id"):
            for d in deals:
                if str(d.get("broker_deal_id")) == str(intent["broker_deal_id"]):
                    linked_deal = d
                    break
        if linked_order is None and intent.get("broker_order_id"):
            for dlist in deals_by_order.get(str(intent["broker_order_id"]), []):
                linked_deal = linked_deal or dlist

        link = _link_by_identifiers(intent, linked_order, linked_deal)
        if link["sufficient"]:
            state = STATE_RECONCILED
        elif not intent.get("broker_order_id") and not intent.get("broker_deal_id"):
            state = STATE_MISSING_BROKER_EVIDENCE
        else:
            state = STATE_UNRESOLVED

        # Never promote paper to broker-executed on heuristics alone
        paper_marked_broker = bool(intent.get("force_broker_executed_without_ids"))
        if paper_marked_broker and not link["sufficient"]:
            state = STATE_UNRESOLVED
            findings.append(
                {
                    "reconciliation_id": _rid("paper_not_broker", intent.get("execution_intent_id")),
                    "state": STATE_UNRESOLVED,
                    "note": "paper_decision_cannot_be_retroactively_broker_executed",
                }
            )

        lifecycles.append(
            {
                "reconciliation_id": _rid("lifecycle", intent.get("execution_intent_id") or UNKNOWN),
                "state": state,
                "decision_id": intent.get("decision_id"),
                "execution_intent_id": intent.get("execution_intent_id") or intent.get("intent_id"),
                "broker_order_id": (linked_order or {}).get("broker_order_id") or intent.get("broker_order_id"),
                "broker_deal_ids": [
                    d.get("broker_deal_id")
                    for d in deals_by_order.get(str(intent.get("broker_order_id") or ""), [])
                ]
                or ([linked_deal.get("broker_deal_id")] if linked_deal else []),
                "position_id": (linked_deal or {}).get("broker_position_id"),
                "link": link,
                "prior_state": STATE_UNKNOWN,
            }
        )

    # Orphan broker evidence (no matching intent) when intents were supplied
    if intents:
        intent_order_ids = {str(i.get("broker_order_id")) for i in intents if i.get("broker_order_id")}
        intent_deal_ids = {str(i.get("broker_deal_id")) for i in intents if i.get("broker_deal_id")}
        for o in orders:
            oid = str(o.get("broker_order_id"))
            if oid and oid not in intent_order_ids:
                findings.append(
                    {
                        "reconciliation_id": _rid("orphan_order", oid),
                        "state": STATE_ORPHAN_BROKER_EVIDENCE,
                        "broker_order_id": oid,
                        "note": "unexpected_broker_activity_no_matching_intent",
                    }
                )
        for d in deals:
            did = str(d.get("broker_deal_id"))
            oid = str(d.get("broker_order_id") or "")
            if did and did not in intent_deal_ids and oid not in intent_order_ids:
                findings.append(
                    {
                        "reconciliation_id": _rid("orphan_deal", did),
                        "state": STATE_ORPHAN_BROKER_EVIDENCE,
                        "broker_deal_id": did,
                        "note": "unexpected_broker_activity",
                    }
                )

    # Balance ops are observed broker evidence, not trade fills
    for b in balances:
        findings.append(
            {
                "reconciliation_id": _rid("balance", b.get("broker_deal_id")),
                "state": STATE_OBSERVED,
                "record_kind": "BROKER_BALANCE_OPERATION",
                "broker_deal_id": b.get("broker_deal_id"),
                "note": "balance_or_credit_not_a_trade_fill",
            }
        )

    # Empty observations
    empty_flags = {
        "positions_empty": len(positions) == 0,
        "open_orders_empty": len([o for o in orders if not o.get("historical")]) == 0,
        "trade_deals_empty": len(deals) == 0,
        "accounts_observed": len(accounts) > 0,
    }

    # Decision → never fabricate deal
    for dec in decisions:
        if dec.get("fabricate_broker_deal"):
            findings.append(
                {
                    "reconciliation_id": _rid("fabricate_blocked", dec.get("decision_id")),
                    "state": STATE_UNRESOLVED,
                    "note": "broker_deal_must_never_be_fabricated_from_paper_decision",
                    "blocked": True,
                }
            )

    states_seen = sorted({f.get("state") for f in findings} | {lc.get("state") for lc in lifecycles})
    out = {
        "recon_version": RECON_VERSION,
        "store": STORE_BROKER_EVIDENCE,
        "n_events": len(events),
        "n_intents": len(intents),
        "n_decisions": len(decisions),
        "n_findings": len(findings),
        "n_lifecycles": len(lifecycles),
        "findings": findings,
        "lifecycles": lifecycles,
        "empty_flags": empty_flags,
        "states_seen": states_seen,
        "matching_rules": {
            "never_timestamp_alone": True,
            "never_price_alone": True,
            "never_volume_alone": True,
            "prefer_broker_and_intent_ids": True,
            "preserve_partial_fills": True,
            "preserve_multi_deal_per_order": True,
            "preserve_multi_order_lifecycle": True,
        },
        "fill_reconciliation_validated": False,  # requires genuine trade fills
        "pass": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def state_machine_spec() -> dict[str, Any]:
    return {
        "states": [
            STATE_UNKNOWN,
            STATE_OBSERVED,
            STATE_RECONCILED,
            STATE_ORPHAN_BROKER_EVIDENCE,
            STATE_MISSING_BROKER_EVIDENCE,
            STATE_CONFLICTING_BROKER_EVIDENCE,
            STATE_DUPLICATE_BROKER_EVIDENCE,
            STATE_UNRESOLVED,
        ],
        "happy_path": [STATE_UNKNOWN, STATE_OBSERVED, STATE_RECONCILED],
        "exception_states": [
            STATE_ORPHAN_BROKER_EVIDENCE,
            STATE_MISSING_BROKER_EVIDENCE,
            STATE_CONFLICTING_BROKER_EVIDENCE,
            STATE_DUPLICATE_BROKER_EVIDENCE,
            STATE_UNRESOLVED,
        ],
        "rules": [
            "Exception states never convert to successful execution solely because timestamps are close",
            "RECONCILED requires explicit identifier linkage",
            "Paper cannot authorize or become broker-executed without sufficient evidence",
        ],
    }
