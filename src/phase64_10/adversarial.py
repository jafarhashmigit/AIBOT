"""Adversarial / required tests for Phase 64.10 economics & risk."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_10.commission import investigate_commission
from phase64_10.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    ORDER_SEND,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    UNAPPROVED,
    UNKNOWN,
    VERIFIED,
    canonical_json_sha256,
)
from phase64_10.cost_model import build_cost_model
from phase64_10.margin_model import build_margin_model, leverage_margin_estimate
from phase64_10.risk_policy import build_demo_risk_policy, evaluate_policy_gates
from phase64_10.sessions import build_session_model, rollover_window_check, session_boundary_check
from phase64_10.stress import build_stress_framework
from phase64_10.swap_analysis import analyze_swap_conflict


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    # commission unknown
    c0 = investigate_commission(n_trade_deals=0)
    add("commission_unknown", c0["actual_commission_observed"] == UNKNOWN and c0["actual_commission_status"] == UNKNOWN)

    # commission verified requires trade deals — currently cannot be VERIFIED
    add(
        "commission_verified",
        c0["actual_commission_status"] != VERIFIED and c0["blocks_deterministic_execution_cost"] is True,
    )

    # published vs account-specific not merged
    add(
        "published_vs_account_specific_commission",
        c0["merged"] is False and c0["published_commission"]["status"] == UNKNOWN,
    )

    # margin estimate vs broker observation
    m = build_margin_model()
    add(
        "margin_estimate_vs_broker_observation",
        m["leverage_estimate"]["kind"] == "CALCULATED_ESTIMATE"
        and m["broker_observed"]["kind"] == "BROKER_OBSERVED"
        and m["leverage_estimate"]["usable_as_broker_fact"] is False,
    )

    # missing margin data
    add("missing_margin_data", m["MARGIN_MODEL"] == "INCOMPLETE")

    # session unknown
    sess = build_session_model()
    add("session_unknown", sess["programmatic_status"] == UNKNOWN and sess["conservative_execution_block_required"])

    # session boundary
    sb = session_boundary_check(sessions=sess)
    add("session_boundary", sb["allowed"] is False)

    # rollover window
    rw = rollover_window_check(weekday_utc=2)
    add("rollover_window", rw["allowed"] is False and rw["triple_swap_weekday_mt5"] == 3)

    # swap conflict
    sw = analyze_swap_conflict()
    add(
        "swap_conflict",
        sw["observations"][0]["swap_long"] == SWAP_LONG_PHASE63
        and sw["observations"][1]["swap_long"] == SWAP_LONG_PHASE64_7
        and sw["overwrite"] is False
        and sw["status_for_execution"] == "UNKNOWN_FOR_EXECUTION",
    )

    policy = build_demo_risk_policy()
    # spread guard
    g = evaluate_policy_gates(policy, context={"spread_explosion": True})
    add("spread_guard", "spread_guard" in g["reasons"] and not g["allowed"])

    # stale tick
    g = evaluate_policy_gates(policy, context={"stale_tick": True})
    add("stale_tick", "stale_data_guard" in g["reasons"])

    # insufficient free margin
    g = evaluate_policy_gates(policy, context={"insufficient_free_margin": True})
    add("insufficient_free_margin", "margin_safety" in g["reasons"])

    # excessive aggregate risk
    g = evaluate_policy_gates(policy, context={"excessive_aggregate_risk": True})
    add("excessive_aggregate_risk", "aggregate_risk" in g["reasons"])

    # daily loss limit
    g = evaluate_policy_gates(policy, context={"daily_loss_breached": True})
    add("daily_loss_limit", "daily_loss_limit" in g["reasons"])

    # drawdown limit
    g = evaluate_policy_gates(policy, context={"drawdown_breached": True})
    add("drawdown_limit", "drawdown_limit" in g["reasons"])

    # consecutive-loss lockout
    g = evaluate_policy_gates(policy, context={"consecutive_loss_lockout": True})
    add("consecutive_loss_lockout", "consecutive_loss_circuit_breaker" in g["reasons"])

    # combined cost stress
    stress = build_stress_framework(expected_edge_usd=10.0)
    add(
        "combined_cost_stress",
        stress["scenarios"]["combined_stress"]["usd"] > stress["scenarios"]["baseline"]["total_known_usd"]
        and stress["never_manufacture_edge"] is True,
    )

    # unknown cost blocking
    g = evaluate_policy_gates(policy, context={"unknown_cost": True})
    add("unknown_cost_blocking", "unknown_cost_blocking" in g["reasons"])

    # risk-policy approval blocking execution
    add(
        "risk_policy_approval_blocking_execution",
        policy["approval_status"] == UNAPPROVED and policy["authorizes_execution"] is False,
    )

    # cost model never zeroes unknown
    cm = build_cost_model(spread_points=240, spread_status=VERIFIED)
    add(
        "unknown_not_collapsed_to_zero",
        cm["never_collapse_unknown_to_zero"]
        and cm["components"][2]["value"] == UNKNOWN  # commission
        and cm["deterministic_execution_cost_complete"] is False,
    )

    # leverage estimate exists
    lev = leverage_margin_estimate(price=2650.0, volume=0.01)
    add("leverage_margin_estimate", lev["usable_as_broker_fact"] is False and lev["margin_estimate_usd"] > 0)

    # no-order invariants
    add("order_send_prohibited", "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED")
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False)
    add("execution_not_authorized", BROKER_EXECUTION_AUTHORIZED is False)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
