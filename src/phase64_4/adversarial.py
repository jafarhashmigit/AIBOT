"""Adversarial validation for Phase64.4 design + authorization gate."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_4.authorization_gate import (
    AuthorizationContext,
    HumanApproval,
    attempt_unauthorized_submit,
    evaluate_authorization,
)
from phase64_4.constants import RECIPE_ID, canonical_json_sha256
from phase64_4.economics import empty_cost_ledger, finalize_economics
from phase64_4.kill_switch import KillSwitch
from phase64_4.risk_spec import default_broker_risk_config, evaluate_broker_risk_gates
from phase64_4.schemas import (
    build_example_request,
    make_execution_request_id,
    make_fill_id,
    validate_event,
)
from phase64_4.state_machine import BrokerExecutionStateMachine, ExecutionStateError


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # Duplicate execution request id
    a = make_execution_request_id(intent_id="i1", attempt=1)
    b = make_execution_request_id(intent_id="i1", attempt=1)
    c = make_execution_request_id(intent_id="i1", attempt=2)
    cases.append(
        {
            "name": "duplicate_execution_request_deterministic",
            "pass": a == b and a != c,
            "evidence": "SIMULATED",
        }
    )

    # Duplicate broker order / deal handling in FSM
    sm = BrokerExecutionStateMachine(execution_request_id="er_dup")
    for s in ("VALIDATED", "AUTHORIZED"):
        sm.transition(s, reason="ok")
    sm.mark_submission_pending()
    sm.transition("ACKNOWLEDGED", reason="ack")
    sm.broker_order_id = "BO1"
    sm.ingest_deal(deal_id="D1", price=1.0, volume=0.01, remaining=0.0)
    dup_deal = False
    try:
        sm2 = BrokerExecutionStateMachine(execution_request_id="er_dup2")
        for s in ("VALIDATED", "AUTHORIZED"):
            sm2.transition(s, reason="ok")
        sm2.mark_submission_pending()
        sm2.transition("ACKNOWLEDGED", reason="ack")
        sm2.ingest_deal(deal_id="D9", price=1.0, volume=0.01, remaining=0.01)
        sm2.ingest_deal(deal_id="D9", price=1.1, volume=0.01, remaining=0.0)
    except ExecutionStateError:
        dup_deal = True
    cases.append({"name": "duplicate_deal_id", "pass": dup_deal, "evidence": "SIMULATED"})

    # Partial fills
    sm3 = BrokerExecutionStateMachine(execution_request_id="er_pf")
    for s in ("VALIDATED", "AUTHORIZED"):
        sm3.transition(s, reason="ok")
    sm3.mark_submission_pending()
    sm3.transition("ACKNOWLEDGED", reason="ack")
    sm3.ingest_deal(deal_id="P1", price=10.0, volume=0.01, remaining=0.01)
    cases.append(
        {
            "name": "partial_fills",
            "pass": sm3.state == "PARTIALLY_FILLED",
            "evidence": "SIMULATED",
        }
    )

    # Conflicting fill prices → incident
    sm4 = BrokerExecutionStateMachine(execution_request_id="er_cf")
    sm4.raise_conflict_incident(reason="conflicting_fill_prices")
    cases.append(
        {
            "name": "conflicting_fill_prices",
            "pass": sm4.incident_raised and sm4.state == "UNKNOWN_REQUIRES_RECONCILIATION",
            "evidence": "SIMULATED",
        }
    )

    # Timeout after acceptance path
    sm5 = BrokerExecutionStateMachine(execution_request_id="er_to")
    for s in ("VALIDATED", "AUTHORIZED"):
        sm5.transition(s, reason="ok")
    sm5.mark_submission_pending()
    sm5.on_timeout_without_ack()
    cases.append(
        {
            "name": "timeout_after_broker_acceptance_uncertainty",
            "pass": sm5.state == "UNKNOWN_REQUIRES_RECONCILIATION",
            "evidence": "SIMULATED",
        }
    )

    # Missing acknowledgement ≠ reject
    cases.append(
        {
            "name": "missing_acknowledgement_not_reject",
            "pass": sm5.state != "REJECTED",
            "evidence": "SIMULATED",
        }
    )

    # Account mismatch
    ctx = AuthorizationContext(
        expected_demo_login="111",
        observed_demo_login="222",
        active_symbol="XAUUSDm",
    )
    auth = evaluate_authorization(ctx)
    cases.append(
        {
            "name": "account_mismatch",
            "pass": not auth["gates"]["demo_account_identity"]["pass"],
            "evidence": "SIMULATED",
        }
    )

    # Wrong symbol
    bad = build_example_request(decision_id="d", intent_id="i", symbol="XAUUSD")
    ok, why = validate_event(bad)
    cases.append({"name": "wrong_symbol", "pass": (not ok) and why == "superseded_symbol", "evidence": "SIMULATED"})

    # Unknown tick size blocks metadata gate
    ctx2 = AuthorizationContext(
        symbol_metadata={"tick_size": "UNKNOWN", "tick_value": "UNKNOWN"},
        active_symbol="XAUUSDm",
    )
    auth2 = evaluate_authorization(ctx2)
    cases.append(
        {
            "name": "unknown_tick_size",
            "pass": not auth2["gates"]["complete_symbol_metadata"]["pass"],
            "evidence": "SIMULATED",
        }
    )

    # Incomplete commission → economics INCOMPLETE
    led = empty_cost_ledger(execution_request_id="er_e")
    led["components"]["commission"] = "UNKNOWN"
    fin = finalize_economics(led)
    cases.append(
        {
            "name": "incomplete_commission",
            "pass": fin["total_execution_economics"] == "INCOMPLETE",
            "evidence": "SIMULATED",
        }
    )

    # Stale quote
    risk = evaluate_broker_risk_gates(context={"stale_quote": True})
    cases.append({"name": "stale_quote", "pass": not risk["allowed"] and "stale_market_data" in risk["blocked_reasons"], "evidence": "SIMULATED"})

    # Risk limit not configured
    risk2 = evaluate_broker_risk_gates()
    cases.append(
        {
            "name": "risk_limit_not_configured",
            "pass": not risk2["allowed"],
            "evidence": "SIMULATED",
        }
    )

    # Kill switch
    ks = KillSwitch()
    cases.append({"name": "kill_switch_activated", "pass": ks.blocks_submission, "evidence": "SIMULATED"})

    # Corrupt journal (invalid schema event)
    corrupt = {"schema_version": "bad", "event_type": "BROKER_DEAL"}
    cok, _ = validate_event(corrupt)
    cases.append({"name": "corrupt_journal_event", "pass": not cok, "evidence": "SIMULATED"})

    # Restart during reconciliation + repeated recon
    sm6 = BrokerExecutionStateMachine(execution_request_id="er_recon")
    for s in ("VALIDATED", "AUTHORIZED"):
        sm6.transition(s, reason="ok")
    sm6.mark_submission_pending()
    sm6.on_timeout_without_ack()
    sm6.transition("UNKNOWN_REQUIRES_RECONCILIATION", reason="repeat_recon")
    cases.append(
        {
            "name": "restart_during_reconciliation",
            "pass": sm6.state == "UNKNOWN_REQUIRES_RECONCILIATION",
            "evidence": "SIMULATED",
        }
    )
    cases.append(
        {
            "name": "repeated_reconciliation",
            "pass": sm6.state == "UNKNOWN_REQUIRES_RECONCILIATION" and not sm6.incident_raised,
            "evidence": "SIMULATED",
        }
    )

    # Unauthorized submission attempt
    unauth = attempt_unauthorized_submit()
    cases.append(
        {
            "name": "unauthorized_submission_attempt",
            "pass": unauth["blocked"] and not unauth["reached_order_send"],
            "evidence": "SYNTHETIC_UNAUTHORIZED_ATTEMPT",
        }
    )

    # Env var cannot authorize
    old = os.environ.get("AIBOT_BROKER_SUBMIT")
    try:
        os.environ["AIBOT_BROKER_SUBMIT"] = "true"
        auth_env = evaluate_authorization(
            AuthorizationContext(human_approval=HumanApproval(approved=True, approver_id="x", approval_reference="y", scope="DEMO_EXECUTION_REVIEW_PENDING"))
        )
        env_blocked = not auth_env["gates"]["explicit_human_approval"]["pass"]
    finally:
        if old is None:
            os.environ.pop("AIBOT_BROKER_SUBMIT", None)
        else:
            os.environ["AIBOT_BROKER_SUBMIT"] = old
    cases.append({"name": "env_cannot_authorize", "pass": env_blocked, "evidence": "SIMULATED"})

    # order_send still prohibited
    cases.append({"name": "order_send_prohibited", "pass": "order_send" in PROHIBITED_MT5_API, "evidence": "ALLOWLIST"})

    # fill id stable
    f1 = make_fill_id(deal_id="D", execution_request_id="E")
    f2 = make_fill_id(deal_id="D", execution_request_id="E")
    cases.append({"name": "duplicate_fill_id_stable", "pass": f1 == f2, "evidence": "SIMULATED"})

    # Default auth all blocked for submission
    default_auth = evaluate_authorization()
    cases.append(
        {
            "name": "default_authorization_blocks_submission",
            "pass": default_auth["submission_authorized"] is False,
            "evidence": "SIMULATED",
        }
    )

    # Recipe + no secrets in default config dump
    cfg = default_broker_risk_config()
    dumped = json.dumps(cfg)
    cases.append(
        {
            "name": "no_credentials_in_risk_config",
            "pass": "password" not in dumped.lower() and RECIPE_ID.startswith("phase64_4"),
            "evidence": "SIMULATED",
        }
    )

    # Temp journal write without secrets
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "evt.json"
        p.write_text(json.dumps(build_example_request(decision_id="d", intent_id="i")), encoding="utf-8")
        text = p.read_text(encoding="utf-8")
        cases.append(
            {
                "name": "fixture_event_no_password",
                "pass": "password" not in text.lower(),
                "evidence": "SIMULATED",
            }
        )

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
        "genuine_broker_evidence": 0,
        "evidence_label": "SIMULATED_FIXTURE_WHERE_NO_BROKER",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
