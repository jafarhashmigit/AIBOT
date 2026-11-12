"""Adversarial checks."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase65.consumption import build_consumption_registry
from phase67.exploratory import consumed_days
from phase68.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    DISPLACEMENT_ATR_MULT,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    canonical_json_sha256,
)
from phase68.integrity import audit_integrity
from phase68.live_integrity import audit_live_evidence
from phase68.security import security_audit


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    cons = build_consumption_registry()
    days = consumed_days()
    add("no_holdout_in_days", not set(days) & set(cons["phase58_holdout_sealed"]))
    add("displacement_mult_fixed", DISPLACEMENT_ATR_MULT == 1.5)
    add("champion", CHAMPION_STATUS == "NO_MODEL")
    add("wait", PRODUCTION_FINAL_ACTION == "WAIT")
    add("order_send", ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API)
    add("submission_off", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    live = audit_live_evidence()
    add("backfill_separated", live["historical_init_backfill_m5"] > 0)
    add("backfill_not_as_new_flag", live["backfill_not_counted_as_new_live"] is True)
    add("newly_less_than_backfill", live["newly_observed_live_closed_m5"] < live["historical_init_backfill_m5"])
    add("no_synthetic_in_genuine", live["synthetic_fixtures"] == 0)
    add("live_integrity_verified", live["integrity_verified"] is True)
    add("no_uptime_claim", live["continuous_uptime_claimed"] is False)

    add("security", security_audit()["pass"])
    add("integrity", audit_integrity()["checks_pass"])

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
