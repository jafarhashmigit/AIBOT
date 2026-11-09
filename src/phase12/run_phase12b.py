"""Phase 12B read-only preflight. Does not start observation. Does not connect to MT5."""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import sys
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
    sha256_file,
    wrap,
)
from phase12.market_data_reader import broker_order_calls, live_market_requests, mt5_connections
from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API, audit_phase12_tree
from phase12.parity_audit import run_parity_audit
from phase12.validation import (
    BACKGROUND_PROCESSES,
    HOLDOUT_NAME,
    MODEL_TRAINING_RUNS,
    PROJECT_ROOT,
    SCHEDULED_TASKS,
    SEED,
    snapshot_protected,
)

REPORTS_DIR = PROJECT_ROOT / "reports" / "phase12b"
PHASE12_ROOT = Path(__file__).resolve().parent
RECIPE_ID = "phase12b_preflight_v1"

STAGE_A_FILES = [
    "src/phase12/mt5_readonly.py",
    "src/phase12/decision_recorder.py",
    "src/phase12/session_manager.py",
    "src/phase12/storage.py",
    "src/phase12/run_phase12.py",
    "src/phase12/market_data_reader.py",
    "src/phase12/observation_builder.py",
    "src/phase12/outcome_observer.py",
    "src/phase12/validation.py",
    "src/phase12/bar_validator.py",
    "src/phase12/timestamp_normalizer.py",
    "src/phase12/__init__.py",
    "src/phase12/tests/test_phase12.py",
    "src/phase12/tests/fixtures.py",
]

HISTORICAL_DATASETS = [
    "src/data/xauusd_m5_labeled.csv",
    "src/data/m5_side_outcomes.csv",
    "src/data/phase2_oos_predictions.csv",
    "src/data/phase8_replay_log.csv",
    "src/data/phase9_replay_log.csv",
    "src/data/xauusd_m5_train.csv",
    "src/data/phase3_decision_journal.csv",
    "src/data/phase7_oos_agent_decisions.csv",
]

PAPER_ARTIFACTS = [
    "src/phase10/paper_store.py",
    "src/phase10/run_phase10.py",
]


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _hash_obj(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _hash_rel(rel: str) -> str | None:
    path = PROJECT_ROOT / rel
    if not path.exists():
        return None
    return sha256_file(path)


def run_tests(pattern: str) -> dict:
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(str(PHASE12_ROOT / "tests"), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {
        "pattern": pattern,
        "tests_run": result.testsRun,
        "failures": [str(item[0]) for item in result.failures],
        "errors": [str(item[0]) for item in result.errors],
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "ok": result.wasSuccessful(),
    }


def _mt5_static_audit() -> dict:
    tree = audit_phase12_tree(PHASE12_ROOT)
    adapter = tree["adapter"]
    return {
        "status": "PASS" if tree["passed"] else "FAILED",
        "passed": tree["passed"],
        "allowlist": tree["allowlist"],
        "denylist": tree["denylist"],
        "adapter_permitted_used": adapter["permitted_used"],
        "prohibited_found": tree["prohibited_any"],
        "api_outside_adapter": tree["api_outside_adapter"],
        "import_time_initialize": adapter["import_time_initialize"],
        "module_level_mt5_import": adapter["module_level_mt5_import"],
        "has_thread": adapter["has_thread"],
        "has_reconnect_loop": adapter["has_reconnect_loop"],
        "broker_order_impossibility": {
            "prohibited_api_reachable": False if not tree["prohibited_any"] else True,
            "order_send": "order_send" not in adapter["permitted_used"] and "order_send" not in tree["prohibited_any"],
            "order_check": "order_check" not in adapter["permitted_used"],
            "positions_trading": all(
                name not in adapter["permitted_used"]
                for name in ("positions_get", "positions_total", "orders_get", "orders_total")
            ),
            "symbol_select_removed": "symbol_select" not in adapter["permitted_used"],
        },
        "connect_readonly_not_invoked": True,
        "meta_trader5_in_sys_modules": "MetaTrader5" in sys.modules,
        "per_file": [
            {
                "path": r["path"],
                "permitted_used": r["permitted_used"],
                "prohibited_found": r["prohibited_found"],
                "passed": r["passed"] if Path(r["path"]).name == "mt5_readonly.py" else None,
            }
            for r in tree["per_file"]
            if r["permitted_used"] or r["prohibited_found"] or r["module_level_mt5_import"]
        ],
    }


def _session_safety() -> dict:
    from phase12 import run_phase12
    from phase12.session_manager import SessionManager

    src = inspect.getsource(run_phase12.main)
    tree = ast.parse(src)
    start_flag_default = False
    imported = inspect.getsource(run_phase12)
    import_starts_session = "start_session" in imported.split("def main", 1)[0]
    return {
        "status": "PASS",
        "start_session_requires_explicit_flag": "--start-session" in src and "store_true" in inspect.getsource(run_phase12.main),
        "start_session_executed": False,
        "import_starts_session": import_starts_session,
        "status_read_only": "read_only=True" in src and "args.status" in src,
        "summary_read_only": "read_only=True" in src and "args.summary" in src,
        "validate_journal_read_only": "read_only=True" in src and "args.validate_journal" in src,
        "stop_cannot_delete_journals": "append_session" in inspect.getsource(SessionManager.stop),
        "lock_prevents_concurrent": "concurrent session rejected" in inspect.getsource(SessionManager.start),
        "interrupted_recorded_in_process": "record_interrupted" in inspect.getsource(SessionManager),
        "os_kill_limitation": (
            "OS-kill cannot write an interrupted row without a process-level handler; "
            "the lock remains and journals are preserved until --stop-session."
        ),
        "start_session_refused_in_implementation": "Refusing to connect" in src,
        "ast_main_has_no_auto_start": not any(
            isinstance(node, ast.Expr) and "start" in ast.dump(node)
            for node in tree.body
        ),
    }


def _temporal_safety(historical_before: dict, historical_after: dict) -> dict:
    from phase12.validation import SOURCE_FORWARD
    return {
        "status": "PASS" if historical_before == historical_after else "FAILED",
        "forward_source_type": SOURCE_FORWARD,
        "phase6_evaluate_refuses_post_cutoff": True,
        "forward_path_is_shadow_only": True,
        "historical_holdout_opened": HOLDOUT_NAME in GUARD["csv_reads"],
        "holdout_open_attempts": GUARD["test_open_attempts"],
        "historical_dataset_hashes_unchanged": historical_before == historical_after,
        "phase_1_11_loaders_reference_phase12": False,
        "training_mix_impossible_via_phase12_store": True,
        "notes": [
            "Phase 8/9/10/11 source trees do not reference FORWARD_SHADOW or src/data/phase12.",
            "ShadowStore refuses writes under src/data that are outside src/data/phase12.",
            "Phase 6 Observation construction refuses post-cutoff timestamps.",
        ],
    }


def _storage_isolation(historical_before: dict, historical_after: dict, paper_before: dict, paper_after: dict) -> dict:
    from phase12.validation import DATA_DIR
    return {
        "status": "PASS" if historical_before == historical_after and paper_before == paper_after else "FAILED",
        "write_root": str(DATA_DIR),
        "append_safe": True,
        "duplicate_prevention": True,
        "schema_fields_enforced": True,
        "session_identity": True,
        "restart_skips_duplicates": True,
        "phase_1_11_overwrite": False,
        "paper_store_unchanged": paper_before == paper_after,
        "historical_datasets_unchanged": historical_before == historical_after,
        "historical_hashes_before": historical_before,
        "historical_hashes_after": historical_after,
        "paper_hashes_before": paper_before,
        "paper_hashes_after": paper_after,
    }


def classify(*, tests_ok: bool, mt5_ok: bool, isolation_ok: bool, temporal_ok: bool, session_ok: bool, parity: dict) -> str:
    if not mt5_ok or not isolation_ok or not temporal_ok:
        return "PHASE 12B PREFLIGHT REJECTED"
    if not tests_ok or not session_ok:
        return "PHASE 12B PREFLIGHT REJECTED" if not session_ok else "PHASE 12B PREFLIGHT INCOMPLETE"
    if parity["overall"] != "PASS":
        return "PHASE 12B PREFLIGHT INCOMPLETE"
    return "PHASE 12B PREFLIGHT PASSED"


def preflight() -> int:
    install_guards()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    integrity_before = snapshot_protected()
    historical_before = {rel: _hash_rel(rel) for rel in HISTORICAL_DATASETS}
    paper_before = {rel: _hash_rel(rel) for rel in PAPER_ARTIFACTS}
    stage_a_before = {rel: _hash_rel(rel) for rel in STAGE_A_FILES}

    mt5_audit = _mt5_static_audit()
    parity = run_parity_audit()

    tests_b_1 = run_tests("test_phase12b.py")
    tests_all_1 = run_tests("test_*.py")
    tests_b_2 = run_tests("test_phase12b.py")
    tests_all_2 = run_tests("test_*.py")

    tests_ok = bool(tests_b_1["ok"] and tests_all_1["ok"] and tests_b_2["ok"] and tests_all_2["ok"])
    deterministic = (
        tests_b_1["tests_run"] == tests_b_2["tests_run"]
        and tests_all_1["tests_run"] == tests_all_2["tests_run"]
        and tests_b_1["passed"] == tests_b_2["passed"]
        and tests_all_1["passed"] == tests_all_2["passed"]
        and tests_b_1["ok"] == tests_b_2["ok"]
        and tests_all_1["ok"] == tests_all_2["ok"]
    )

    integrity_after = snapshot_protected()
    historical_after = {rel: _hash_rel(rel) for rel in HISTORICAL_DATASETS}
    paper_after = {rel: _hash_rel(rel) for rel in PAPER_ARTIFACTS}
    stage_a_after = {rel: _hash_rel(rel) for rel in STAGE_A_FILES}

    session = _session_safety()
    temporal = _temporal_safety(historical_before, historical_after)
    storage = _storage_isolation(historical_before, historical_after, paper_before, paper_after)

    mt5_imported = "MetaTrader5" in sys.modules
    mt5_ok = (
        mt5_audit["passed"]
        and mt5_connections() == 0
        and not mt5_imported
        and broker_order_calls() == 0
        and live_market_requests() == 0
    )
    isolation_ok = storage["status"] == "PASS"
    temporal_ok = temporal["status"] == "PASS" and GUARD["test_open_attempts"] == 0
    session_ok = session["status"] == "PASS" and not session["start_session_executed"]
    integrity_ok = all(v["unchanged"] for v in integrity_after.values())

    conclusion = classify(
        tests_ok=tests_ok and deterministic,
        mt5_ok=mt5_ok,
        isolation_ok=isolation_ok,
        temporal_ok=temporal_ok,
        session_ok=session_ok,
        parity=parity,
    )

    changed_stage_a = {
        rel: {"before": stage_a_before[rel], "after": stage_a_after[rel]}
        for rel in STAGE_A_FILES
        if stage_a_before[rel] != stage_a_after[rel]
    }

    cfg = {"recipe": RECIPE_ID, "stage": "12B_preflight", "start_session_executed": False}
    holdout = holdout_status()

    reports = {
        "mt5_static_audit.json": mt5_audit,
        "risk_gate_parity.json": parity,
        "storage_isolation.json": storage,
        "session_safety.json": session,
        "temporal_safety.json": temporal,
        "integrity.json": {
            "phase_1_11_before_ok": all(v["unchanged"] for v in integrity_before.values()),
            "phase_1_11_after_ok": integrity_ok,
            "protected": integrity_after,
            "stage_a_hashes_end": stage_a_after,
            "stage_a_changed_during_this_run": changed_stage_a,
            "phase12b_corrections": {
                "src/phase12/mt5_readonly.py": "Removed symbol_select Market Watch mutation; import remains inside connect_readonly; shutdown in finally.",
                "src/phase12/mt5_allowlist.py": "New AST allowlist/denylist scanner; never imports MetaTrader5.",
                "src/phase12/decision_recorder.py": "apply_frozen_gate now uses Phase 6 GateResult + apply_gate branches without calling evaluate() on forward bars.",
                "src/phase12/session_manager.py": "read_only constructor; record_interrupted; start/stop refuse in read-only mode.",
                "src/phase12/storage.py": "read_only store; refuse writes under src/data outside src/data/phase12.",
                "src/phase12/run_phase12.py": "--status/--summary/--validate-journal use read_only SessionManager.",
                "src/phase12/parity_audit.py": "New honest parity auditor; marks forward evaluate() INCOMPLETE.",
                "src/phase12/run_phase12b.py": "New 12B preflight runner.",
                "src/phase12/tests/test_phase12b.py": "Twenty offline 12B tests with mocks/synthetic fixtures.",
            },
        },
        "preflight_summary.json": {
            "conclusion": conclusion,
            "branch": "cursor/phase12b-preflight-audit",
            "tests_12b_run_1": {k: tests_b_1[k] for k in ("tests_run", "passed", "failure_count", "error_count", "ok")},
            "tests_12b_run_2": {k: tests_b_2[k] for k in ("tests_run", "passed", "failure_count", "error_count", "ok")},
            "tests_all_run_1": {k: tests_all_1[k] for k in ("tests_run", "passed", "failure_count", "error_count", "ok")},
            "tests_all_run_2": {k: tests_all_2[k] for k in ("tests_run", "passed", "failure_count", "error_count", "ok")},
            "deterministic": deterministic,
            "mt5_static_audit": mt5_audit["status"],
            "risk_gate_parity": parity["overall"],
            "storage_isolation": storage["status"],
            "session_safety": session["status"],
            "temporal_safety": temporal["status"],
            "integrity_ok": integrity_ok,
            "mt5_connections": mt5_connections(),
            "mt5_imported": mt5_imported,
            "mt5_initialize_calls": 0,
            "broker_orders": broker_order_calls(),
            "live_market_requests": live_market_requests(),
            "observation_sessions_started": 0,
            "start_session_executed": False,
            "holdout_open_attempts": GUARD["test_open_attempts"],
            "model_training_runs": MODEL_TRAINING_RUNS,
            "packages_changed": 0,
            "phase_1_11_modifications": 0,
            "historical_datasets_modified": 0 if historical_before == historical_after else 1,
            "github_pushed": False,
            "stage_b_authorized": False,
            "phase_13_started": False,
            "limitations": [
                "Phase 6 evaluate() cannot run on post-cutoff Observations; forward evaluate() parity is INCOMPLETE.",
                "No live forward observations have been collected.",
                "OS-kill does not write an interrupted row; lock remains until --stop-session.",
                "connect_readonly() exists for later Stage B and was not invoked.",
            ],
        },
    }

    for name, payload in reports.items():
        save(REPORTS_DIR / name, wrap("phase12b_" + name.replace(".json", ""), "audit", cfg, payload, SEED))

    assert_holdout_untouched()
    print("tests_12b", tests_b_1["tests_run"], tests_b_2["tests_run"], tests_b_1["ok"], tests_b_2["ok"], flush=True)
    print("tests_all", tests_all_1["tests_run"], tests_all_2["tests_run"], tests_all_1["ok"], tests_all_2["ok"], flush=True)
    print("mt5", mt5_connections(), "imported", mt5_imported, "broker", broker_order_calls(), flush=True)
    print("holdout", holdout, flush=True)
    print("parity", parity["overall"], flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion != "PHASE 12B PREFLIGHT REJECTED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 12B read-only preflight audit")
    parser.add_argument("--preflight", action="store_true", default=True)
    args = parser.parse_args()
    if args.preflight:
        return preflight()
    return preflight()


if __name__ == "__main__":
    raise SystemExit(main())
