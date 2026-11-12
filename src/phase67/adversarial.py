"""Adversarial checks for Phase 67."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase65.consumption import build_consumption_registry
from phase67.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    canonical_json_sha256,
)
from phase67.exploratory import consumed_days
from phase67.integrity import audit_integrity
from phase67.security import security_audit
from phase67.tick_api_audit import audit_tick_api_approval


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    tick = audit_tick_api_approval()
    add("tick_apis_not_approved", tick["any_tick_api_approved"] is False)
    add("phase67_does_not_use_ticks", tick["phase67_uses_ticks"] is False)

    cons = build_consumption_registry()
    days = consumed_days()
    add("no_holdout_in_exploratory_days", not set(days) & set(cons["phase58_holdout_sealed"]))
    add("holdout_still_sealed", cons["phase58_holdout_opened"] is False)

    # Lightweight exploratory smoke (may take time — call full only if days small enough;
    # for adversarial, just check imports and day list non-empty)
    add("consumed_days_nonempty", len(days) >= 40)

    sec = security_audit()
    add("security_pass", sec["pass"])
    integ = audit_integrity()
    add("integrity_pass", integ["checks_pass"])
    add("champion_NO_MODEL", CHAMPION_STATUS == "NO_MODEL")
    add("production_WAIT", PRODUCTION_FINAL_ACTION == "WAIT")
    add("order_send_prohibited", ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API)
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
