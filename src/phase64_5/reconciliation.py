"""Deterministic, idempotent reconciliation engine."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from phase64_5.constants import RECON_VERSION, UNKNOWN, canonical_json_sha256, sha256_hex
from phase64_5.linkage import link_journal_events


def _recon_id(*parts: str) -> str:
    return sha256_hex(f"{RECON_VERSION}:recon:" + "|".join(parts))


def reconcile(
    *,
    events: list[dict[str, Any]],
    aibot_intents: list[dict[str, Any]] | None = None,
    linkage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aibot_intents = aibot_intents or []
    linkage = linkage or link_journal_events(events, aibot_intents=aibot_intents)

    deals = [e for e in events if e.get("record_kind") == "BROKER_DEAL"]
    orders = [e for e in events if e.get("record_kind") == "BROKER_ORDER"]
    balances = [e for e in events if e.get("record_kind") == "BROKER_BALANCE_OPERATION"]

    deals_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in deals:
        oid = d.get("broker_order_id") or UNKNOWN
        deals_by_order[str(oid)].append(d)

    findings: list[dict[str, Any]] = []

    # Broker order with no deal
    order_ids_from_orders = {str(o.get("broker_order_id")) for o in orders if o.get("broker_order_id")}
    order_ids_from_deals = {str(d.get("broker_order_id")) for d in deals if d.get("broker_order_id")}
    for oid in sorted(order_ids_from_orders - order_ids_from_deals):
        findings.append(
            {
                "reconciliation_id": _recon_id("order_no_deal", oid),
                "status": "ORDER_WITHOUT_DEAL",
                "record_ids": [oid],
                "evidence": ["order_present_no_deal_with_order_id"],
                "missing_information": ["broker_deal_for_order"],
            }
        )

    # Deal with no identifiable order
    for d in deals:
        if not d.get("broker_order_id"):
            findings.append(
                {
                    "reconciliation_id": _recon_id("deal_no_order", str(d.get("broker_deal_id"))),
                    "status": "DEAL_WITHOUT_ORDER",
                    "record_ids": [d.get("event_id")],
                    "evidence": ["deal_missing_order_id"],
                    "missing_information": ["broker_order_id"],
                }
            )

    # Multiple deals / partial
    for oid, ds in deals_by_order.items():
        if oid == UNKNOWN:
            continue
        if len(ds) > 1:
            findings.append(
                {
                    "reconciliation_id": _recon_id("multi_deal", oid),
                    "status": "MULTIPLE_DEALS_FOR_ORDER",
                    "record_ids": [d.get("event_id") for d in ds],
                    "evidence": [f"n_deals={len(ds)}"],
                    "missing_information": [],
                }
            )
            # Partial if volumes suggest incomplete — without requested volume mark UNKNOWN
            vols = [d.get("volume") for d in ds if d.get("volume") is not None]
            findings.append(
                {
                    "reconciliation_id": _recon_id("partial_or_multi", oid),
                    "status": "PARTIAL_EXECUTION_POSSIBLE",
                    "record_ids": [d.get("event_id") for d in ds],
                    "evidence": [{"volumes": vols}],
                    "missing_information": ["requested_order_volume_to_confirm_partial"],
                }
            )

    # Duplicate broker identifiers already handled at ingest; report incidents separately
    # Conflicting volumes/prices among deals sharing deal_id shouldn't exist in events

    # Missing commission/swap/fees
    for d in deals:
        missing_cost = [k for k in ("commission", "swap", "fee") if d.get(k) is None]
        if missing_cost:
            findings.append(
                {
                    "reconciliation_id": _recon_id("missing_cost", str(d.get("broker_deal_id"))),
                    "status": "MISSING_COST_FIELDS",
                    "record_ids": [d.get("event_id")],
                    "evidence": ["null_cost_fields"],
                    "missing_information": missing_cost,
                }
            )

    # Unknown account/symbol provenance
    for e in events:
        if e.get("record_kind") not in ("BROKER_DEAL", "BROKER_ORDER", "BROKER_BALANCE_OPERATION"):
            continue
        prov = e.get("provenance") or {}
        if prov.get("broker_server") in (None, UNKNOWN) and e.get("record_kind") != "BROKER_FEE":
            findings.append(
                {
                    "reconciliation_id": _recon_id("unknown_server", str(e.get("event_id"))),
                    "status": "UNKNOWN_ACCOUNT_OR_SERVER_PROVENANCE",
                    "record_ids": [e.get("event_id")],
                    "evidence": ["provenance.broker_server_missing_or_unknown"],
                    "missing_information": ["broker_server"],
                }
            )
        if e.get("timezone_provenance") == UNKNOWN:
            findings.append(
                {
                    "reconciliation_id": _recon_id("tz", str(e.get("event_id"))),
                    "status": "TIMEZONE_AMBIGUITY",
                    "record_ids": [e.get("event_id")],
                    "evidence": ["timezone_provenance=UNKNOWN"],
                    "missing_information": ["export_timezone"],
                }
            )

    # Linkage-derived
    for lr in linkage.get("results") or []:
        st = lr.get("linkage_status")
        if st == "UNMATCHED_BROKER_RECORD":
            findings.append(
                {
                    "reconciliation_id": _recon_id("unmatched_broker", str(lr.get("event_id"))),
                    "status": "BROKER_ORDER_OR_DEAL_WITHOUT_VERIFIED_AIBOT_INTENT",
                    "record_ids": [lr.get("event_id")],
                    "evidence": lr.get("evidence") or [],
                    "missing_information": lr.get("missing_information") or [],
                }
            )
        elif st == "CONFLICT":
            findings.append(
                {
                    "reconciliation_id": _recon_id("link_conflict", str(lr.get("event_id"))),
                    "status": "LINKAGE_CONFLICT",
                    "record_ids": [lr.get("event_id")],
                    "evidence": [lr.get("reason")],
                    "missing_information": lr.get("missing_information") or [],
                }
            )
        elif st == "VERIFIED_LINK":
            findings.append(
                {
                    "reconciliation_id": _recon_id("verified", str(lr.get("event_id"))),
                    "status": "VERIFIED_DECISION_TO_DEAL_LINK",
                    "record_ids": [lr.get("event_id")],
                    "evidence": lr.get("evidence") or [],
                    "missing_information": lr.get("missing_information") or [],
                }
            )

    # AIBOT intents with no broker order
    linked_intents = set()
    for lr in linkage.get("results") or []:
        chain = lr.get("chain") or {}
        if lr.get("linkage_status") == "VERIFIED_LINK" and chain.get("intent_id"):
            linked_intents.add(chain["intent_id"])
    for intent in aibot_intents:
        iid = intent.get("intent_id")
        if iid and iid not in linked_intents:
            findings.append(
                {
                    "reconciliation_id": _recon_id("intent_no_broker", str(iid)),
                    "status": "AIBOT_INTENT_WITHOUT_BROKER_ORDER",
                    "record_ids": [iid],
                    "evidence": ["intent_present_no_verified_broker_link"],
                    "missing_information": ["broker_order_id"],
                }
            )

    # Balance-only notice
    if balances and not deals:
        findings.append(
            {
                "reconciliation_id": _recon_id("balance_only"),
                "status": "BALANCE_ONLY_NO_TRADE_DEALS",
                "record_ids": [b.get("event_id") for b in balances],
                "evidence": [f"n_balance={len(balances)}"],
                "missing_information": ["XAUUSDm_trade_deals"],
            }
        )

    # Stabilize: sort by reconciliation_id for determinism
    findings.sort(key=lambda x: x.get("reconciliation_id") or "")

    # Never mark unknown/conflict as silently reconciled
    unresolved = [
        f
        for f in findings
        if f.get("status")
        not in (
            "VERIFIED_DECISION_TO_DEAL_LINK",
            "MULTIPLE_DEALS_FOR_ORDER",
        )
    ]

    out = {
        "recon_version": RECON_VERSION,
        "findings": findings,
        "n_findings": len(findings),
        "n_unresolved": len(unresolved),
        "linkage_counts": linkage.get("counts"),
        "n_events": len(events),
        "n_deals": len(deals),
        "n_orders": len(orders),
        "n_balances": len(balances),
        "idempotent": True,
        "silently_reconciled_unknowns": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def reconcile_twice(events: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    a = reconcile(events=events, **kwargs)
    b = reconcile(events=events, **kwargs)
    return {
        "identical_sha256": a["sha256"] == b["sha256"],
        "identical_n_findings": a["n_findings"] == b["n_findings"],
        "pass": a["sha256"] == b["sha256"],
        "first": a,
        "second_sha256": b["sha256"],
    }
