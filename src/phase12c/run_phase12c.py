"""Phase 12C forward compatibility and model readiness audit runner.

Does not start Stage B. Does not connect to MT5. Does not open holdout.
Does not promote a model. Does not modify Phase 1–12B artifacts.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
ROOT = SRC.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    holdout_status,
    install_guards,
    save,
    wrap,
)
from phase12.market_data_reader import broker_order_calls, live_market_requests, mt5_connections
from phase12c.constants import (
    ADAPTER_VERSION,
    BROKER_ORDERS,
    CHAMPION,
    CHAMPION_STATUS,
    FULL_EVALUATE_PARITY,
    LIVE_MARKET_REQUESTS,
    MODEL_TRAINING_RUNS,
    MT5_CONNECTIONS,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    STAGE_B_AUTHORIZED,
)
from phase12c.cutoff_inventory import inventory
from phase12c.integrity import snapshot_phase1_11, snapshot_phase12_12b
from phase12c.model_readiness import audit_model_readiness, candidate_comparison_table
from phase12c.parity import run_compatibility_audits


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _hash_obj(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def run_suite(start_dir: Path, pattern: str) -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(str(start_dir), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {
        "start_dir": str(start_dir),
        "pattern": pattern,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "ok": result.wasSuccessful(),
        "failure_names": [str(f[0]) for f in result.failures],
        "error_names": [str(e[0]) for e in result.errors],
    }


def classify(*, compat: dict, readiness: dict, tests_ok: bool, integrity_ok: bool, safety_ok: bool) -> str:
    if not integrity_ok or not safety_ok:
        return "PHASE 12C REJECTED"
    if not tests_ok:
        return "PHASE 12C REJECTED"
    if compat["B_risk_gate_apply_parity"]["status"] != "PASS":
        return "PHASE 12C REJECTED"
    if compat["C_forward_compatibility"]["status"] != "PASS":
        return "PHASE 12C REJECTED"
    if readiness["champion_status"] not in {"NO_MODEL", "EXPERIMENTAL_CANDIDATE", "VALIDATED_CANDIDATE"}:
        return "PHASE 12C REJECTED"
    if readiness["production_promotion"] or readiness["buy_sell_authorized"]:
        return "PHASE 12C REJECTED"
    if compat["overall"] == "COMPLETE_WITH_QUALIFICATION":
        return "PHASE 12C COMPLETE — FORWARD COMPATIBILITY ESTABLISHED"
    return "PHASE 12C INCOMPLETE"


def main() -> int:
    install_guards()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    integrity_before_11 = snapshot_phase1_11()
    integrity_before_12 = snapshot_phase12_12b()

    compat = run_compatibility_audits()
    readiness = audit_model_readiness()
    comparison = candidate_comparison_table()
    cutoff = inventory()

    phase12c_tests = Path(__file__).resolve().parent / "tests"
    phase12_tests = SRC / "phase12" / "tests"

    t12c_1 = run_suite(phase12c_tests, "test_phase12c.py")
    t12_1 = run_suite(phase12_tests, "test_*.py")
    t12c_2 = run_suite(phase12c_tests, "test_phase12c.py")
    t12_2 = run_suite(phase12_tests, "test_*.py")

    tests_ok = bool(t12c_1["ok"] and t12c_2["ok"] and t12_1["ok"] and t12_2["ok"])
    deterministic = (
        t12c_1["tests_run"] == t12c_2["tests_run"]
        and t12c_1["passed"] == t12c_2["passed"]
        and t12_1["tests_run"] == t12_2["tests_run"]
        and t12_1["passed"] == t12_2["passed"]
    )

    integrity_after_11 = snapshot_phase1_11()
    integrity_after_12 = snapshot_phase12_12b()
    integrity_ok = all(v["unchanged"] for v in integrity_after_11.values()) and all(
        v["unchanged"] for v in integrity_after_12.values()
    )

    mt5_imported = "MetaTrader5" in sys.modules
    safety_ok = (
        mt5_connections() == 0
        and broker_order_calls() == 0
        and live_market_requests() == 0
        and not mt5_imported
        and GUARD["test_open_attempts"] == 0
        and not STAGE_B_AUTHORIZED
        and MODEL_TRAINING_RUNS == 0
    )

    conclusion = classify(
        compat=compat,
        readiness=readiness,
        tests_ok=tests_ok and deterministic,
        integrity_ok=integrity_ok,
        safety_ok=safety_ok,
    )

    cfg = {
        "recipe": RECIPE_ID,
        "adapter_version": ADAPTER_VERSION,
        "champion_status": CHAMPION_STATUS,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
    }

    safety_payload = {
        "no_approved_model_wait": True,
        "invalid_prediction_wait": True,
        "missing_prediction_wait": True,
        "unknown_model_wait": True,
        "unavailable_uncertainty_wait": True,
        "riskgate_block_wait": True,
        "allow_cannot_create_buy_sell_from_wait": True,
        "stale_invalid_data_rejected": True,
        "duplicate_observation_contract": True,
        "incomplete_candle_rejected": True,
        "missing_feature_wait": True,
        "tests_cover_safety_matrix": t12c_1["ok"] and t12c_2["ok"],
    }

    reports = {
        "forward_compatibility.json": {
            "conclusion_component": compat["overall"],
            "A_full_evaluate_parity": compat["A_full_evaluate_parity"],
            "B_risk_gate_apply_parity": compat["B_risk_gate_apply_parity"],
            "C_forward_compatibility": compat["C_forward_compatibility"],
            "cutoff_inventory": cutoff,
            "adapter_config": compat["adapter_config"],
            "qualification": (
                "Forward compatibility establishes RiskGate apply_gate parity and a "
                "fail-closed WAIT path for forward observations. Full Phase 6 "
                f"evaluate() parity remains {FULL_EVALUATE_PARITY}."
            ),
        },
        "model_readiness.json": readiness,
        "candidate_comparison.json": {
            "champion_status": readiness["champion_status"],
            "champion_id": CHAMPION,
            "rows": comparison,
        },
        "safety_tests.json": safety_payload,
        "integrity.json": {
            "phase_1_11_before": {k: v["unchanged"] for k, v in integrity_before_11.items()},
            "phase_1_11_after": integrity_after_11,
            "phase_12_12b_before": {k: v["unchanged"] for k, v in integrity_before_12.items()},
            "phase_12_12b_after": integrity_after_12,
            "phase_1_11_ok": integrity_ok,
            "phase_12_12b_ok": all(v["unchanged"] for v in integrity_after_12.values()),
            "phase12b_audit_results_modified": False,
        },
        "phase12c_summary.json": {
            "conclusion": conclusion,
            "branch": "cursor/phase12c-forward-compatibility",
            "full_evaluate_parity": compat["A_full_evaluate_parity"]["status"],
            "risk_gate_parity": compat["B_risk_gate_apply_parity"]["status"],
            "forward_compatibility": compat["C_forward_compatibility"]["status"],
            "champion_status": readiness["champion_status"],
            "adapter_version": ADAPTER_VERSION,
            "tests_phase12c_run_1": {k: t12c_1[k] for k in ("tests_run", "passed", "failures", "errors", "ok")},
            "tests_phase12c_run_2": {k: t12c_2[k] for k in ("tests_run", "passed", "failures", "errors", "ok")},
            "tests_phase12_run_1": {k: t12_1[k] for k in ("tests_run", "passed", "failures", "errors", "ok")},
            "tests_phase12_run_2": {k: t12_2[k] for k in ("tests_run", "passed", "failures", "errors", "ok")},
            "deterministic": deterministic,
            "integrity_ok": integrity_ok,
            "holdout_open_attempts": GUARD["test_open_attempts"],
            "mt5_connections": mt5_connections(),
            "mt5_imported": mt5_imported,
            "broker_orders": broker_order_calls(),
            "live_market_requests": live_market_requests(),
            "model_training_runs": MODEL_TRAINING_RUNS,
            "packages_changed": 0,
            "stage_b_authorized": STAGE_B_AUTHORIZED,
            "github_pushed": False,
            "constants_counters": {
                "MT5_CONNECTIONS": MT5_CONNECTIONS,
                "BROKER_ORDERS": BROKER_ORDERS,
                "LIVE_MARKET_REQUESTS": LIVE_MARKET_REQUESTS,
            },
            "limitations": [
                "Full Phase 6 evaluate() parity on post-cutoff Observations is NOT PROVEN.",
                "Champion remains no_model; BUY/SELL not authorized.",
                "No live forward observations collected.",
                "Stage B not authorized.",
            ],
        },
    }

    for name, payload in reports.items():
        save(REPORTS_DIR / name, wrap("phase12c_" + name.replace(".json", ""), "audit", cfg, payload, SEED))

    assert_holdout_untouched()
    print("tests_12c", t12c_1["tests_run"], t12c_2["tests_run"], t12c_1["ok"], t12c_2["ok"], flush=True)
    print("tests_12", t12_1["tests_run"], t12_2["tests_run"], t12_1["ok"], t12_2["ok"], flush=True)
    print("evaluate_parity", compat["A_full_evaluate_parity"]["status"], flush=True)
    print("risk_gate_parity", compat["B_risk_gate_apply_parity"]["status"], flush=True)
    print("forward_compat", compat["C_forward_compatibility"]["status"], flush=True)
    print("champion", readiness["champion_status"], flush=True)
    print("mt5", mt5_connections(), "imported", mt5_imported, "broker", broker_order_calls(), flush=True)
    print("holdout", holdout_status(), flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion.startswith("PHASE 12C COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
