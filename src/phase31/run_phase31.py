"""Phase 31 runner — forensic edge-failure diagnosis (autonomous)."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phase31.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase31.cost_sensitivity import run_cost_sensitivity
from phase31.data_audit import run_data_integrity_audit
from phase31.directional_diagnostics import run_buy_sell_diagnostics
from phase31.execution_audit import run_execution_cost_audit
from phase31.feature_audit import run_feature_audit
from phase31.horizon_analysis import run_horizon_analysis
from phase31.integrity import safety_snapshot
from phase31.label_audit import run_label_reconstruction_audit
from phase31.prediction_diagnostics import run_prediction_diagnostics
from phase31.preflight import run_preflight
from phase31.progress import log, mark, save_progress
from phase31.root_cause import build_root_cause_matrix
from phase31.statistical_audit import run_statistical_audit


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None if obj != obj else ("inf" if obj > 0 else "-inf")
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize(v) for v in obj]
    return obj


def _write(name: str, obj: Any) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_sanitize(obj), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def write_docs(artifacts: dict[str, Any], verdict: dict[str, Any], runtime: dict[str, Any]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    plan = DOCS_DIR / "PHASE_31_RESEARCH_PLAN.md"
    results = DOCS_DIR / "PHASE_31_RESULTS.md"
    plan.write_text(
        "\n".join(
            [
                "# PHASE 31 — Research Plan (Edge Failure Diagnosis)",
                "",
                f"Recipe: `{RECIPE_ID}`",
                "",
                "## Objective",
                "",
                "Forensic diagnosis of why Phase25–30 strategies show no credible edge.",
                "No new strategies. No optimization. No holdout. Production remains WAIT.",
                "",
                "## Stages",
                "",
                "1. Preflight / evidence verification",
                "2. Data integrity",
                "3. Feature causality",
                "4. Label reconstruction",
                "5. Execution/cost audit",
                "6. BUY/SELL diagnostic",
                "7. Horizon analysis",
                "8. Prediction vs profitability",
                "9. Statistical methodology audit",
                "10. Cost sensitivity",
                "11. Root-cause matrix + verdict",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    q = artifacts
    lines = [
        "# PHASE 31 — Results",
        "",
        f"Verdict: **{verdict['phase_verdict']}**",
        f"Champion: `{CHAMPION_STATUS}` | H13_C: `{H13C_STATUS}` | Production: `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## Biggest root cause",
        "",
        "```json",
        json.dumps(_sanitize(verdict.get("biggest_root_cause")), indent=2),
        "```",
        "",
        "## Answers",
        "",
        f"1. M5 internally valid? `{ (q.get('data_integrity') or {}).get('internally_valid') }`",
        f"2. UTC/DST conversion? see `data_integrity.timezone` (Athens→UTC methodology re-checked).",
        f"3. Features causal? `{ (q.get('feature_audit') or {}).get('features_appear_causal') }`",
        f"4. Labels reconstruct? `{ (q.get('label_reconstruction') or {}).get('reconstruction_agrees') }`",
        f"5. TP/SL same-candle? `{ ((q.get('label_reconstruction') or {}).get('unit_synthetic') or {}).get('same_candle_buy_sl_priority') }`",
        f"6. Gaps handled? label contract excludes gap windows; gap count in data audit.",
        f"7. Costs once? `{ ((q.get('execution_cost_audit') or {}).get('gross_minus_costs_equals_net') or {}).get('ok') }`",
        f"8. Execution realism enough? `{ (q.get('execution_cost_audit') or {}).get('execution_realism_fully_established') }`",
        f"9. BUY vs SELL? see buy_sell_diagnostics (typically both weak).",
        f"10. Least-poor horizon? `{ (q.get('horizon_analysis') or {}).get('least_poor_horizon') }`",
        f"11. Directional prediction > chance? compare accuracy vs majority in prediction_diagnostics.",
        "12. Predictive value failing at execution? see pred_r correlation vs mean net R.",
        "13. Bootstrap reliability? day-cluster preferred; IID may understate dependence.",
        "14. Phase30 permutation appropriate? sign-randomization has limited timing interpretation.",
        "15. Multiple-testing sufficient? log(n) penalty is heuristic, not Holm/BH.",
        "16. Negative before costs? see cost_sensitivity.recomputed.*.negative_even_before_approx_cost_addback",
        f"17. Prior conclusions invalidated? `{ verdict.get('previous_conclusions_materially_invalidated') }`",
        f"18. Biggest root cause: `{ (verdict.get('biggest_root_cause') or {}).get('id') }`",
        "19. Missing evidence: historical bid/ask; tick-level MFE/MAE; independent full feature recompute.",
        "20. Next phase: either execution-realism data collection OR new authorized research with revised stats — not H13_C tuning.",
        "",
        "## Runtime",
        "",
        "```json",
        json.dumps(runtime, indent=2),
        "```",
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(_sanitize(artifacts.get("final_safety")), indent=2),
        "```",
        "",
    ]
    results.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    start = datetime.now(timezone.utc)
    t0 = time.time()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save_progress(
        {
            "stage": "start",
            "completed_stages": [],
            "completed_audits": [],
            "completed_tests": True,
            "last_successful_operation": "start",
            "errors": [],
        }
    )

    artifacts: dict[str, Any] = {}

    log("Preflight ...")
    pre = run_preflight()
    artifacts["preflight"] = pre
    _write("preflight.json", pre)
    mark("preflight")
    if not pre.get("ok"):
        log("Preflight reported missing artifacts or safety issue — continuing only if hashes OK")
    if not pre["safety"]["protected_artifacts_intact"]:
        log("PROTECTED ARTIFACT HASH FAILURE — stopping")
        return 2
    log("Preflight complete")

    log("Data integrity audit ...")
    artifacts["data_integrity"] = run_data_integrity_audit()
    _write("data_integrity.json", artifacts["data_integrity"])
    mark("data_integrity")

    log("Feature audit ...")
    artifacts["feature_audit"] = run_feature_audit()
    _write("feature_audit.json", artifacts["feature_audit"])
    mark("feature_audit")

    log("Label reconstruction ...")
    artifacts["label_reconstruction"] = run_label_reconstruction_audit()
    _write("label_reconstruction.json", artifacts["label_reconstruction"])
    mark("label_reconstruction")

    log("Execution/cost audit ...")
    artifacts["execution_cost_audit"] = run_execution_cost_audit()
    _write("execution_cost_audit.json", artifacts["execution_cost_audit"])
    mark("execution_cost_audit")

    log("BUY/SELL diagnostics ...")
    artifacts["buy_sell_diagnostics"] = run_buy_sell_diagnostics()
    _write("buy_sell_diagnostics.json", artifacts["buy_sell_diagnostics"])
    mark("buy_sell_diagnostics")

    log("Horizon analysis ...")
    artifacts["horizon_analysis"] = run_horizon_analysis()
    _write("horizon_analysis.json", artifacts["horizon_analysis"])
    mark("horizon_analysis")

    log("Prediction diagnostics ...")
    artifacts["prediction_diagnostics"] = run_prediction_diagnostics()
    _write("prediction_diagnostics.json", artifacts["prediction_diagnostics"])
    mark("prediction_diagnostics")

    log("Statistical audit ...")
    artifacts["statistical_audit"] = run_statistical_audit()
    _write("statistical_audit.json", artifacts["statistical_audit"])
    mark("statistical_audit")

    log("Cost sensitivity ...")
    artifacts["cost_sensitivity"] = run_cost_sensitivity()
    _write("cost_sensitivity.json", artifacts["cost_sensitivity"])
    mark("cost_sensitivity")

    log("Root-cause matrix ...")
    verdict = build_root_cause_matrix(artifacts)
    artifacts["root_cause_matrix"] = verdict
    _write("root_cause_matrix.json", verdict)
    mark("root_cause")

    final_safety = safety_snapshot()
    artifacts["final_safety"] = final_safety
    end = datetime.now(timezone.utc)
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": time.time() - t0,
        "DURATION": f"{(time.time() - t0)/60.0:.2f} min",
    }
    _write("runtime.json", runtime)

    final = {
        "phase_verdict": verdict["phase_verdict"],
        "biggest_root_cause": verdict["biggest_root_cause"],
        "previous_conclusions_materially_invalidated": verdict["previous_conclusions_materially_invalidated"],
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13c": H13C_STATUS,
        "holdout_accessed": final_safety["holdout_accessed"],
        "protected_artifacts_intact": final_safety["protected_artifacts_intact"],
        "runtime": runtime,
    }
    _write("final_verdict.json", final)
    mark("final_verdict")
    write_docs(artifacts, verdict, runtime)

    log(f"Final verdict ... {verdict['phase_verdict']}")
    print(json.dumps(_sanitize(final), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
