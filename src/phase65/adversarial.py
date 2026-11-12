"""Deterministic adversarial checks for Phase 65."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase65.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    REGISTRY_PATH,
    canonical_json_sha256,
)
from phase65.consumption import build_consumption_registry
from phase65.cost_stress import cost_taxonomy
from phase65.integrity import audit_integrity
from phase65.registry import build_and_freeze_registry


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    cons = build_consumption_registry()
    add("date_event_consumption_registry", cons["sufficient_unconsumed_for_discovery"])
    add("sealed_holdout_protection", cons["phase58_holdout_opened"] is False and len(cons["phase58_holdout_sealed"]) == 10)
    add(
        "holdout_not_in_phase65_splits",
        not set(cons["phase65_discovery"] + cons["phase65_validation"]) & set(cons["phase58_holdout_sealed"]),
    )

    reg = build_and_freeze_registry(
        discovery_days=cons["phase65_discovery"],
        validation_days=cons["phase65_validation"],
    )
    add("hypothesis_preregistration", reg["preregistered"] and reg["frozen_before_evaluation"])
    add("registry_immutability", REGISTRY_PATH.is_file() and reg.get("registry_sha256"))
    add("hypothesis_versioning", all(h.get("version") == "v1" for h in reg["hypotheses"]))
    add("chronological_split_integrity", max(cons["phase65_discovery"]) < min(cons["phase65_validation"]))

    tax = cost_taxonomy()
    add("unknown_commission_handling", tax["commission"]["never_zero"] is True)
    add("unknown_swap_handling", tax["swap"]["never_zero"] is True)
    add("cost_uncertainty_propagation", tax["fully_execution_robust"] is False)

    integ = audit_integrity()
    add("champion_NO_MODEL_preservation", integ["champion"] == "NO_MODEL" == CHAMPION_STATUS)
    add("production_WAIT_preservation", integ["production"] == "WAIT" == PRODUCTION_FINAL_ACTION)
    add("no_order_security_invariant", "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED")
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    # registry freeze reload same hash
    reg2 = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    add("registry_hash_stable", reg2.get("registry_sha256") == reg.get("registry_sha256"))

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
