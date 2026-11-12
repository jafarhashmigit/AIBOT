"""Canonical decision identity — deterministic, idempotent; never rewrite historical IDs."""

from __future__ import annotations

from typing import Any

from phase64_1.constants import (
    DECISION_ID_SCHEME,
    DOMAIN_AGENT_SHADOW,
    canonical_json_sha256,
    sha256_hex,
)


COMPATIBILITY = {
    "phase6_journal_id": "Deterministic `{timestamp}_{market}_{timeframe}` — research journal only; not paper path",
    "phase54_runtime_uuid": "uuid4.hex from decide() — retained as runtime_uuid_decision_id; never rewritten in hist stores",
    "phase64_1_canonical": (
        "sha256 of (scheme, domain, symbol, timeframe, bar_timestamp_utc, snapshot_hash, policy_version) — "
        "forward paper path identity; one logical decision → one canonical id"
    ),
    "intent_id": "Independent UUID per intent journal record; at most one executable intent per canonical decision",
    "position_id": "Paper position UUID from phase54.paper_exec",
    "txn_id": "Phase57.1 durable txn per position",
    "broker_order_deal_id": "Future/demo only — never fabricated as genuine in Phase64.1",
    "migration": (
        "Historical phase54/57.1 experiences keep original decision_id UUIDs. "
        "New Phase64.1 runs annotate decision_id=canonical and store runtime_uuid_decision_id. "
        "No silent rewrite of prior JSONL/experience rows."
    ),
}


def make_canonical_decision_id(
    *,
    domain: str,
    symbol: str,
    timeframe: str,
    bar_timestamp_utc: str,
    snapshot_hash: str,
    policy_version: str,
) -> str:
    """Deterministic decision identity for the same logical decision inputs."""
    body = {
        "scheme": DECISION_ID_SCHEME,
        "domain": domain,
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_timestamp_utc": bar_timestamp_utc,
        "snapshot_hash": snapshot_hash,
        "policy_version": policy_version,
    }
    return sha256_hex(canonical_json_sha256(body) + "|decision")


def apply_canonical_identity(
    decision: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    domain: str = DOMAIN_AGENT_SHADOW,
    policy_version: str,
) -> dict[str, Any]:
    """
    Annotate a phase54 decide() result with canonical identity.
    Preserves runtime UUID; does not mutate external historical stores.
    """
    out = dict(decision)
    runtime_uuid = str(out.get("decision_id") or "")
    canonical = make_canonical_decision_id(
        domain=domain,
        symbol=str(snapshot.get("symbol") or out.get("instrument") or "UNKNOWN"),
        timeframe=str(snapshot.get("timeframe") or out.get("timeframe") or "UNKNOWN"),
        bar_timestamp_utc=str(snapshot.get("bar_timestamp_utc") or out.get("timestamp_utc") or "UNKNOWN"),
        snapshot_hash=str(snapshot.get("snapshot_hash") or "UNKNOWN"),
        policy_version=str(policy_version),
    )
    out["runtime_uuid_decision_id"] = runtime_uuid
    out["decision_id"] = canonical
    out["decision_id_scheme"] = DECISION_ID_SCHEME
    out["snapshot_id"] = snapshot.get("snapshot_id")
    out["snapshot_hash"] = snapshot.get("snapshot_hash")
    out["identity_domain"] = domain
    # Enrich refs for intent / slippage (UNKNOWN if absent — never invent)
    ea = dict(out.get("execution_assumptions") or {})
    if snapshot.get("bid") is not None:
        ea["bid_ref"] = snapshot.get("bid")
    if snapshot.get("ask") is not None:
        ea["ask_ref"] = snapshot.get("ask")
    out["execution_assumptions"] = ea
    return out


def identity_contract() -> dict[str, Any]:
    out = {
        "scheme": DECISION_ID_SCHEME,
        "compatibility": COMPATIBILITY,
        "separates": {
            "decision_id": "canonical logical decision",
            "runtime_uuid_decision_id": "phase54 decide() UUID (compat)",
            "intent_id": "execution intent",
            "position_id": "paper position",
            "txn_id": "phase57.1 durable txn",
            "broker_order_id": "future broker order (not authorized here)",
            "broker_deal_id": "future broker deal (not authorized here)",
        },
        "domains_isolated": [DOMAIN_AGENT_SHADOW, "HISTORICAL_HYPOTHETICAL", "EXNESS_DEMO"],
        "historical_ids_rewritten": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
