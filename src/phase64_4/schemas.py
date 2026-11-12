"""Versioned broker execution event schemas — design + validation (no submission)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase64_4.constants import (
    EVENT_TYPES,
    FORBIDDEN_KEYS,
    SCHEMA_VERSION,
    canonical_json,
    canonical_json_sha256,
    sha256_hex,
)

UNKNOWN = "UNKNOWN"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reject_forbidden(obj: dict[str, Any]) -> None:
    for k in obj:
        if str(k).lower() in FORBIDDEN_KEYS:
            raise ValueError(f"forbidden_key:{k}")
        v = obj[k]
        if isinstance(v, dict):
            reject_forbidden(v)


def make_execution_request_id(*, intent_id: str, attempt: int, schema_version: str = SCHEMA_VERSION) -> str:
    """Deterministic internal ID for an execution attempt (does not equal broker order id)."""
    return sha256_hex(f"{schema_version}:exec_req:{intent_id}:{int(attempt)}")


def make_fill_id(*, deal_id: str, execution_request_id: str) -> str:
    return sha256_hex(f"{SCHEMA_VERSION}:fill:{execution_request_id}:{deal_id}")


def linkage_chain(
    *,
    canonical_decision_id: str,
    intent_id: str,
    execution_request_id: str,
    broker_order_id: str | None = None,
    broker_deal_id: str | None = None,
    fill_id: str | None = None,
) -> dict[str, Any]:
    return {
        "canonical_decision_id": canonical_decision_id,
        "intent_id": intent_id,
        "execution_request_id": execution_request_id,
        "broker_order_id": broker_order_id if broker_order_id is not None else UNKNOWN,
        "broker_deal_id": broker_deal_id if broker_deal_id is not None else UNKNOWN,
        "fill_id": fill_id if fill_id is not None else UNKNOWN,
        "note": "Broker-generated IDs stay separate from internal deterministic IDs",
    }


def base_envelope(*, event_type: str, linkage: dict[str, Any], provenance: str) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    env = {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "event_id": sha256_hex(f"{SCHEMA_VERSION}:evt:{event_type}:{canonical_json(linkage)}:{_utc()}"),
        "recorded_at_utc": _utc(),
        "provenance": provenance,
        "linkage": linkage,
        "raw_broker_evidence": UNKNOWN,
        "raw_broker_evidence_sha256": UNKNOWN,
    }
    reject_forbidden(env)
    return env


def schema_definitions() -> dict[str, Any]:
    """Auditable field requirements for each event type."""
    common = [
        "schema_version",
        "event_type",
        "event_id",
        "recorded_at_utc",
        "provenance",
        "linkage.canonical_decision_id",
        "linkage.intent_id",
        "linkage.execution_request_id",
    ]
    defs = {
        "BROKER_EXECUTION_REQUEST": {
            "required": common
            + [
                "symbol",
                "side",
                "requested_volume",
                "order_type",
                "filling_mode",
                "attempt_number",
                "authorization_token_ref",
                "kill_switch_state",
            ],
            "unknown_ok": ["limit_price", "sl", "tp", "comment"],
            "rules": [
                "attempt_number >= 1; each attempt gets a NEW execution_request_id",
                "Never reuse execution_request_id for a second broker submission",
                "symbol must be XAUUSDm; XAUUSD forbidden",
            ],
        },
        "BROKER_ORDER_SUBMISSION": {
            "required": common + ["submission_attempted_at_utc", "adapter_version", "payload_sha256"],
            "unknown_ok": ["mt5_request_echo"],
            "rules": [
                "DESIGN-ONLY in Phase64.4 — record shape only; no live submission",
                "Timeout after this event → UNKNOWN_REQUIRES_RECONCILIATION, never blind resubmit",
            ],
        },
        "BROKER_ORDER_ACKNOWLEDGEMENT": {
            "required": common
            + [
                "broker_order_id",
                "ack_timestamp_utc",
                "broker_retcode",
                "raw_broker_evidence",
                "raw_broker_evidence_sha256",
            ],
            "unknown_ok": ["broker_comment"],
            "rules": ["broker_order_id is broker-generated; never equal to execution_request_id"],
        },
        "BROKER_DEAL": {
            "required": common
            + [
                "broker_order_id",
                "broker_deal_id",
                "deal_volume",
                "deal_price",
                "deal_timestamp_utc",
                "raw_broker_evidence",
                "raw_broker_evidence_sha256",
            ],
            "unknown_ok": ["commission", "swap", "fee"],
            "rules": [
                "Multiple deals may share one broker_order_id",
                "Idempotent ingest key = (broker_deal_id)",
            ],
        },
        "BROKER_FILL": {
            "required": common
            + [
                "broker_order_id",
                "broker_deal_id",
                "fill_id",
                "filled_volume",
                "fill_price",
                "cumulative_filled_volume",
                "remaining_volume",
            ],
            "unknown_ok": ["slippage", "latency_ms"],
            "rules": [
                "fill_id deterministic from deal_id + execution_request_id",
                "Partial fills update exposure; remaining_volume may be > 0",
            ],
        },
        "BROKER_EXECUTION_REJECTION": {
            "required": common + ["reject_reason", "broker_retcode", "rejected_at_utc"],
            "unknown_ok": ["raw_broker_evidence"],
            "rules": ["Terminal for this execution_request_id; new attempt needs new request id"],
        },
        "BROKER_EXECUTION_CANCELLATION": {
            "required": common + ["cancel_reason", "cancelled_at_utc", "broker_order_id"],
            "unknown_ok": ["raw_broker_evidence"],
            "rules": ["Must reconcile broker state before treating as cancelled locally"],
        },
        "BROKER_EXECUTION_RECONCILIATION": {
            "required": common
            + [
                "recon_id",
                "trigger",
                "broker_query_status",
                "local_state_before",
                "local_state_after",
                "incident_raised",
            ],
            "unknown_ok": ["broker_orders_found", "broker_deals_found"],
            "rules": [
                "Missing local ack ≠ broker rejection",
                "Conflicting evidence → incident_raised=True and halt submissions",
            ],
        },
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "event_types": list(EVENT_TYPES),
        "definitions": defs,
        "linkage_invariant": "canonical_decision_id → intent_id → execution_request_id → broker_order_id → broker_deal_id → fill_id",
        "unknown_policy": "Never invent missing broker fields; use UNKNOWN",
        "idempotency": {
            "execution_request": "execution_request_id unique",
            "broker_order": "broker_order_id unique per ingest",
            "broker_deal": "broker_deal_id unique per ingest",
            "fill": "fill_id unique; duplicate deal_id rejected",
        },
    }


def validate_event(event: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(event, dict):
        return False, "not_object"
    try:
        reject_forbidden(event)
    except ValueError as exc:
        return False, str(exc)
    if event.get("schema_version") != SCHEMA_VERSION:
        return False, "bad_schema_version"
    if event.get("event_type") not in EVENT_TYPES:
        return False, "bad_event_type"
    link = event.get("linkage") or {}
    for k in ("canonical_decision_id", "intent_id", "execution_request_id"):
        if not link.get(k):
            return False, f"missing_linkage:{k}"
    if event.get("event_type") == "BROKER_EXECUTION_REQUEST":
        if event.get("symbol") == "XAUUSD":
            return False, "superseded_symbol"
        if event.get("symbol") not in ("XAUUSDm", UNKNOWN):
            # Allow UNKNOWN only in incomplete drafts; production gate requires XAUUSDm
            if event.get("symbol") != "XAUUSDm":
                return False, "wrong_symbol"
    return True, "ok"


def build_example_request(
    *,
    decision_id: str,
    intent_id: str,
    attempt: int = 1,
    symbol: str = "XAUUSDm",
) -> dict[str, Any]:
    eid = make_execution_request_id(intent_id=intent_id, attempt=attempt)
    link = linkage_chain(
        canonical_decision_id=decision_id,
        intent_id=intent_id,
        execution_request_id=eid,
    )
    evt = base_envelope(
        event_type="BROKER_EXECUTION_REQUEST",
        linkage=link,
        provenance="DESIGN_FIXTURE_SIMULATED",
    )
    evt.update(
        {
            "symbol": symbol,
            "side": "BUY",
            "requested_volume": 0.01,
            "order_type": "MARKET",
            "filling_mode": "IOC",
            "attempt_number": attempt,
            "authorization_token_ref": UNKNOWN,
            "kill_switch_state": "ARMED_BLOCKING",
            "limit_price": UNKNOWN,
            "sl": UNKNOWN,
            "tp": UNKNOWN,
            "comment": UNKNOWN,
        }
    )
    # Stable event_id for fixtures (recompute without wall clock entropy for tests)
    evt["event_id"] = sha256_hex(f"{SCHEMA_VERSION}:fixture_req:{eid}")
    return evt


def audit_schemas() -> dict[str, Any]:
    defs = schema_definitions()
    ex = build_example_request(decision_id="dec_fixture", intent_id="intent_fixture")
    ok, why = validate_event(ex)
    bad_sym = build_example_request(decision_id="d", intent_id="i", symbol="XAUUSD")
    bad_ok, bad_why = validate_event(bad_sym)
    out = {
        "schema_version": SCHEMA_VERSION,
        "definitions": defs,
        "example_request_valid": ok,
        "example_request_why": why,
        "rejects_xauusd": (not bad_ok) and bad_why == "superseded_symbol",
        "evidence_type": "DESIGN_SCHEMA",
        "pass": ok and (not bad_ok) and bad_why == "superseded_symbol",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
