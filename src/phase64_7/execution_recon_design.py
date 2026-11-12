"""How future RO broker observations reconcile with Phase64.4/64.5 — design only."""

from __future__ import annotations

from typing import Any

from phase64_7.constants import canonical_json_sha256


def execution_reconciliation_design() -> dict[str, Any]:
    return {
        "design_only": True,
        "uses_existing": [
            "phase64_5.BrokerEvidenceJournal",
            "phase64_4 schemas linkage_chain / state machine",
            "phase64_4 authorization gate (submission blocked)",
        ],
        "linkage_rule": "Never infer decision→deal from timestamp/price/volume alone; require explicit intent tags or verified IDs",
        "flow": [
            {
                "step": "canonical_decision",
                "store": "phase64_2/64_3 hardened runtime",
                "id": "canonical_decision_id",
            },
            {
                "step": "execution_intent",
                "store": "HardenedIntentJournal",
                "id": "intent_id",
            },
            {
                "step": "execution_request",
                "store": "future broker exec journal",
                "id": "execution_request_id",
                "note": "Created only after authorization; Phase64.6/64.7 submit unreachable",
            },
            {
                "step": "broker_order",
                "observation": "orders_get / history_orders_get (PROHIBITED today) or CSV",
                "id": "broker_order_id",
                "link": "comment/magic aibot_intent: or aibot_exec_req:",
            },
            {
                "step": "broker_deal",
                "observation": "history_deals_get (PROHIBITED today) or CSV → BrokerEvidenceJournal",
                "id": "broker_deal_id",
            },
            {
                "step": "partial_fills",
                "rule": "Multiple deals share broker_order_id; cumulative volume; remaining UNKNOWN without order volume",
            },
            {
                "step": "full_fills",
                "rule": "Remaining volume 0 + terminal FILLED; idempotent deal ingest",
            },
            {
                "step": "rejections_cancellations",
                "rule": "Broker state → REJECTED/CANCELLED; missing local ack ≠ reject (64.4)",
            },
            {
                "step": "commission_fees",
                "rule": "From deal fields only; never published schedules; else economics INCOMPLETE",
            },
        ],
        "deterministic": True,
        "append_only": True,
        "fabricate_evidence": False,
        "modify_historical_records": False,
    }


def audit_recon_design() -> dict[str, Any]:
    d = execution_reconciliation_design()
    out = {"design": d, "pass": d["fabricate_evidence"] is False and d["append_only"] is True}
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
