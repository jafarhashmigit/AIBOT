"""Existing architecture audit — integration points for broker execution design."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase63.metadata import ACTIVE_SYMBOL, get_active_symbol
from phase64_3.constants import APPROVED_FACTORY, HARDENING_VERSION, RECIPE_ID as P643_RECIPE
from phase64_4.constants import (
    ACTIVE_SYMBOL as P644_SYMBOL,
    APPROVED_PAPER_FACTORY,
    RECIPE_ID,
    SUPERSEDED_SYMBOL,
    canonical_json_sha256,
)


def audit_existing_architecture() -> dict[str, Any]:
    """
    Trace existing paper → intent stack. Design attaches AFTER intent creation,
    never forks a parallel lifecycle for decisions/snapshots.
    """
    integration_points = [
        {
            "layer": "approved_paper_runtime",
            "module": APPROVED_PAPER_FACTORY,
            "role": "Sole approved construction for HardenedLifecycleEngine paper runs",
            "broker_hook": "NONE — paper only; Phase64.4 attaches post-intent design gate",
        },
        {
            "layer": "hardened_lifecycle",
            "module": "phase64_2.engine.HardenedLifecycleEngine",
            "role": "Canonical decision + intent status + WAIT durability + paper finalize",
            "broker_hook": "Intent JOURNAL stages after RISK_APPROVED / PAPER_ENTRY are the attach point",
        },
        {
            "layer": "canonical_identity",
            "module": "phase64_1.identity / market_snapshot",
            "role": "canonical_decision_id + immutable snapshot_id/hash",
            "broker_hook": "execution_request must reference existing decision_id + snapshot_id",
        },
        {
            "layer": "execution_intent_journal",
            "module": "phase64.execution_intent / phase64_2.hardened_journal",
            "role": "Append-only intent records; intent_id linkage",
            "broker_hook": "BROKER_EXECUTION_REQUEST links intent_id → execution_request_id",
        },
        {
            "layer": "risk_paper",
            "module": "phase54.risk.RiskManager",
            "role": "Paper position sizing/limits; circuit breaker",
            "broker_hook": "Broker risk gates are SEPARATE UNCONFIGURED design; do not reuse invented paper numbers as broker limits",
        },
        {
            "layer": "durable_lifecycle",
            "module": "phase57_1.durable_engine / journal",
            "role": "WAL crash recovery for paper outcomes/experiences",
            "broker_hook": "Broker reconciliation journal must be equally durable; reuse patterns, not paper journals for broker IDs",
        },
        {
            "layer": "broker_metadata",
            "module": "phase63.metadata ACTIVE_XAUUSDm_SPEC",
            "role": "User-reported XAUUSDm specs; UNKNOWN for tick/account leverage",
            "broker_hook": "Authorization requires RO MT5 verification procedure before demo execution review",
        },
        {
            "layer": "mt5_allowlist",
            "module": "phase12.mt5_allowlist",
            "role": "order_send prohibited; RO market data only",
            "broker_hook": "Phase64.4 MUST NOT expand allowlist; submission remains unreachable",
        },
        {
            "layer": "demo_collection",
            "module": "phase62 collector posture",
            "role": "READ_ONLY demo collection",
            "broker_hook": "History/deal import stays separate from hist/shadow; no store merge",
        },
    ]

    data_flow = [
        "OBSERVATION → SNAPSHOT (64.1) → CANONICAL_DECISION (64.1/64.2)",
        "→ RISK (54) → INTENT (64/64.2)",
        "→ [DESIGN] BROKER_EXECUTION_REQUEST (64.4 schema) IF AND ONLY IF authorization gate PASS",
        "→ [FUTURE PHASE — NOT IMPLEMENTED] submission adapter after allowlist + human demo authorization review",
        "→ PAPER path remains: PAPER_ENTRY → monitor → PAPER_FINALIZED / WAIT_FINALIZED",
    ]

    out = {
        "recipe": RECIPE_ID,
        "design_only": True,
        "submission_path_exists": False,
        "parallel_lifecycle_introduced": False,
        "justification": (
            "Broker execution attaches as a gated extension after hardened intent creation; "
            "paper HardenedLifecycleEngine remains the decision/intent authority."
        ),
        "active_symbol": get_active_symbol(),
        "active_symbol_expected": ACTIVE_SYMBOL,
        "superseded_symbol": SUPERSEDED_SYMBOL,
        "p644_symbol_constant": P644_SYMBOL,
        "approved_paper_factory": APPROVED_FACTORY,
        "hardening_version": HARDENING_VERSION,
        "phase64_3_recipe": P643_RECIPE,
        "integration_points": integration_points,
        "data_flow": data_flow,
        "mt5_order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "mt5_permitted_count": len(PERMITTED_MT5_API),
        "mt5_prohibited_includes_history_deals": "history_deals_get" in PROHIBITED_MT5_API,
        "note_history_deals": (
            "history_deals_get / orders_get remain PROHIBITED today. "
            "Reconciliation design therefore specifies a FUTURE read-only allowlist expansion "
            "that requires a separate security review — not performed in Phase64.4."
        ),
        "stores_remain_separate": True,
        "pass": get_active_symbol() == ACTIVE_SYMBOL == P644_SYMBOL
        and "order_send" in PROHIBITED_MT5_API
        and APPROVED_FACTORY == APPROVED_PAPER_FACTORY,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
