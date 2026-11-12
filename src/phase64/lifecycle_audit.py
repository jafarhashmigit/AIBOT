"""Static + runtime lifecycle stage inventory (read-only over prior phases)."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64.constants import LIFECYCLE_STAGES, canonical_json_sha256


def audit_lifecycle() -> dict[str, Any]:
    """
    Document EXISTS / PARTIAL / MISSING for the decision→execution path.
    Does not activate broker execution. FUTURE_BROKER_ORDER remains NOT_AUTHORIZED.
    """
    stages: dict[str, dict[str, Any]] = {
        "OBSERVATION": {
            "status": "EXISTS",
            "owners": ["phase54.observer", "phase56.observer"],
            "notes": "build_observation / MarketObserver; historical ticks only",
        },
        "MARKET_SNAPSHOT": {
            "status": "PARTIAL",
            "owners": ["phase54.observer", "phase6.schemas.MarketState"],
            "notes": "Embedded as market_state_id + observation; no first-class persisted MarketSnapshot type",
        },
        "DECISION": {
            "status": "EXISTS",
            "owners": ["phase54.decision.decide", "phase6.decision_engine"],
            "notes": "BUY/SELL/WAIT; default NullPolicy → WAIT",
        },
        "UNIQUE_DECISION_ID": {
            "status": "EXISTS",
            "owners": ["phase54.decision (uuid4.hex)", "phase6.journal (deterministic bar id)"],
            "notes": "Paper path uses globally unique UUID; phase6 journal uses deterministic per-bar id — inconsistent semantics across research vs paper",
        },
        "RISK_CHECK": {
            "status": "EXISTS",
            "owners": ["phase54.risk.RiskManager", "phase6.risk_gate"],
            "notes": "May downgrade BUY/SELL → WAIT; never invents direction",
        },
        "EXECUTION_INTENT": {
            "status": "PARTIAL",
            "owners": ["phase64.execution_intent (NEW scaffold)"],
            "notes": "Was MISSING system-wide before Phase64; Phase64 introduces append-only intent journal scaffold. Not wired into phase54/56 production lifecycle.",
        },
        "FUTURE_BROKER_ORDER": {
            "status": "MISSING",
            "owners": [],
            "notes": "Intentional. order_send prohibited. Automated orders DISABLED. Marked NOT_TESTED for genuine broker submission.",
            "broker_test_status": "NOT_TESTED",
        },
        "BROKER_DEAL": {
            "status": "PARTIAL",
            "owners": ["phase62.store.ExecutionStore", "phase63.import_pipeline"],
            "notes": "Genuine Exness demo CSV import path exists; not linked to paper decision_id. Current genuine XAUUSDm deals: awaiting non-empty CSV.",
        },
        "PARTIAL_OR_FULL_FILL": {
            "status": "PARTIAL",
            "owners": ["phase54.paper_exec (full fill only)", "phase62.schema (multi-deal/order)"],
            "notes": "Paper: single full fill. Demo schema supports multi-deal; independent decisions require linkage (Phase64 counts by decision_id).",
        },
        "COMMISSION_FEES": {
            "status": "PARTIAL",
            "owners": ["phase59.costs", "phase61.commission", "phase63.economics"],
            "notes": "UNKNOWN must not become zero. Paper commission=None. Demo from CSV when present.",
        },
        "EXECUTION_OUTCOME": {
            "status": "EXISTS",
            "owners": ["phase54.paper_exec", "phase57_1.outcome", "phase6.outcome"],
            "notes": "Paper/durable outcomes exist; no broker outcome on paper path",
        },
        "EXPERIENCE": {
            "status": "EXISTS",
            "owners": ["phase54.experience", "phase50.experience_store", "phase57_1.outcome"],
            "notes": "AGENT_SHADOW / HISTORICAL_HYPOTHETICAL separate from Exness demo store",
        },
    }

    existing = [s for s, v in stages.items() if v["status"] == "EXISTS"]
    partial = [s for s, v in stages.items() if v["status"] == "PARTIAL"]
    missing = [s for s, v in stages.items() if v["status"] == "MISSING"]

    out = {
        "lifecycle_order": list(LIFECYCLE_STAGES),
        "stages": stages,
        "summary": {
            "exists": existing,
            "partial": partial,
            "missing": missing,
            "n_exists": len(existing),
            "n_partial": len(partial),
            "n_missing": len(missing),
        },
        "critical_gaps": [
            "EXECUTION_INTENT not wired into production lifecycle (scaffold only in Phase64)",
            "FUTURE_BROKER_ORDER not authorized / not tested with genuine broker",
            "Paper decision_id not linked to genuine broker order_id/deal_id",
            "No genuine XAUUSDm demo fills available for end-to-end evidence",
        ],
        "safety": {
            "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
            "automated_orders": "DISABLED",
            "live": "NOT_AUTHORIZED",
            "demo_collection": "READ_ONLY",
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
