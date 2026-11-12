"""Adversarial validation — every unsafe case fails closed."""

from __future__ import annotations

import os
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_4.authorization_gate import AuthorizationContext, attempt_unauthorized_submit
from phase64_6.constants import ACTIVE_SYMBOL, SUPERSEDED_SYMBOL, UNKNOWN, canonical_json_sha256
from phase64_6.contract_integrity import (
    round_volume_to_step,
    stop_loss_monetary_risk,
)
from phase64_6.execution_gate import ExecutionGate, ExecutionIntentPrep
from phase64_6.readonly_adapter import FakeMt5Backend, ReadOnlyMetadataAdapter, assert_no_prohibited_in_adapter_source
from phase64_6.risk_policy import propose_demo_risk_policy


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # MT5 disconnected
    b = FakeMt5Backend(connected=False)
    r = ReadOnlyMetadataAdapter(backend=b).fetch()
    cases.append({"name": "mt5_disconnected", "pass": r["status"] == "BLOCKED" and r.get("block_reason") == "terminal_disconnected"})

    # Wrong account
    b = FakeMt5Backend()
    r = ReadOnlyMetadataAdapter(backend=b, expected_login="999").fetch()
    cases.append({"name": "wrong_account_connected", "pass": r["status"] == "BLOCKED" and "wrong_account" in str(r.get("block_reason"))})

    # Wrong symbol
    b = FakeMt5Backend()
    assert b.symbol is not None
    b.symbol["name"] = SUPERSEDED_SYMBOL
    r = ReadOnlyMetadataAdapter(backend=b, expected_symbol=ACTIVE_SYMBOL).fetch()
    cases.append({"name": "wrong_symbol_selected", "pass": r["status"] == "BLOCKED"})

    # Stale tick
    b = FakeMt5Backend()
    assert b.symbol is not None
    b.symbol["time"] = 1
    r = ReadOnlyMetadataAdapter(backend=b, max_tick_age_sec=120).fetch()
    cases.append({"name": "stale_tick", "pass": r["status"] == "BLOCKED" and r.get("block_reason") == "stale_tick"})

    # Missing tick value → incomplete / SL risk incomplete
    sl = stop_loss_monetary_risk(entry=10, stop=9, volume=0.01, tick_size=0.001, tick_value=UNKNOWN)
    cases.append({"name": "missing_tick_value", "pass": sl["status"] == "INCOMPLETE"})

    # Invalid contract size
    from phase64_6.contract_integrity import position_notional

    pn = position_notional(price=2650, volume=0.01, contract_size=UNKNOWN)
    cases.append({"name": "invalid_contract_size", "pass": pn["status"] == "INCOMPLETE"})

    # Invalid volume step
    vs = round_volume_to_step(0.01, volume_step=UNKNOWN, volume_min=0.01, volume_max=200)
    cases.append({"name": "invalid_volume_step", "pass": vs["status"] == "INCOMPLETE"})

    # Incomplete trading sessions (via metadata bundle)
    b = FakeMt5Backend()
    r = ReadOnlyMetadataAdapter(backend=b).fetch()
    cases.append(
        {
            "name": "incomplete_trading_sessions",
            "pass": r.get("status") in ("OK", "OK_PARTIAL") and "trading_sessions" in str(r.get("incomplete_fields")),
        }
    )

    # Spread explosion — gate context
    from phase64_6.risk_policy import evaluate_risk_policy_blocks

    ev = evaluate_risk_policy_blocks(context={"spread_explosion": True})
    cases.append({"name": "spread_explosion", "pass": not ev["allowed"] and "spread_explosion" in ev["blocked_reasons"]})

    # Duplicate intent / replayed decision
    gate = ExecutionGate()
    prep = ExecutionIntentPrep(canonical_decision_id="D", intent_id="I", action="BUY", symbol=ACTIVE_SYMBOL)
    gate.prepare_execution_request(prep)
    dup = gate.prepare_execution_request(prep)
    cases.append({"name": "duplicate_intent", "pass": dup["status"] == "BLOCKED"})

    gate2 = ExecutionGate()
    replay = gate2.prepare_execution_request(
        ExecutionIntentPrep(canonical_decision_id="D2", intent_id="I2", action="BUY", symbol=ACTIVE_SYMBOL, replayed=True)
    )
    cases.append({"name": "replayed_decision", "pass": replay["status"] == "BLOCKED"})

    # Restart during intent preparation — new gate loses memory; same erid deterministic but new state allows prep once
    # Prove submit still blocked after restart
    gate_a = ExecutionGate()
    p1 = gate_a.prepare_execution_request(
        ExecutionIntentPrep(canonical_decision_id="D3", intent_id="I3", action="BUY", symbol=ACTIVE_SYMBOL)
    )
    gate_b = ExecutionGate()  # restart
    p2 = gate_b.authorize_and_submit(
        prep=ExecutionIntentPrep(canonical_decision_id="D3", intent_id="I3", action="BUY", symbol=ACTIVE_SYMBOL),
        metadata_bundle={"status": "OK", "critical_metadata_complete": False, "incomplete_fields": ["tick_value"]},
    )
    cases.append(
        {
            "name": "restart_during_intent_preparation",
            "pass": p1["status"] == "PREPARED_NOT_AUTHORIZED" and p2["status"] == "BLOCKED" and not p2.get("broker_order_send"),
        }
    )

    # Broker evidence mismatch — wrong server on adapter
    b = FakeMt5Backend()
    r = ReadOnlyMetadataAdapter(backend=b, expected_server="OTHER-SERVER").fetch()
    cases.append({"name": "broker_evidence_mismatch_server", "pass": r["status"] == "BLOCKED"})

    # Unknown commission / slippage → costs incomplete blocks submit
    gate3 = ExecutionGate()
    gate3.state.kill_switch.disengage(reason="adversarial_cost_path_only")
    c = gate3.authorize_and_submit(
        prep=ExecutionIntentPrep(canonical_decision_id="D4", intent_id="I4", action="BUY", symbol=ACTIVE_SYMBOL),
        metadata_bundle={"status": "OK", "critical_metadata_complete": True, "incomplete_fields": []},
        cost_completeness="INCOMPLETE",
    )
    cases.append({"name": "unknown_commission", "pass": c["status"] == "BLOCKED" and "incomplete" in str(c.get("reasons"))})
    cases.append({"name": "unknown_slippage", "pass": c["status"] == "BLOCKED"})  # same incomplete costs path

    # Unauthorized execution attempt
    unauth = attempt_unauthorized_submit(AuthorizationContext())
    g4 = ExecutionGate()
    u2 = g4.authorize_and_submit(
        prep=ExecutionIntentPrep(canonical_decision_id="D5", intent_id="I5", action="BUY", symbol=ACTIVE_SYMBOL)
    )
    cases.append(
        {
            "name": "unauthorized_execution_attempt",
            "pass": unauth["blocked"] and u2["status"] == "BLOCKED" and u2.get("broker_order_send") is False,
        }
    )

    # Attempted allowlist bypass
    src = assert_no_prohibited_in_adapter_source()
    cases.append({"name": "attempted_allowlist_bypass", "pass": src["pass"] and "order_send" in PROHIBITED_MT5_API})

    # Env cannot authorize
    old = os.environ.get("AIBOT_BROKER_SUBMIT")
    try:
        os.environ["AIBOT_BROKER_SUBMIT"] = "true"
        g5 = ExecutionGate()
        # Even with complete meta+costs, risk UNAPPROVED and 64.4 block; also env check inside authorize
        e = g5.authorize_and_submit(
            prep=ExecutionIntentPrep(canonical_decision_id="D6", intent_id="I6", action="BUY", symbol=ACTIVE_SYMBOL),
            metadata_bundle={"status": "OK", "critical_metadata_complete": True, "incomplete_fields": []},
            cost_completeness="COMPLETE",
            risk_policy=propose_demo_risk_policy(account_balance=500, account_currency="USD"),
        )
        cases.append({"name": "env_cannot_authorize_submit", "pass": e["status"] == "BLOCKED"})
    finally:
        if old is None:
            os.environ.pop("AIBOT_BROKER_SUBMIT", None)
        else:
            os.environ["AIBOT_BROKER_SUBMIT"] = old

    # initialize failed
    b = FakeMt5Backend(init_ok=False)
    r = ReadOnlyMetadataAdapter(backend=b).fetch()
    cases.append({"name": "initialize_failed", "pass": r["status"] == "BLOCKED"})

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
        "evidence": "SIMULATED_FIXTURE_BACKEND",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
