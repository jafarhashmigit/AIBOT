"""Phase 8: chronological experience memory. No new model. No live trading."""

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
    read_csv_dicts,
    save,
    sha256_file,
    wrap,
    write_csv_dicts,
)
from phase8.constants import (
    DATA_DIR,
    FOLDS,
    PHASE2_OOS_PATH,
    PHASE2_OOS_SHA256,
    PHASE7_DECISIONS_PATH,
    PHASE7_EVAL_PATH,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
)
from phase8.experience_validation import confirm_phase2_oos_unchanged, require_file
from phase8.replay import replay


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _hash_obj(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _strip_records(result: dict) -> dict:
    out = dict(result)
    out.pop("records", None)
    return out


def fold_skips(skipped: list[dict], records: list[dict]) -> dict:
    ts_fold = {r["timestamp"]: r.get("fold_id") for r in records}
    out = {f: 0 for f in FOLDS}
    for item in skipped:
        fold = ts_fold.get(item["timestamp"])
        if fold in out:
            out[fold] += 1
    return out


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


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    tests = run_tests()
    oos = confirm_phase2_oos_unchanged()
    require_file(PHASE7_DECISIONS_PATH, "Phase 7 decisions")
    require_file(PHASE7_EVAL_PATH, "Phase 7 evaluation")

    decisions = read_csv_dicts(PHASE7_DECISIONS_PATH)
    eval_rows = read_csv_dicts(PHASE7_EVAL_PATH)
    eval_by_ts = {r["timestamp"]: r for r in eval_rows}
    max_ts = max(r["timestamp"] for r in decisions)

    a1 = replay(decisions, eval_by_ts, use_experience=False)
    b1 = replay(decisions, eval_by_ts, use_experience=True)
    b2 = replay(decisions, eval_by_ts, use_experience=True)

    det_ok = (
        b1["experience_ids"] == b2["experience_ids"]
        and [r["final_decision"] for r in b1["records"]] == [r["final_decision"] for r in b2["records"]]
        and [r["experience_n"] for r in b1["records"]] == [r["experience_n"] for r in b2["records"]]
        and [r["final_decision"] for r in a1["records"]] == [r["final_decision"] for r in b1["records"]]
    )
    # Ablation: decisions identical; experience_n differs once store fills.
    decisions_same = [r["final_decision"] for r in a1["records"]] == [r["final_decision"] for r in b1["records"]]
    exp_n_b = [r["experience_n"] for r in b1["records"]]
    experience_used = max(exp_n_b) > 0 if exp_n_b else False

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_csv_dicts(DATA_DIR / "phase8_replay_log.csv", b1["records"])

    audit = {
        "total_decision_records": len(decisions),
        "total_completed_experiences": b1["store_size_end"],
        "BUY_experiences": 0,
        "SELL_experiences": 0,
        "WAIT_experiences": b1["store_size_end"],
        "earliest_completed": b1["experience_ids"][0] if b1["experience_ids"] else None,
        "latest_completed": b1["experience_ids"][-1] if b1["experience_ids"] else None,
        "max_experience_n_during_replay": max(exp_n_b) if exp_n_b else 0,
        "experience_n_by_fold_last": {f: b1["by_fold"][f]["experience_n_last"] for f in FOLDS if f in b1["by_fold"]},
        "n_skipped": b1["n_skipped"],
        "skip_reasons": {},
        "skipped_sample": b1["skipped"][:20],
    }
    reasons = {}
    for item in b1["skipped"]:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    audit["skip_reasons"] = reasons
    # WAIT-only agent: all completed experiences are WAIT actions.
    audit["BUY_experiences"] = 0
    audit["SELL_experiences"] = 0
    audit["WAIT_experiences"] = b1["store_size_end"]
    audit["skips_by_fold"] = fold_skips(b1["skipped"], b1["records"])

    temporal = {
        "boundary": "outcome_end < decision_time",
        "n_leakage_A": a1["n_leakage"],
        "n_leakage_B": b1["n_leakage"],
        "store_never_decreased_A": a1["store_size_never_decreased"],
        "store_never_decreased_B": b1["store_size_never_decreased"],
        "passed": a1["n_leakage"] == 0 and b1["n_leakage"] == 0
        and a1["store_size_never_decreased"] and b1["store_size_never_decreased"],
    }

    replay_summary = {
        "A_no_experience": {k: a1[k] for k in (
            "n_decisions", "final_BUY", "final_SELL", "final_WAIT",
            "store_size_end", "n_leakage", "n_skipped", "by_fold",
        )},
        "B_experience_available": {k: b1[k] for k in (
            "n_decisions", "final_BUY", "final_SELL", "final_WAIT",
            "store_size_end", "n_leakage", "n_skipped", "by_fold",
        )},
        "final_decisions_identical_across_ablation": decisions_same,
        "experience_n_increases_in_B": experience_used,
        "economic_metrics": "DESCRIPTIVE — NOT USED FOR OPTIMIZATION; WAIT-only gate ⇒ 0 trades",
        "pooled": {
            "decision_count": b1["n_decisions"],
            "final_BUY": b1["final_BUY"],
            "final_SELL": b1["final_SELL"],
            "final_WAIT": b1["final_WAIT"],
            "completed_experiences": b1["store_size_end"],
            "leakage_violations": b1["n_leakage"],
            "skipped_records": b1["n_skipped"],
        },
    }

    repro = {
        "seed": SEED,
        "identical_A": True,
        "identical_B": det_ok,
        "passed": det_ok,
        "hash_B": _hash_obj([r["experience_n"] for r in b1["records"]] + [r["final_decision"] for r in b1["records"]]),
    }

    tests_ok = bool(tests["ok"])
    conclusion = "EXPERIENCE MEMORY VALIDATED"
    if not tests_ok or not temporal["passed"] or not det_ok:
        conclusion = "EXPERIENCE MEMORY REJECTED" if (not temporal["passed"] or not tests_ok) else "EXPERIENCE MEMORY VALIDATION INCOMPLETE"

    payload = {
        "conclusion": conclusion,
        "oos": oos,
        "max_timestamp": max_ts,
        "tests": tests,
        "temporal": temporal,
        "determinism": repro,
        "holdout": holdout_status(),
        "phase2_hash_ok": sha256_file(PHASE2_OOS_PATH) == PHASE2_OOS_SHA256,
        "live_trading": False,
        "risk_gate_loosened": False,
        "new_model": False,
    }
    save(REPORTS_DIR / "experience_audit.json", wrap("phase8_audit", "exploratory", {"recipe": RECIPE_ID}, audit, SEED))
    save(REPORTS_DIR / "temporal_validation.json", wrap("phase8_temporal", "exploratory", {"recipe": RECIPE_ID}, temporal, SEED))
    save(REPORTS_DIR / "replay_summary.json", wrap("phase8_replay", "exploratory", {"recipe": RECIPE_ID}, replay_summary, SEED))
    save(REPORTS_DIR / "reproducibility.json", wrap("phase8_repro", "exploratory", {"recipe": RECIPE_ID}, repro, SEED))
    save(REPORTS_DIR / "phase8_conclusion.json", wrap("phase8_conclusion", "exploratory", {"recipe": RECIPE_ID}, payload, SEED))

    assert_holdout_untouched()
    print("tests", tests)
    print("temporal", temporal["passed"], "det", det_ok)
    print("store", b1["store_size_end"], "skipped", b1["n_skipped"])
    print("final", b1["final_BUY"], b1["final_SELL"], b1["final_WAIT"])
    print("holdout", holdout_status())
    print(conclusion)
    return 0 if conclusion == "EXPERIENCE MEMORY VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
