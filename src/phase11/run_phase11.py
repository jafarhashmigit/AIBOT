"""Phase 11: dual-source experience validation. No learner. No live trading."""

from __future__ import annotations

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
from phase10.constants import MAX_ACCESS_TIMESTAMP, RESEARCH_CUTOFF
from phase11.compatibility_audit import audit_compatibility
from phase11.future_learning_contract import future_learning_contract
from phase11.historical_audit import audit_historical
from phase11.paper_audit import audit_paper
from phase11.performance_summary import separate_summaries
from phase11.temporal_audit import audit_temporal
from phase11.validation import (
    BROKER_ORDERS,
    LIVE_MARKET_CONNECTIONS,
    MODEL_TRAINING_RUNS,
    MT5_CONNECTIONS,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    ValidationError,
    load_real_stores,
    snapshot_protected,
)


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


def _audits(state: dict) -> dict:
    as_of = state["as_of"]
    hist = audit_historical(state["historical"], as_of=as_of, skipped=state["skipped"])
    paper = audit_paper(state["paper"], as_of=as_of)
    compat = audit_compatibility(state["historical"], state["paper"])
    temporal = audit_temporal(state["historical"], state["paper"], as_of=as_of)
    perf = separate_summaries(state["historical"], state["paper"], as_of=as_of)
    contract = future_learning_contract()
    return {
        "historical": hist,
        "paper": paper,
        "compatibility": compat,
        "temporal": temporal,
        "performance": perf,
        "contract": contract,
        "max_ts": state["max_ts"],
    }


def classify(tests_ok: bool, audits_ok: bool, repro_ok: bool, integrity_ok: bool,
             fundamental_defect: bool) -> str:
    if fundamental_defect:
        return "DUAL-SOURCE EXPERIENCE VALIDATION REJECTED"
    if not tests_ok or not audits_ok or not repro_ok or not integrity_ok:
        return "DUAL-SOURCE EXPERIENCE VALIDATION INCOMPLETE"
    return "DUAL-SOURCE EXPERIENCE VALIDATION PASSED"


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    integrity_before = snapshot_protected()
    tests = run_tests()

    fundamental = False
    audits_ok = True
    try:
        print("audit run 1", flush=True)
        a_state = load_real_stores()
        a = _audits(a_state)
        print("audit run 2", flush=True)
        b_state = load_real_stores()
        b = _audits(b_state)
    except ValidationError as exc:
        fundamental = True
        audits_ok = False
        a = {"error": str(exc)}
        b = a
        a_state = {"max_ts": None, "as_of": MAX_ACCESS_TIMESTAMP}

    repro_ok = (not fundamental) and _hash_obj(a) == _hash_obj(b)
    integrity_after = snapshot_protected()
    integrity_ok = all(v["unchanged"] for v in integrity_after.values())
    holdout = holdout_status()
    conclusion = classify(bool(tests["ok"]), audits_ok, repro_ok, integrity_ok, fundamental)

    cfg = {"recipe": RECIPE_ID, "as_of": MAX_ACCESS_TIMESTAMP}
    if audits_ok:
        save(REPORTS_DIR / "historical_validation.json", wrap("phase11_historical", "exploratory", cfg, a["historical"], SEED))
        save(REPORTS_DIR / "paper_validation.json", wrap("phase11_paper", "exploratory", cfg, a["paper"], SEED))
        save(REPORTS_DIR / "source_compatibility.json", wrap("phase11_compat", "exploratory", cfg, a["compatibility"], SEED))
        save(REPORTS_DIR / "temporal_validation.json", wrap("phase11_temporal", "exploratory", cfg, a["temporal"], SEED))
        save(REPORTS_DIR / "performance_summary.json", wrap("phase11_performance", "exploratory", cfg, a["performance"], SEED))
        save(REPORTS_DIR / "future_learning_contract.json", wrap("phase11_contract", "exploratory", cfg, a["contract"], SEED))
    repro = {
        "passed": repro_ok,
        "hash_1": _hash_obj(a),
        "hash_2": _hash_obj(b),
        "seed": SEED,
        "note": "no RNG; seed recorded for convention only",
    }
    save(REPORTS_DIR / "reproducibility.json", wrap("phase11_repro", "exploratory", cfg, repro, SEED))
    payload = wrap("phase11_conclusion", "exploratory", cfg, {
        "conclusion": conclusion,
        "tests": tests,
        "audits_ok": audits_ok,
        "reproducibility": repro,
        "integrity_before_ok": all(v["unchanged"] for v in integrity_before.values()),
        "integrity_after_ok": integrity_ok,
        "holdout": holdout,
        "max_timestamp": a_state.get("max_ts") if isinstance(a_state, dict) else None,
        "mt5_connections": MT5_CONNECTIONS,
        "live_market_connections": LIVE_MARKET_CONNECTIONS,
        "broker_orders": BROKER_ORDERS,
        "model_training_runs": MODEL_TRAINING_RUNS,
        "packages_changed": 0,
        "pushed": False,
        "learner_implemented": False,
    }, SEED)
    save(REPORTS_DIR / "phase11_conclusion.json", payload)

    assert_holdout_untouched()
    print("tests", tests, flush=True)
    if audits_ok:
        print("historical", a["historical"]["record_count"], a["historical"]["buy_count"], a["historical"]["sell_count"], flush=True)
        print("paper", a["paper"]["decision_count"], a["paper"]["trade_count"], a["paper"]["completed_outcomes"], flush=True)
        print("max_ts", a_state["max_ts"], flush=True)
    print("holdout", holdout, flush=True)
    print("repro", repro_ok, "integrity", integrity_ok, flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion == "DUAL-SOURCE EXPERIENCE VALIDATION PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
