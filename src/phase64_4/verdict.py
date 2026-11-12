"""Phase64.4 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(bundle: dict[str, Any]) -> tuple[str, str]:
    arch = bundle.get("architecture") or {}
    schemas = bundle.get("schemas") or {}
    fsm = bundle.get("state_machine") or {}
    symbol = bundle.get("symbol") or {}
    risk = bundle.get("risk") or {}
    econ = bundle.get("economics") or {}
    recovery = bundle.get("recovery") or {}
    auth = bundle.get("authorization") or {}
    adv = bundle.get("adversarial") or {}
    integ = bundle.get("integrity") or {}
    tests = bundle.get("unit_tests") or {}

    core = [
        arch.get("pass"),
        schemas.get("pass"),
        fsm.get("pass"),
        symbol.get("pass"),
        risk.get("pass"),
        econ.get("pass"),
        recovery.get("pass"),
        auth.get("submission_authorized") is False,
        auth.get("broker_order_send_permitted") is False,
        adv.get("suite_pass"),
        integ.get("checks_pass"),
        tests.get("ok"),
    ]
    if all(core):
        return (
            "BROKER_EXECUTION_DESIGN_VALIDATED",
            "Design + authorization gate validated; submission remains blocked; no order_send",
        )
    if any(core):
        return (
            "BROKER_EXECUTION_DESIGN_PARTIAL",
            "Some design/auth checks incomplete or failed",
        )
    return "BROKER_EXECUTION_DESIGN_FAILED", "Critical design or safety checks failed"
