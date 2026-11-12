"""Conservative decision→deal linkage — never infer from time/price/volume alone."""

from __future__ import annotations

import re
from typing import Any

from phase64_4.schemas import make_execution_request_id, make_fill_id
from phase64_5.constants import UNKNOWN, canonical_json_sha256, sha256_hex

# Only accept explicit identifiers in comment/magic
INTENT_COMMENT_RE = re.compile(r"aibot_intent:([A-Za-z0-9_\-]+)")
DECISION_COMMENT_RE = re.compile(r"aibot_decision:([A-Za-z0-9_\-]+)")
EXEC_REQ_COMMENT_RE = re.compile(r"aibot_exec_req:([A-Za-z0-9_\-]+)")


def extract_explicit_ids(record: dict[str, Any]) -> dict[str, str | None]:
    comment = str(record.get("comment") or "")
    magic = str(record.get("magic") or "")
    intent = None
    decision = None
    exec_req = None
    m = INTENT_COMMENT_RE.search(comment)
    if m:
        intent = m.group(1)
    m = DECISION_COMMENT_RE.search(comment)
    if m:
        decision = m.group(1)
    m = EXEC_REQ_COMMENT_RE.search(comment)
    if m:
        exec_req = m.group(1)
    return {
        "intent_id": intent,
        "canonical_decision_id": decision,
        "execution_request_id": exec_req,
        "magic": magic if magic and magic != UNKNOWN else None,
    }


def classify_link(
    *,
    broker_record: dict[str, Any],
    aibot_intents: list[dict[str, Any]] | None = None,
    aibot_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Link only with reliable identifiers.
    Matching timestamp/direction/volume/price alone → UNVERIFIED_CANDIDATE at most,
    and we intentionally do NOT auto-promote those.
    """
    aibot_intents = aibot_intents or []
    aibot_decisions = aibot_decisions or []
    ids = extract_explicit_ids(broker_record)
    broker_order_id = broker_record.get("broker_order_id")
    broker_deal_id = broker_record.get("broker_deal_id")

    missing = []
    if not ids["intent_id"] and not ids["execution_request_id"] and not ids["canonical_decision_id"]:
        missing.append("explicit_aibot_identifier_in_comment_or_mapped_magic")

    if ids["intent_id"]:
        match = next((i for i in aibot_intents if i.get("intent_id") == ids["intent_id"]), None)
        if match is None and aibot_intents:
            # Intent id claimed but not found in provided set
            return {
                "linkage_status": "CONFLICT",
                "reason": "comment_intent_id_not_found_in_aibot_set",
                "extracted": ids,
                "broker_order_id": broker_order_id,
                "broker_deal_id": broker_deal_id,
                "missing_information": ["matching_aibot_intent_record"],
            }
        if match is not None or not aibot_intents:
            # Verified when comment carries intent id (and matches if set provided)
            did = ids["canonical_decision_id"] or (match or {}).get("decision_id") or UNKNOWN
            iid = ids["intent_id"]
            erid = ids["execution_request_id"]
            if erid is None and iid != UNKNOWN:
                # Do not manufacture execution_request unless we have intent+attempt — leave UNKNOWN
                erid = UNKNOWN
            fill_id = UNKNOWN
            if broker_deal_id and erid not in (None, UNKNOWN):
                fill_id = make_fill_id(deal_id=str(broker_deal_id), execution_request_id=str(erid))
            return {
                "linkage_status": "VERIFIED_LINK",
                "reason": "explicit_intent_id_in_broker_comment",
                "chain": {
                    "canonical_decision_id": did,
                    "intent_id": iid,
                    "execution_request_id": erid,
                    "broker_order_id": broker_order_id or UNKNOWN,
                    "broker_deal_id": broker_deal_id or UNKNOWN,
                    "fill_id": fill_id,
                },
                "extracted": ids,
                "missing_information": []
                if erid != UNKNOWN
                else ["execution_request_id_not_present_in_export"],
                "evidence": ["broker_comment_aibot_intent_tag"],
            }

    # No reliable link — keep unmatched (do not use time/price/volume)
    return {
        "linkage_status": "UNMATCHED_BROKER_RECORD",
        "reason": "insufficient_identifiers_for_verified_link",
        "extracted": ids,
        "broker_order_id": broker_order_id,
        "broker_deal_id": broker_deal_id,
        "missing_information": missing
        + [
            "Do not infer from timestamp/direction/volume/price alone",
        ],
        "evidence": [],
        "manual_trade_not_aibot_decision": True,
    }


def link_journal_events(
    events: list[dict[str, Any]],
    *,
    aibot_intents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    results = []
    for e in events:
        if e.get("record_kind") not in ("BROKER_DEAL", "BROKER_ORDER"):
            continue
        # Paper decisions must never be treated as broker fills — skip synthetic paper markers
        if e.get("evidence_label") == "PAPER_SIMULATED_AS_BROKER":
            results.append(
                {
                    "linkage_status": "CONFLICT",
                    "reason": "paper_decision_presented_as_broker_fill",
                    "event_id": e.get("event_id"),
                }
            )
            continue
        r = classify_link(broker_record=e, aibot_intents=aibot_intents)
        r["event_id"] = e.get("event_id")
        r["record_kind"] = e.get("record_kind")
        r["linkage_id"] = sha256_hex(f"link:{e.get('event_id')}:{r.get('linkage_status')}")
        results.append(r)

    counts = {
        "VERIFIED_LINK": sum(1 for r in results if r.get("linkage_status") == "VERIFIED_LINK"),
        "UNVERIFIED_CANDIDATE": sum(1 for r in results if r.get("linkage_status") == "UNVERIFIED_CANDIDATE"),
        "UNMATCHED_BROKER_RECORD": sum(1 for r in results if r.get("linkage_status") == "UNMATCHED_BROKER_RECORD"),
        "CONFLICT": sum(1 for r in results if r.get("linkage_status") == "CONFLICT"),
    }
    out = {"results": results, "counts": counts, "n": len(results)}
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
