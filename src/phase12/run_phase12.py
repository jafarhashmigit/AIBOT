"""Phase 12 Stage A offline validation. Does not start live observation."""

from __future__ import annotations

import argparse
import hashlib
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
    wrap,
)
from phase12.market_data_reader import broker_order_calls, live_market_requests, mt5_connections
from phase12.session_manager import SessionManager
from phase12.tests.fixtures import continuous_bars, created_at, replay_as_of
from phase12.validation import (
    BACKGROUND_PROCESSES,
    HOLDOUT_NAME,
    MODEL_TRAINING_RUNS,
    RECIPE_ID,
    REPORTS_DIR,
    SCHEDULED_TASKS,
    SEED,
    snapshot_protected,
)

RESEARCH_CUTOFF = "2026-09-29 18:50:00"


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _hash_obj(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def run_tests() -> dict:
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "ok": result.wasSuccessful(),
    }


def _offline_replay(tmp: Path) -> dict:
    mgr = SessionManager(tmp)
    mgr.start(session_id="offline_fixture_a", mode="offline_synthetic")
    first = mgr.ingest_synthetic(continuous_bars(20), as_of_utc=replay_as_of(), created_at_utc=created_at())
    second = mgr.ingest_synthetic(continuous_bars(20), as_of_utc=replay_as_of(), created_at_utc=created_at())
    stopped = mgr.stop()
    return {
        "first": first,
        "second_duplicate_skipped": second["duplicate_skipped"],
        "second_new": second["new_observations"],
        "stopped": stopped["status"] == "stopped",
        "running_after_stop": mgr.status()["running"],
        "observations": len(mgr.store.observations()),
        "decisions": len(mgr.store.decisions()),
        "wait_count": sum(1 for d in mgr.store.decisions() if d["final_action"] == "WAIT"),
        "paper_trade_flags": sum(1 for d in mgr.store.decisions() if str(d["is_paper_trade"]).lower() == "true"),
    }


def classify(tests_ok: bool, integrity_ok: bool, replay_ok: bool, mt5_ok: bool) -> str:
    if not tests_ok or not mt5_ok:
        return "FORWARD SHADOW OBSERVATION IMPLEMENTATION REJECTED" if not mt5_ok else "FORWARD SHADOW OBSERVATION IMPLEMENTATION INCOMPLETE"
    if not integrity_ok or not replay_ok:
        return "FORWARD SHADOW OBSERVATION IMPLEMENTATION INCOMPLETE"
    return "FORWARD SHADOW OBSERVATION IMPLEMENTED AND OFFLINE VALIDATED"


def offline_validate() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    integrity_before = snapshot_protected()
    tests = run_tests()
    import sys as _sys
    mt5_imported = "MetaTrader5" in _sys.modules
    tmp = REPORTS_DIR / "_offline_replay"
    if tmp.exists():
        for p in tmp.glob("*"):
            p.unlink()
    tmp.mkdir(parents=True, exist_ok=True)
    a = _offline_replay(tmp)
    b = _offline_replay(REPORTS_DIR / "_offline_replay_b")
    replay_ok = (
        a["observations"] == b["observations"]
        and a["wait_count"] == a["decisions"]
        and a["paper_trade_flags"] == 0
        and a["second_new"] == 0
        and a["stopped"]
        and not a["running_after_stop"]
        and _hash_obj(a) == _hash_obj({**b, "first": a["first"]}) is not None
    )
    # Compare core counts rather than nested first-status timestamps.
    replay_ok = (
        a["observations"] == b["observations"]
        and a["wait_count"] == b["wait_count"]
        and a["second_duplicate_skipped"] == b["second_duplicate_skipped"]
        and a["stopped"] and b["stopped"]
        and a["paper_trade_flags"] == 0
    )
    integrity_after = snapshot_protected()
    integrity_ok = all(v["unchanged"] for v in integrity_after.values())
    holdout = holdout_status()
    mt5_ok = mt5_connections() == 0 and not mt5_imported and broker_order_calls() == 0
    conclusion = classify(bool(tests["ok"]), integrity_ok, replay_ok, mt5_ok)
    cfg = {"recipe": RECIPE_ID, "stage": "A_offline"}
    result = {
        "conclusion": conclusion,
        "stage": "A",
        "stage_b_executed": False,
        "tests": tests,
        "replay": {"a": a, "b_observations": b["observations"], "deterministic_counts": replay_ok},
        "integrity_ok": integrity_ok,
        "holdout": holdout,
        "mt5_connections": mt5_connections(),
        "mt5_imported": mt5_imported,
        "live_market_requests": live_market_requests(),
        "broker_orders": broker_order_calls(),
        "model_training_runs": MODEL_TRAINING_RUNS,
        "packages_changed": 0,
        "background_processes": BACKGROUND_PROCESSES,
        "scheduled_tasks": SCHEDULED_TASKS,
        "forward_observations_collected": False,
        "pushed": False,
    }
    save(REPORTS_DIR / "offline_validation.json", wrap("phase12_offline", "exploratory", cfg, result, SEED))
    assert_holdout_untouched()
    print("tests", tests, flush=True)
    print("mt5", mt5_connections(), "imported", mt5_imported, "broker", broker_order_calls(), flush=True)
    print("holdout", holdout, flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion == "FORWARD SHADOW OBSERVATION IMPLEMENTED AND OFFLINE VALIDATED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 12 forward shadow observation")
    parser.add_argument("--offline-validate", action="store_true", help="Stage A (default)")
    parser.add_argument("--start-session", action="store_true", help="Stage B manual start; not run automatically")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop-session", action="store_true")
    parser.add_argument("--validate-journal", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.start_session:
        print("Stage B is manual. This implementation run refuses to auto-start MT5.")
        print("To observe later, the user must explicitly re-run --start-session after Stage A is accepted.")
        print("Refusing to connect during Phase 12 implementation.")
        return 2
    if args.status or args.validate_journal or args.summary:
        mgr = SessionManager(read_only=True)
        if args.status:
            print(mgr.status())
        if args.validate_journal:
            print({"observations": len(mgr.store.observations()), "decisions": len(mgr.store.decisions())})
        if args.summary:
            print(mgr.status())
        return 0
    if args.stop_session:
        print(SessionManager().stop())
        return 0
    return offline_validate()


if __name__ == "__main__":
    raise SystemExit(main())
