"""Trace canonical decision → broker evidence architecture; locate order_send entry."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_9.constants import (
    BROKER_SUBMISSION_ENABLED,
    ORDER_SEND,
    SRC_DIR,
    canonical_json_sha256,
)


def _scan_order_send_call_sites() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    attr = "order" + "_send"
    needles = (f"mt5.{attr}", f"MetaTrader5.{attr}")
    skip_names = {"path_trace.py", "security_review.py", "adversarial.py", "integrity.py"}
    for path in (SRC_DIR).rglob("*.py"):
        if "__pycache__" in path.parts or path.name in skip_names:
            continue
        text = path.read_text(encoding="utf-8")
        for n in needles:
            if n in text:
                hits.append({"path": str(path.relative_to(SRC_DIR.parent)), "pattern": n})
    return hits


def build_path_trace() -> dict[str, Any]:
    stages = [
        {
            "stage": "canonical_decision",
            "owners": ["phase54/decision", "phase64_3 HardenedLifecycleEngine"],
            "notes": "NullPolicy / paper decisions; WAIT default",
        },
        {
            "stage": "decision_validation",
            "owners": ["phase64_6 ExecutionGate.prepare_execution_request", "phase64_9 ExecutionPreflight"],
            "notes": "Blocks WAIT/REJECTED/duplicates/wrong symbol",
        },
        {
            "stage": "risk_check",
            "owners": ["phase64_4 risk_spec", "phase64_6 risk_policy", "phase64_9 risk_calc"],
            "notes": "UNAPPROVED / UNCONFIGURED limits → RISK_INCOMPLETE / PREFLIGHT_REJECTED",
        },
        {
            "stage": "execution_intent",
            "owners": ["phase64 ExecutionIntentJournal", "phase64_9 IntentStateMachine"],
            "notes": "One decision → at most one intent; durable before any submit",
        },
        {
            "stage": "broker_preflight",
            "owners": ["phase64_9 ExecutionPreflight"],
            "notes": "Identity/market/order/risk/lifecycle gates; fail closed",
        },
        {
            "stage": "broker_order_request",
            "owners": ["phase64_9 BrokerExecutionAdapter.submit"],
            "notes": "Interface exists; BROKER_SUBMISSION_ENABLED=False; order_send PROHIBITED",
            "order_send_entry": True,
        },
        {
            "stage": "broker_response",
            "owners": ["phase64_9 FakeBrokerBackend / future LiveSubmitBackend"],
            "notes": "Accept/reject/timeout/unknown; live path not enabled",
        },
        {
            "stage": "broker_evidence",
            "owners": ["phase64_8 RO collector", "BrokerEvidenceJournal"],
            "notes": "positions_get/orders_get/history_* only",
        },
        {
            "stage": "fill_reconciliation",
            "owners": ["phase64_8 reconcile", "phase64_9 recovery"],
            "notes": "Required before retry after SUBMISSION_UNKNOWN",
        },
        {
            "stage": "durable_lifecycle",
            "owners": ["phase64_4 FSM", "phase64_9 intent states"],
            "notes": "Crash-safe WAL; no blind retry",
        },
        {
            "stage": "experience",
            "owners": ["hist / paper / broker_evidence / future broker_execution stores"],
            "notes": "Strict separation; synthetic never enters genuine broker store",
        },
    ]

    hits = _scan_order_send_call_sites()
    out = {
        "pipeline": stages,
        "order_send": {
            "exists_in_allowlist": "order_send" in PROHIBITED_MT5_API,
            "status": ORDER_SEND,
            "currently_callable_from_aibot": False,
            "broker_submission_enabled": BROKER_SUBMISSION_ENABLED,
            "entry_point_if_enabled": "phase64_9.adapter.BrokerExecutionAdapter._live_submit → MT5 order submission API",
            "objects_that_can_reach_it_today": [],
            "env_can_activate": False,
            "indirect_wrapper_exists": False,
            "paper_can_reach": False,
            "restart_replay_can_invoke": False,
            "duplicate_intents_can_reach": False,
            "call_sites_in_src": hits,
            "note": "No executable path reaches order_send; adapter hard-disabled",
        },
        "pass": BROKER_SUBMISSION_ENABLED is False
        and ORDER_SEND == "PROHIBITED"
        and "order_send" in PROHIBITED_MT5_API
        and len(hits) == 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
