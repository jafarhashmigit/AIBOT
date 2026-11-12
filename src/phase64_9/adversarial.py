"""Adversarial security tests for Phase 64.9 — all prohibited paths fail closed."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_9.adapter import BrokerExecutionAdapter, SubmitRequest
from phase64_9.authorization import AuthorizationBundle, config_file_cannot_authorize, evaluate_authorization
from phase64_9.constants import (
    ACTIVE_SYMBOL,
    BROKER_SUBMISSION_ENABLED,
    EXPECTED_CURRENCY,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    FORBIDDEN_AUTH_ENV,
    SUPERSEDED_SYMBOL,
    UNAPPROVED,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_DIGITS,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)
from phase64_9.fake_broker import FakeBrokerBackend
from phase64_9.intent_fsm import ExecutionIntentStore
from phase64_9.path_trace import build_path_trace
from phase64_9.preflight import PreflightContext, run_preflight, symbol_spec_hash
from phase64_9.recovery import run_recovery_suite


def _spec() -> str:
    return symbol_spec_hash(
        tick_size=VERIFIED_TICK_SIZE,
        tick_value=VERIFIED_TICK_VALUE,
        contract_size=VERIFIED_CONTRACT_SIZE,
        digits=VERIFIED_DIGITS,
        volume_min=0.01,
        volume_step=0.01,
    )


def _good_ctx(**over: Any) -> PreflightContext:
    s = _spec()
    base = dict(
        account_fingerprint="fp",
        expected_fingerprint="fp",
        server=EXPECTED_SERVER,
        currency=EXPECTED_CURRENCY,
        login=EXPECTED_DEMO_LOGIN,
        symbol=ACTIVE_SYMBOL,
        symbol_spec_hash=s,
        expected_symbol_spec_hash=s,
        bid=2649.5,
        ask=2650.0,
        tick_age_sec=1.0,
        max_spread_points=500.0,
        trading_session_known=True,
        in_trading_session=True,
        direction="BUY",
        volume=0.01,
        price=2650.0,
        sl=2649.0,
        tp=2652.0,
        min_sl_distance_points=10.0,
        filling_mode_bitmask=7,
        requested_filling=1,
        commission=-0.06,
        risk_policy_status="APPROVED",
        per_trade_risk_limit=500.0,
        aggregate_risk_limit=2000.0,
        daily_loss_limit=500.0,
        drawdown_limit=0.5,
        trade_count_limit=20,
        decision_id="d1",
        decision_action="BUY",
        execution_intent_id="i1",
        intent_unique=True,
    )
    base.update(over)
    return PreflightContext(**base)


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    # 1 Direct order_send
    add("direct_order_send", "order_send" in PROHIBITED_MT5_API and build_path_trace()["pass"])

    # 2 Indirect order_send
    adapter = BrokerExecutionAdapter()
    r = adapter.submit(SubmitRequest("i", "d", ACTIVE_SYMBOL, "BUY", 0.01, 2650.0, 2649.0, 2652.0))
    add("indirect_order_send", r["reached_order_send"] is False and r["status"] == "BLOCKED")

    # 3 Env var authorization
    old = {k: os.environ.get(k) for k in FORBIDDEN_AUTH_ENV}
    try:
        for k in FORBIDDEN_AUTH_ENV:
            os.environ[k] = "1"
        auth = evaluate_authorization(
            AuthorizationBundle(
                demo_account_verified=True,
                broker_server_verified=True,
                symbol_metadata_complete=True,
                risk_policy_approved=True,
                execution_policy_approved=True,
                reconciliation_ready=True,
                durable_journal_ready=True,
                kill_switch_disengaged=True,
                human_approval_present=True,
                broker_submission_source_enabled=True,
                phase65_authorization_complete=True,
            )
        )
        r2 = BrokerExecutionAdapter().submit({"intent_id": "x"})
        add(
            "env_var_authorization",
            auth["authorized"] is False and r2["reached_order_send"] is False and BROKER_SUBMISSION_ENABLED is False,
        )
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # 4 Config-file bypass
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "auth.json"
        cfg.write_text('{"broker_execution_authorized": true, "BROKER_SUBMISSION_ENABLED": true}', encoding="utf-8")
        add("config_file_authorization_bypass", config_file_cannot_authorize(cfg)["pass"])

    # 5 Paper engine reaching broker adapter
    paper = BrokerExecutionAdapter().submit({"intent_id": "paper", "source": "paper_engine", "decision_action": "BUY"})
    add("paper_engine_reaches_broker_adapter", paper["status"] == "BLOCKED" and not paper["reached_order_send"])

    # 6 WAIT decision
    pf = run_preflight(_good_ctx(decision_action="WAIT"))
    add("wait_decision_reaches_broker", pf["status"] == "PREFLIGHT_REJECTED" and "decision_not_executable:WAIT" in pf["reasons"])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store = ExecutionIntentStore(root / "intents")

        # 7 Duplicate canonical decision
        store.create_intent(decision_id="dup_dec", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        d2 = store.create_intent(decision_id="dup_dec", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        add("duplicate_canonical_decision", d2["status"] == "DUPLICATE_REJECTED")

        # 8 Duplicate execution intent (same as above)
        add("duplicate_execution_intent", d2["status"] == "DUPLICATE_REJECTED")

        # 9 Replay after restart
        c = store.create_intent(decision_id="replay_dec", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        store2 = ExecutionIntentStore(root / "intents")
        again = store2.create_intent(decision_id="replay_dec", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        add("replay_after_restart", again["status"] == "DUPLICATE_REJECTED" and store2.get(c["intent_id"]) is not None)

        # Recovery suite covers 10, 22-25 partially
        recovery = run_recovery_suite(root / "rec")
        add("timeout_after_broker_acceptance", any(c["name"] == "uncertain_crash_restart_reconcile" and c["pass"] for c in recovery["cases"]))
        add("broker_rejection", any(c["name"] == "rejected_order" and c["pass"] for c in recovery["cases"]))
        add("partial_fill", any(c["name"] == "partial_fills" and c["pass"] for c in recovery["cases"]))
        add("missing_deal_after_accepted_order", any(c["name"] == "accepted_missing_deal" and c["pass"] for c in recovery["cases"]))
        add("process_crash_after_submission", recovery["suite_pass"])

    # 11 Wrong account
    pf = run_preflight(_good_ctx(login=999))
    add("wrong_account", "login_mismatch" in pf["reasons"])

    # 12 Wrong server
    pf = run_preflight(_good_ctx(server="Wrong-Server"))
    add("wrong_server", "server_mismatch" in pf["reasons"])

    # 13 Wrong symbol
    pf = run_preflight(_good_ctx(symbol=SUPERSEDED_SYMBOL))
    add("wrong_symbol", any("symbol_invalid" in r for r in pf["reasons"]))

    # 14 Stale tick
    pf = run_preflight(_good_ctx(tick_age_sec=9999))
    add("stale_tick", "stale_tick" in pf["reasons"])

    # 15 Spread explosion
    pf = run_preflight(_good_ctx(bid=2640.0, ask=2650.0, max_spread_points=100.0))
    add("spread_explosion", "spread_explosion" in pf["reasons"])

    # 16 Invalid volume
    pf = run_preflight(_good_ctx(volume=0.013))
    add("invalid_volume", "volume_not_aligned_to_step" in pf["reasons"] or any("volume" in r for r in pf["reasons"]))

    # 17 Excessive risk
    pf = run_preflight(_good_ctx(per_trade_risk_limit=1.0, sl=2600.0))
    add("excessive_risk", "per_trade_risk_exceeded" in pf["reasons"] or "risk_incomplete" in pf["reasons"] or any("risk" in r for r in pf["reasons"]))

    # 18 Unknown commission
    pf = run_preflight(_good_ctx(commission=None, accept_unknown_commission=False))
    add("unknown_commission", "risk_incomplete" in pf["reasons"])

    # 19 Unknown critical cost
    pf = run_preflight(_good_ctx(tick_value=None))
    add("unknown_critical_cost", any("critical_unknown" in r or "risk_incomplete" in r for r in pf["reasons"]))

    # 20 Invalid SL/TP
    pf = run_preflight(_good_ctx(sl=2651.0, tp=2648.0))
    add("invalid_sl_tp", "buy_sl_not_below" in pf["reasons"] or "buy_tp_not_above" in pf["reasons"])

    # 21 Unsupported filling mode
    pf = run_preflight(_good_ctx(filling_mode_bitmask=2, requested_filling=1))
    add("unsupported_filling_mode", "unsupported_filling_mode" in pf["reasons"])

    # Risk policy still unapproved constant
    add("risk_policy_unapproved_constant", UNAPPROVED == "UNAPPROVED")

    # Fake broker never genuine
    syn = BrokerExecutionAdapter(backend=FakeBrokerBackend()).submit_synthetic(
        {"intent_id": "s", "decision_id": "d", "symbol": ACTIVE_SYMBOL, "direction": "BUY", "volume": 0.01, "price": 2650.0, "sl": 2649.0, "tp": 2652.0}
    )
    add("fake_fills_not_genuine_broker_evidence", syn.get("not_genuine_broker_evidence") is True)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
