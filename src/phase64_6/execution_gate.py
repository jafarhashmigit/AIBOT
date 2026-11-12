"""
Execution authorization hardening — submission remains unreachable.

Extends Phase64.4 gate concepts without modifying Phase64.4 source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from phase64_4.authorization_gate import (
    AuthorizationContext,
    HumanApproval,
    evaluate_authorization,
)
from phase64_4.kill_switch import KillSwitch
from phase64_6.constants import (
    ACTIVE_SYMBOL,
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    EXEC_GATE_VERSION,
    INCOMPLETE,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    UNAPPROVED,
    canonical_json_sha256,
    sha256_hex,
)
from phase64_6.risk_policy import evaluate_risk_policy_blocks, propose_demo_risk_policy


@dataclass
class ExecutionIntentPrep:
    """Prepared intent boundary — never submits."""

    canonical_decision_id: str
    intent_id: str
    action: str
    symbol: str
    snapshot_id: str | None = None
    execution_request_id: str | None = None
    replayed: bool = False


@dataclass
class ExecutionGateState:
    seen_decision_ids: set[str] = field(default_factory=set)
    seen_intent_ids: set[str] = field(default_factory=set)
    seen_execution_request_ids: set[str] = field(default_factory=set)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)


class ExecutionGate:
    def __init__(self, state: ExecutionGateState | None = None):
        self.state = state or ExecutionGateState()
        self.submission_reachable = False  # invariant

    def prepare_execution_request(self, prep: ExecutionIntentPrep) -> dict[str, Any]:
        """Deterministic prep; blocks WAIT/reject/stale/duplicates; never submits."""
        reasons: list[str] = []
        if prep.action in ("WAIT", "REJECTED", "NO_TRADE", "RISK_BLOCKED"):
            reasons.append(f"non_executable_action:{prep.action}")
        if prep.symbol != ACTIVE_SYMBOL:
            reasons.append(f"symbol_mismatch:{prep.symbol}")
        if prep.symbol == SUPERSEDED_SYMBOL:
            reasons.append("superseded_symbol")
        if prep.replayed:
            reasons.append("replayed_decision")
        if prep.canonical_decision_id in self.state.seen_decision_ids:
            reasons.append("duplicate_canonical_decision")
        if prep.intent_id in self.state.seen_intent_ids:
            reasons.append("duplicate_intent")
        # Kill switch blocks authorize/submit, not deterministic prep bookkeeping

        # One decision → at most one execution request id (deterministic)
        erid = prep.execution_request_id or sha256_hex(
            f"{EXEC_GATE_VERSION}:exec_req:{prep.intent_id}:1"
        )
        if erid in self.state.seen_execution_request_ids:
            reasons.append("duplicate_execution_request")

        if reasons:
            return {
                "status": "BLOCKED",
                "reasons": reasons,
                "execution_request_id": None,
                "submission_attempted": False,
                "submission_reachable": False,
            }

        self.state.seen_decision_ids.add(prep.canonical_decision_id)
        self.state.seen_intent_ids.add(prep.intent_id)
        self.state.seen_execution_request_ids.add(erid)
        return {
            "status": "PREPARED_NOT_AUTHORIZED",
            "execution_request_id": erid,
            "canonical_decision_id": prep.canonical_decision_id,
            "intent_id": prep.intent_id,
            "submission_attempted": False,
            "submission_reachable": False,
            "note": "Preparation only; broker submit function unreachable",
        }

    def authorize_and_submit(
        self,
        *,
        prep: ExecutionIntentPrep,
        auth_ctx: AuthorizationContext | None = None,
        metadata_bundle: dict[str, Any] | None = None,
        cost_completeness: str = INCOMPLETE,
        risk_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Full path evaluation. Always fails closed for actual submission in Phase64.6.
        """
        prepared = self.prepare_execution_request(prep)
        if prepared["status"] == "BLOCKED":
            return {**prepared, "broker_order_send": False, "fill_fabricated": False}

        if self.state.kill_switch.blocks_submission:
            return {
                "status": "BLOCKED",
                "reasons": ["kill_switch_engaged"],
                "prepared": prepared,
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }

        meta = metadata_bundle or {}
        if meta.get("status") == "BLOCKED" or meta.get("fail_closed"):
            return {
                "status": "BLOCKED",
                "reasons": [f"metadata:{meta.get('block_reason')}"],
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }
        if not meta.get("critical_metadata_complete", False):
            return {
                "status": "BLOCKED",
                "reasons": ["incomplete_critical_metadata"],
                "incomplete_fields": meta.get("incomplete_fields"),
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }
        if cost_completeness != "COMPLETE":
            return {
                "status": "BLOCKED",
                "reasons": ["unknown_or_incomplete_costs"],
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }

        risk = evaluate_risk_policy_blocks(policy=risk_policy or propose_demo_risk_policy())
        if not risk["allowed"]:
            return {
                "status": "BLOCKED",
                "reasons": risk["blocked_reasons"],
                "risk_approval_status": risk.get("approval_status"),
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }

        # Phase64.4 gate — still blocks
        auth = evaluate_authorization(auth_ctx or AuthorizationContext())
        if not auth.get("submission_authorized"):
            return {
                "status": "BLOCKED",
                "reasons": ["phase64_4_authorization_blocked"] + list(auth.get("block_reasons") or [])[:3],
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }

        # Env cannot enable
        if os.environ.get("AIBOT_BROKER_SUBMIT", "").lower() in {"1", "true", "yes"}:
            return {
                "status": "BLOCKED",
                "reasons": ["env_var_cannot_authorize"],
                "submission_attempted": False,
                "broker_order_send": False,
                "fill_fabricated": False,
            }

        # Hard invariant — even if somehow authorized, Phase64.6 has no submit implementation
        return {
            "status": "BLOCKED",
            "reasons": ["submission_function_unreachable_phase64_6"],
            "prepared": prepared,
            "submission_attempted": False,
            "broker_order_send": False,
            "fill_fabricated": False,
            "submission_reachable": False,
            "automated_orders": AUTOMATED_ORDERS,
            "broker_execution_ready": BROKER_EXECUTION_READY,
        }


def threat_model() -> dict[str, Any]:
    return {
        "exec_gate_version": EXEC_GATE_VERSION,
        "threats": [
            {
                "id": "T1",
                "threat": "Duplicate/replayed intent creates two broker orders",
                "mitigation": "seen_decision_ids/intent_ids/execution_request_ids; one exec_req per intent attempt",
            },
            {
                "id": "T2",
                "threat": "WAIT/rejected/stale decisions execute",
                "mitigation": "prepare blocks non-executable actions; metadata stale_tick blocks",
            },
            {
                "id": "T3",
                "threat": "Wrong account/symbol",
                "mitigation": "adapter expected_login/server/symbol gates + gate symbol check",
            },
            {
                "id": "T4",
                "threat": "Unknown costs still execute",
                "mitigation": "cost_completeness must be COMPLETE",
            },
            {
                "id": "T5",
                "threat": "Env var / paper readiness implies authorization",
                "mitigation": "env blocked; paper readiness not consulted; 64.4 gate + unreachable submit",
            },
            {
                "id": "T6",
                "threat": "Broker failure fabricates fill",
                "mitigation": "no submit path; no fill fabrication flag always False",
            },
            {
                "id": "T7",
                "threat": "Allowlist bypass to call order_send",
                "mitigation": "AST allowlist unchanged; adapter asserts no prohibited calls; gate submission_reachable=False",
            },
        ],
        "submission_reachable": False,
        "reconciliation_append_only": True,
    }


def audit_execution_gate() -> dict[str, Any]:
    gate = ExecutionGate()
    # WAIT blocked
    w = gate.authorize_and_submit(
        prep=ExecutionIntentPrep(
            canonical_decision_id="d1", intent_id="i1", action="WAIT", symbol=ACTIVE_SYMBOL
        )
    )
    # BUY still blocked (auth + costs + risk)
    gate2 = ExecutionGate()
    b = gate2.authorize_and_submit(
        prep=ExecutionIntentPrep(
            canonical_decision_id="d2", intent_id="i2", action="BUY", symbol=ACTIVE_SYMBOL
        ),
        metadata_bundle={"status": "OK", "critical_metadata_complete": True, "incomplete_fields": []},
        cost_completeness="COMPLETE",
        risk_policy={**propose_demo_risk_policy(account_balance=500, account_currency="USD")},
        auth_ctx=AuthorizationContext(
            human_approval=HumanApproval(
                approved=True, approver_id="x", approval_reference="y", scope="BROKER_ORDER_SUBMIT"
            )
        ),
    )
    # duplicate decision
    gate3 = ExecutionGate()
    prep = ExecutionIntentPrep(
        canonical_decision_id="d3", intent_id="i3", action="BUY", symbol=ACTIVE_SYMBOL
    )
    gate3.prepare_execution_request(prep)
    dup = gate3.prepare_execution_request(prep)
    out = {
        "threat_model": threat_model(),
        "wait_blocked": w["status"] == "BLOCKED",
        "buy_still_blocked": b["status"] == "BLOCKED" and b.get("broker_order_send") is False,
        "duplicate_blocked": dup["status"] == "BLOCKED",
        "submission_reachable": False,
        "pass": w["status"] == "BLOCKED" and b["status"] == "BLOCKED" and dup["status"] == "BLOCKED",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
