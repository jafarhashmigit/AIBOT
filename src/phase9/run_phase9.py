"""Phase 9: experience-informed Ridge vs frozen Phase 6 agent. Research only."""

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
    jsonable,
    save,
    sha256_file,
    wrap,
    write_csv_dicts,
)
from phase7.evaluation import baseline_actions, score_actions
from phase7.oos_adapter import load_paired
from phase9.audit import snapshot_protected
from phase9.constants import (
    DATA_DIR,
    FOLDS,
    MIN_EXPERIENCES_PER_SIDE,
    N_BOOT,
    PHASE2_OOS_PATH,
    PHASE2_OOS_SHA256,
    PHASE9_LEARNER_FEATURE_ALLOWLIST,
    POLICY_ID,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    RIDGE_ALPHA,
    SEED,
)
from phase9.evaluation import (
    actions_from_records,
    bootstrap_decision_r_diff,
    fold_counts,
    prediction_quality,
)
from phase9.replay import replay


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


def _csv_rows(records: list[dict]) -> list[dict]:
    out = []
    for rec in records:
        row = dict(rec)
        for key in ("pred_buy", "pred_sell", "latest_outcome_end", "max_training_outcome_end"):
            if row.get(key) is None:
                row[key] = ""
        out.append(row)
    return out


def _label(metrics: dict) -> dict:
    out = dict(metrics)
    out["label"] = "DESCRIPTIVE — NOT USED FOR OPTIMIZATION"
    return out


def _write_results_md(path: Path, payload: dict) -> None:
    r = payload["result"]
    b = r["bootstrap"]
    dist = r["phase9_final"]["distribution"]
    raw = r["phase9_raw_diagnostic"]["distribution"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "# Phase 9 results",
            "",
            "Research only. Not production. Not live trading. Not an economic edge.",
            "",
            f"**Conclusion:** `{r['conclusion']}`",
            "",
            "## Configuration (frozen before scoring)",
            "",
            f"- Recipe: `{r['learner']['recipe_id']}`",
            f"- Policy: `{r['learner']['policy_id']}`",
            f"- Ridge alpha: `{r['learner']['alpha']}`",
            f"- Min experiences per side: `{r['learner']['min_experiences_per_side']}`",
            f"- Allowlist: `{', '.join(r['learner']['feature_allowlist'])}`",
            f"- RiskGate: wait_only / champion `no_model` (unchanged)",
            "",
            "## Replay",
            "",
            f"- Decisions: {r['replay']['n_decisions']}",
            f"- Completed experiences used for training: {r['replay']['completed_experiences']}",
            f"- Skipped / pending: {r['replay']['n_skipped']}",
            f"- Cold-start fallbacks: {r['replay']['n_fallback']}",
            f"- Learner-available decisions: {r['replay']['n_learner_available']}",
            f"- Max timestamp accessed: `{r['max_timestamp']}`",
            f"- Holdout opens: {r['holdout']['test_open_attempts']}",
            "",
            "## BUY / SELL / WAIT (final, after RiskGate)",
            "",
            f"- BUY {dist['BUY']} / SELL {dist['SELL']} / WAIT {dist['WAIT']}",
            "",
            "## BUY / SELL / WAIT (raw, pre-gate, diagnostic only)",
            "",
            f"- BUY {raw['BUY']} / SELL {raw['SELL']} / WAIT {raw['WAIT']}",
            "",
            "## Primary comparison (final decisions)",
            "",
            f"- Mean difference in R (Phase 9 − frozen Phase 6): {b['mean_difference_r']}",
            f"- 95% CI: [{b['ci_low']}, {b['ci_high']}]",
            f"- Bootstrap P(diff <= 0): {b['p_diff_le_0']}",
            f"- Draws: {b['n_samples']}, seed {b['seed']}, day-cluster",
            "",
            "Label: DESCRIPTIVE — NOT USED FOR OPTIMIZATION",
            "",
            "## Reproducibility",
            "",
            f"- Two learner replays identical: `{r['reproducibility']['passed']}`",
            "",
            "## Tests",
            "",
            f"- {r['tests']['passed']}/{r['tests']['tests_run']} passed",
            "",
            "## Integrity",
            "",
            f"- Protected artifacts unchanged: `{r['integrity_after_ok']}`",
            f"- Temporal leakage violations: {r['temporal']['n_leakage']}",
            "",
            "Pushed to GitHub: no",
            "",
        ]),
        encoding="utf-8",
    )


def _write_limitations_md(path: Path, payload: dict) -> None:
    r = payload["result"]
    path.write_text(
        "\n".join([
            "# Phase 9 limitations",
            "",
            "This phase is a controlled OOS experiment, not a trading system.",
            "",
            "1. The Phase 6 RiskGate remains WAIT-only with champion `no_model`. "
            "It blocks every BUY/SELL. Final trade count is therefore expected to be zero "
            "regardless of learner output. The gate was not loosened.",
            "2. One predeclared learner: side-specific Ridge, alpha=1.0. No search, no second candidate.",
            "3. Features are only the frozen Phase 2 decision-time allowlist. No new indicators.",
            "4. Targets are hypothetical side `actual_net_r` already present in Phase 2 OOS. "
            "WAIT experiences have no selected realized R; both sides are trained from the same timestamp.",
            "5. Cold start uses the frozen Phase 6 DecisionEngine until 100 completed experiences per side.",
            "6. The holdout file was not opened. No row after "
            f"`{RESEARCH_CUTOFF}` UTC was used.",
            "7. Prediction-quality and pre-gate raw-action metrics are descriptive. "
            "They were not used to retune alpha, features, or the decision rule.",
            "8. Bootstrap is descriptive evidence for the single predeclared comparison. "
            "It is not a license to try another learner.",
            "9. Improvement of raw (pre-gate) counts would still not be an economic edge: "
            "costs, fills, and live execution are out of scope; the frozen gate remains in the architecture.",
            "10. Phase 9 does not claim production readiness and does not enable live trading.",
            "",
            f"Empirical note: final BUY={r['phase9_final']['distribution']['BUY']}, "
            f"SELL={r['phase9_final']['distribution']['SELL']}, "
            f"WAIT={r['phase9_final']['distribution']['WAIT']}; "
            f"completed experiences={r['replay']['completed_experiences']}.",
            "",
        ]),
        encoding="utf-8",
    )


def classify(tests_ok: bool, temporal_ok: bool, det_ok: bool, integrity_ok: bool,
             mean_diff: float, ci_low: float, n_final_trades: int) -> str:
    if not tests_ok or not temporal_ok or not integrity_ok:
        return "PHASE 9 REJECTED"
    if not det_ok:
        return "PHASE 9 VALIDATION INCOMPLETE"
    improved = n_final_trades > 0 and mean_diff > 0 and ci_low > 0
    if improved:
        return "PROMISING OOS EXPERIENCE-LEARNING RESULT — REQUIRES INDEPENDENT REPLICATION"
    return "EXPERIENCE LEARNING DID NOT IMPROVE OOS DECISION QUALITY"


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    integrity_before = snapshot_protected()
    tests = run_tests()

    pairs, eval_rows, oos_integrity = load_paired()
    oos_hash = sha256_file(PHASE2_OOS_PATH)
    if oos_hash != PHASE2_OOS_SHA256:
        raise RuntimeError("HARD FAILURE: Phase 2 OOS hash changed")
    max_ts = max(p["timestamp"] for p in pairs)
    if max_ts > RESEARCH_CUTOFF:
        raise RuntimeError("HARD FAILURE: timestamp after cutoff")

    print("replay A frozen", flush=True)
    a1 = replay(pairs, eval_rows, use_learner=False)
    print("replay B1 learner", flush=True)
    b1 = replay(pairs, eval_rows, use_learner=True)
    print("replay B2 learner", flush=True)
    b2 = replay(pairs, eval_rows, use_learner=True)

    keys = ("final_decision", "raw_decision", "n_experiences", "pred_buy", "pred_sell",
            "source", "learner_train_n")
    det_ok = all(
        [r[k] for r in b1["records"]] == [r[k] for r in b2["records"]]
        for k in keys
    ) and b1["completed_experiences"] == b2["completed_experiences"]
    if not det_ok:
        print("PHASE 9 VALIDATION INCOMPLETE: learner replays differed", flush=True)

    a_final = actions_from_records(a1["records"], "final_decision")
    b_final = actions_from_records(b1["records"], "final_decision")
    b_raw = actions_from_records(b1["records"], "raw_decision")

    score_a = _label(score_actions(eval_rows, a_final))
    score_b = _label(score_actions(eval_rows, b_final))
    score_raw = _label(score_actions(eval_rows, b_raw))
    score_raw["note"] = "pre-gate diagnostic only; not used for optimization or H1"

    baselines = baseline_actions(pairs, eval_rows)
    baseline_scores = {
        "A_WAIT": _label(score_actions(eval_rows, baselines["A_WAIT"])),
        "E1_PHASE2": _label(score_actions(eval_rows, baselines["E1_PHASE2"])),
        "B_DIRECTION": _label(score_actions(eval_rows, baselines["B_DIRECTION"])),
        "D_FROZEN_PHASE6": score_a,
    }

    boot = bootstrap_decision_r_diff(eval_rows, a_final, b_final)
    pred_q = prediction_quality(b1["records"], eval_rows)
    folds = fold_counts(b1["records"])

    for rec in b1["records"]:
        latest = rec["latest_outcome_end"]
        if latest is not None and not (latest < rec["timestamp"]):
            raise RuntimeError("HARD FAILURE: latest_experience_outcome_end >= T")
        tmax = rec["max_training_outcome_end"]
        if tmax is not None and not (tmax < rec["timestamp"]):
            raise RuntimeError("HARD FAILURE: max_training_outcome_end >= T")

    write_csv_dicts(DATA_DIR / "phase9_replay_log.csv", _csv_rows(b1["records"]))
    write_csv_dicts(DATA_DIR / "phase9_frozen_replay.csv", _csv_rows(a1["records"]))

    integrity_after = snapshot_protected()
    integrity_ok = all(v["unchanged"] for v in integrity_after.values())
    temporal_ok = a1["n_leakage"] == 0 and b1["n_leakage"] == 0
    n_final_trades = int(score_b["distribution"]["BUY"] + score_b["distribution"]["SELL"])
    conclusion = classify(
        bool(tests["ok"]), temporal_ok, det_ok, integrity_ok,
        float(boot["mean_difference_r"]), float(boot["ci_low"]) if boot["ci_low"] == boot["ci_low"] else -1.0,
        n_final_trades,
    )

    learner_cfg = {
        "recipe_id": RECIPE_ID,
        "policy_id": POLICY_ID,
        "type": "side_specific_ridge",
        "alpha": RIDGE_ALPHA,
        "min_experiences_per_side": MIN_EXPERIENCES_PER_SIDE,
        "scaler": None,
        "feature_allowlist": list(PHASE9_LEARNER_FEATURE_ALLOWLIST),
        "target": "hypothetical_side_net_r",
        "cold_start": "NO EXPERIENCE MODEL AVAILABLE → frozen Phase 6 DecisionEngine",
        "risk_gate": "phase6_wait_only_no_champion_v1 unchanged",
    }

    replay_summary = {
        "A_frozen": {k: a1[k] for k in (
            "n_decisions", "final_BUY", "final_SELL", "final_WAIT",
            "raw_BUY", "raw_SELL", "raw_WAIT", "n_leakage", "n_skipped",
            "n_fallback", "n_learner_available", "completed_experiences",
        )},
        "B_learner": {k: b1[k] for k in (
            "n_decisions", "final_BUY", "final_SELL", "final_WAIT",
            "raw_BUY", "raw_SELL", "raw_WAIT", "n_leakage", "n_skipped",
            "n_fallback", "n_learner_available", "completed_experiences",
        )},
        "n_decisions": b1["n_decisions"],
        "completed_experiences": b1["completed_experiences"],
        "n_skipped": b1["n_skipped"],
        "n_fallback": b1["n_fallback"],
        "n_learner_available": b1["n_learner_available"],
        "max_timestamp": max_ts,
        "folds": folds,
        "economic_metrics": "DESCRIPTIVE — NOT USED FOR OPTIMIZATION",
    }

    temporal = {
        "boundary": "outcome_end < decision_time AND max_training_outcome_end < decision_time",
        "n_leakage": b1["n_leakage"],
        "n_leakage_A": a1["n_leakage"],
        "passed": temporal_ok,
        "skipped_sample": b1["skipped"][:20],
        "n_skipped": b1["n_skipped"],
    }

    learner_audit = {
        "configuration": learner_cfg,
        "n_fits_logged": b1["n_fits_logged"],
        "fit_audit_head": b1["fit_audit_head"],
        "fit_audit_tail": b1["fit_audit_tail"],
        "n_fallback": b1["n_fallback"],
        "n_learner_available": b1["n_learner_available"],
        "completed_experiences": b1["completed_experiences"],
        "note": "audit records training provenance after the fact; DecisionEngine never reads this file",
    }

    repro = {
        "seed": SEED,
        "passed": det_ok,
        "hash_B1": _hash_obj([[r[k] for k in keys] for r in b1["records"]]),
        "hash_B2": _hash_obj([[r[k] for k in keys] for r in b2["records"]]),
        "identical_predictions": det_ok,
        "identical_decisions": det_ok,
        "identical_experience_counts": det_ok,
    }

    evaluation = {
        "label": "DESCRIPTIVE — NOT USED FOR OPTIMIZATION",
        "windows": list(FOLDS) + ["pooled"],
        "baselines": baseline_scores,
        "phase9_final": score_b,
        "phase9_raw_diagnostic": score_raw,
        "prediction_quality": pred_q,
        "folds": folds,
        "primary_comparison": "Phase 9 Experience Learner vs Frozen Phase 6 Agent",
    }

    holdout = holdout_status()
    result = {
        "conclusion": conclusion,
        "learner": learner_cfg,
        "replay": replay_summary,
        "phase9_final": score_b,
        "phase9_raw_diagnostic": score_raw,
        "bootstrap": boot,
        "reproducibility": repro,
        "tests": tests,
        "temporal": temporal,
        "holdout": holdout,
        "max_timestamp": max_ts,
        "integrity_before_ok": all(v["unchanged"] for v in integrity_before.values()),
        "integrity_after_ok": integrity_ok,
        "oos_integrity": oos_integrity,
        "live_trading": False,
        "risk_gate_loosened": False,
        "pushed": False,
    }

    cfg = {"recipe": RECIPE_ID, "alpha": RIDGE_ALPHA, "min_n": MIN_EXPERIENCES_PER_SIDE, "seed": SEED}
    save(REPORTS_DIR / "learner_audit.json", wrap("phase9_learner_audit", "exploratory", cfg, learner_audit, SEED))
    save(REPORTS_DIR / "temporal_validation.json", wrap("phase9_temporal", "exploratory", cfg, temporal, SEED))
    save(REPORTS_DIR / "replay_summary.json", wrap("phase9_replay", "exploratory", cfg, replay_summary, SEED))
    save(REPORTS_DIR / "evaluation.json", wrap("phase9_evaluation", "exploratory", cfg, evaluation, SEED))
    save(REPORTS_DIR / "bootstrap.json", wrap("phase9_bootstrap", "exploratory", cfg, boot, SEED))
    save(REPORTS_DIR / "reproducibility.json", wrap("phase9_repro", "exploratory", cfg, repro, SEED))
    payload = wrap("phase9_conclusion", "exploratory", cfg, result, SEED)
    save(REPORTS_DIR / "phase9_conclusion.json", payload)

    _write_results_md(ROOT / "docs" / "agent" / "PHASE_9_RESULTS.md", payload)
    _write_limitations_md(ROOT / "docs" / "agent" / "PHASE_9_LIMITATIONS.md", payload)

    integrity_final = snapshot_protected()
    assert_holdout_untouched()
    print("tests", tests, flush=True)
    print("temporal", temporal_ok, "det", det_ok, "integrity", integrity_ok, flush=True)
    print("final", b1["final_BUY"], b1["final_SELL"], b1["final_WAIT"], flush=True)
    print("raw", b1["raw_BUY"], b1["raw_SELL"], b1["raw_WAIT"], flush=True)
    print("holdout", holdout, flush=True)
    print("protected_final", all(v["unchanged"] for v in integrity_final.values()), flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion != "PHASE 9 REJECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
