"""Phase 32 runner — independent data & execution validation."""

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

from phase32.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    VALID_VERDICTS,
)
from phase32.execution_realism import classify_execution_realism
from phase32.feature_comparison import compare_features
from phase32.gross_net_analysis import run_gross_net_analysis
from phase32.independent_features import run_feature_recomputation
from phase32.independent_labels import reconstruct_all_labels
from phase32.integrity import safety_snapshot
from phase32.preflight import run_preflight
from phase32.progress import log, mark, save_progress
from phase32.provider_investigation import run_provider_investigation
from phase32.statistical_validation import run_statistical_validation
from phase32.trade_cost_audit import run_trade_cost_reconciliation


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None if obj != obj else ("inf" if obj > 0 else "-inf")
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if k not in {"recomputed_frame", "corrected_frame"}}
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


def decide_verdict(
    *,
    feat_ok: bool,
    label_ok: bool,
    trade_ok: bool,
    realism_class: str,
) -> str:
    fails = []
    if not feat_ok:
        fails.append("FEATURE_RECOMPUTATION_MISMATCH")
    if not label_ok:
        fails.append("LABEL_RECONSTRUCTION_MISMATCH")
    if not trade_ok:
        fails.append("TRADE_ACCOUNTING_MISMATCH")
    if len(fails) > 1:
        v = "MULTIPLE_VALIDATION_FAILURES"
    elif len(fails) == 1:
        v = fails[0]
    elif realism_class in {"ASSUMPTION_BASED", "PARTIALLY_VERIFIED", "INSUFFICIENT_EVIDENCE"}:
        v = "EXECUTION_REALISM_UNVERIFIED"
    elif realism_class == "HISTORICAL_BID_ASK_VERIFIED" and feat_ok and label_ok and trade_ok:
        v = "INDEPENDENT_VALIDATION_PASSED"
    else:
        v = "INCONCLUSIVE"
    assert v in VALID_VERDICTS
    return v


def write_docs(artifacts: dict[str, Any], verdict: str, runtime: dict) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "PHASE_32_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# PHASE 32 — Research Plan (Independent Data & Execution Validation)",
                "",
                f"Recipe: `{RECIPE_ID}`",
                "",
                "Independent feature recomputation, full label reconstruction, trade-cost reconciliation,",
                "gross vs net analysis, and bid/ask provider investigation — no strategy development.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fc = artifacts.get("feature_comparison") or {}
    lc = artifacts.get("label_comparison") or {}
    gn = artifacts.get("gross_net_analysis") or {}
    lines = [
        "# PHASE 32 — Results",
        "",
        f"Verdict: **{verdict}**",
        f"Champion: `{CHAMPION_STATUS}` | H13_C: `{H13C_STATUS}` | Production: `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## Feature recomputation",
        "",
        f"- Match within tol: `{fc.get('all_features_match_within_tol')}`",
        f"- Corrected UTC match: `{fc.get('corrected_utc_match')}`",
        f"- Totals: `{json.dumps(fc.get('totals'))}`",
        "",
        "## Label reconstruction",
        "",
        f"- Agrees: `{lc.get('reconstruction_agrees')}`",
        f"- Target mismatches: `{lc.get('target_mismatches')}`",
        f"- Side outcome mismatches: `{lc.get('eligible_side_outcome_mismatches')}`",
        f"- Gaps full/cutoff: `{lc.get('gaps_gt_5min_full_raw')}` / `{lc.get('gaps_gt_5min_le_cutoff')}`",
        "",
        "## Gross vs net",
        "",
    ]
    for sid, b in (gn.get("strategies") or {}).items():
        lines.append(
            f"- `{sid}`: n={b.get('n')} class={b.get('class')} "
            f"gross_mean_r={b.get('gross',{}).get('mean_r')} net_mean_r={b.get('net',{}).get('mean_r')}"
        )
    lines.extend(
        [
            "",
            "## Execution realism",
            "",
            f"`{(artifacts.get('execution_realism') or {}).get('classification')}`",
            "",
            "## Provider",
            "",
            f"Dukascopy: `{(artifacts.get('provider_investigation') or {}).get('dukascopy', {}).get('status')}`",
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
    )
    (DOCS_DIR / "PHASE_32_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    start = datetime.now(timezone.utc)
    t0 = time.time()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save_progress({"stage": "start", "completed_stages": [], "errors": [], "last_successful_operation": "start"})

    artifacts: dict[str, Any] = {}
    log("Preflight ...")
    pre = run_preflight()
    artifacts["preflight"] = pre
    _write("preflight.json", pre)
    mark("preflight")
    if not pre["ok"]:
        log("PROTECTED ARTIFACT / CUTOFF FAILURE — stopping")
        return 2
    log("Preflight complete")

    log("Independent feature recomputation ...")
    feat_run = run_feature_recomputation()
    # strip frames for JSON summary
    feat_summary = {k: v for k, v in feat_run.items() if k not in {"recomputed_frame", "corrected_frame"}}
    artifacts["feature_recomputation"] = feat_summary
    _write("feature_recomputation.json", feat_summary)
    mark("feature_recomputation")

    log("Feature comparison ...")
    feat_cmp = compare_features(feat_run["recomputed_frame"], feat_run["corrected_frame"])
    # Drop bulky per-feature detail? Keep but may be large — OK
    artifacts["feature_comparison"] = feat_cmp
    _write("feature_comparison.json", feat_cmp)
    mark("feature_comparison")

    log("Full label reconstruction ...")
    labels = reconstruct_all_labels()
    artifacts["full_label_reconstruction"] = labels
    artifacts["label_comparison"] = labels
    _write("full_label_reconstruction.json", labels)
    _write("label_comparison.json", labels)
    mark("full_label_reconstruction")
    mark("label_comparison")

    log("Trade cost reconciliation ...")
    trade = run_trade_cost_reconciliation()
    artifacts["trade_cost_reconciliation"] = trade
    _write("trade_cost_reconciliation.json", trade)
    mark("trade_cost_reconciliation")

    log("Gross vs net analysis ...")
    gross_net = run_gross_net_analysis()
    artifacts["gross_net_analysis"] = gross_net
    _write("gross_net_analysis.json", gross_net)
    mark("gross_net_analysis")

    log("Provider investigation ...")
    prov = run_provider_investigation()
    artifacts["provider_investigation"] = prov
    _write("provider_investigation.json", prov)
    mark("provider_investigation")

    log("Execution realism classification ...")
    realism = classify_execution_realism(
        trade_cost_ok=bool(trade.get("reconciled")),
        label_ok=bool(labels.get("reconstruction_agrees")),
        bid_ask_verified=False,
    )
    artifacts["execution_realism"] = realism
    _write("execution_realism.json", realism)
    mark("execution_realism")

    log("Statistical validation ...")
    stats = run_statistical_validation(gross_net)
    artifacts["statistical_validation"] = stats
    _write("statistical_validation.json", stats)
    mark("statistical_validation")

    feat_ok = bool(feat_cmp.get("all_features_match_within_tol") and feat_cmp.get("corrected_utc_match"))
    label_ok = bool(labels.get("reconstruction_agrees"))
    trade_ok = bool(trade.get("reconciled"))
    verdict = decide_verdict(
        feat_ok=feat_ok,
        label_ok=label_ok,
        trade_ok=trade_ok,
        realism_class=realism["classification"],
    )

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
        "phase_verdict": verdict,
        "feature_ok": feat_ok,
        "label_ok": label_ok,
        "trade_ok": trade_ok,
        "execution_realism": realism["classification"],
        "dukascopy_status": prov["dukascopy"]["status"],
        "previous_conclusions_materially_invalidated": not (feat_ok and label_ok and trade_ok),
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
    log(f"Final verdict ... {verdict}")
    print(json.dumps(_sanitize(final), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
