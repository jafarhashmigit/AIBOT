"""Phase 30 runner — multi-strategy discovery vs frozen H13_C (research only)."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phase25.data import fold_counts
from phase30.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF_UTC,
    STRATEGY_PARAMS,
)
from phase30.data import load_bundle
from phase30.evaluation.pipeline import evaluate_all, write_json_reports
from phase30.integrity import verify_safety
from phase30.progress import log, save_progress


def _fmt(x) -> str:
    if x is None:
        return "nan"
    try:
        if x != x:
            return "nan"
        return f"{float(x):.6f}"
    except Exception:
        return str(x)


def write_docs(result: dict, safety: dict, preflight: dict) -> dict[str, str]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    plan = DOCS_DIR / "PHASE_30_RESEARCH_PLAN.md"
    results = DOCS_DIR / "PHASE_30_RESULTS.md"

    plan_lines = [
        "# PHASE 30 — Research Plan (Multi-Strategy Discovery & Ranking)",
        "",
        f"Recipe: `{RECIPE_ID}`",
        "",
        "## Objective",
        "",
        "Discover whether any independently specified strategy family produces a more credible",
        "cost-aware OOS edge than frozen H13_C (`PAUSED_FROZEN_BENCHMARK`).",
        "",
        "## Safety",
        "",
        "- Isolated under `src/phase30/`",
        "- No holdout / MT5 / Discord / Telegram / OCI / installs / git push",
        "- No AGENT_SHADOW writes; production remains WAIT; champion NO_MODEL",
        "- H13_C thresholds frozen (not tuned)",
        "",
        f"Research cutoff: `{RESEARCH_CUTOFF_UTC}`",
        "",
        "## Why not Phase 25 repeats",
        "",
        "Each Phase 30 family documents `vs_phase25` in predeclared params.",
        "",
        "## Predeclared parameters",
        "",
        "```json",
        json.dumps(STRATEGY_PARAMS, indent=2),
        "```",
        "",
        "## Preflight",
        "",
        "```json",
        json.dumps(preflight, indent=2, default=str),
        "```",
        "",
        "## Safety snapshot",
        "",
        "```json",
        json.dumps(safety, indent=2, default=str),
        "```",
        "",
    ]
    plan.write_text("\n".join(plan_lines) + "\n", encoding="utf-8")

    h = result["h13c_benchmark"]["metrics"]
    hp = h["score"]["pooled"]
    rlines = [
        "# PHASE 30 — Results",
        "",
        f"Created: `{result['created_at_utc']}`",
        f"Phase verdict: **{result['phase_verdict']}**",
        f"Champion: `{result['champion_status']}` | H13_C: `{result['h13c_status']}` ({result['h13c_role']}) | Production: `{result['production_final_action']}`",
        "",
        "## Comparative table (pooled, after costs)",
        "",
        "| Strategy | N | Mean R | PF | Win% | Max DD$ | Fold Stability | Status |",
        "|---|---:|---:|---:|---:|---:|---|---|",
        (
            f"| H13_C (FROZEN_BENCHMARK) | {hp['n']} | {_fmt(hp['mean_r'])} | {_fmt(hp['profit_factor'])} | "
            f"{_fmt(hp['win_rate'])} | {_fmt(hp['max_drawdown_usd'])} | "
            f"{result['h13c_benchmark']['metrics']['score'].get('all_active_folds_positive')} | FROZEN_BENCHMARK |"
        ),
    ]
    for row in result["ranking"]:
        sid = row["strategy_id"]
        block = result["strategies"][sid]
        p = block["metrics"]["score"]["pooled"]
        rlines.append(
            f"| {sid} | {p['n']} | {_fmt(p['mean_r'])} | {_fmt(p['profit_factor'])} | "
            f"{_fmt(p['win_rate'])} | {_fmt(p['max_drawdown_usd'])} | "
            f"{block['metrics']['score'].get('all_active_folds_positive')} | {block['decision']['status']} |"
        )

    rlines.extend(["", "## Ranking (composite)", ""])
    for row in result["ranking"]:
        rlines.append(
            f"- #{row['rank']} `{row['strategy_id']}` score={_fmt(row['composite_score'])} "
            f"status={row['status']} mean_r={_fmt(row['mean_r'])} n={row['n']} sig/500={_fmt(row.get('signals_per_500'))}"
        )

    rlines.extend(["", "## Required answers", ""])
    best = result["ranking"][0] if result["ranking"] else None
    best_block = result["strategies"][best["strategy_id"]] if best else None
    pos = result["diversity"]["n_positive_mean_r"]
    fold_ok = result["diversity"]["n_fold_stable"]
    rlines.extend(
        [
            f"1. Outperform H13_C mean R? best Δ check via ranking; H13_C mean_r={_fmt(hp['mean_r'])}",
            f"2. Survive all WF folds? n_fold_stable={fold_ok}",
            "3. Survive costs? see Gate E / cost_robustness 1.5x in per-strategy blocks",
            "4. Survive bootstrap? see CI in metrics.bootstrap",
            "5. Survive permutation? see robustness_results for shortlist",
            "6. Param perturbation? see robustness_results",
            "7. Single-trade dependent? see drawdown_concentration flags",
            f"8. Multiple-testing: tested={result['multiple_testing']['n_strategies_tested']}; {result['multiple_testing']['note']}",
            f"9. Failed families: see REJECTED/WEAK statuses",
            f"10. Forward-shadow deserving: verdict={result['phase_verdict']}",
            f"11. Signals per 500 (best): {_fmt(best.get('signals_per_500') if best else None)}",
            "12. Forward validation practicality: require non-rare frequency + RESEARCH_CANDIDATE",
            "13. Better path than H13_C? only if RESEARCH_CANDIDATE_FOUND with material improvement",
            "",
            f"Positive mean-R families: {pos}",
            "",
            "## Diversity",
            "",
            "```json",
            json.dumps(result["diversity"], indent=2),
            "```",
            "",
            "## Final safety",
            "",
            f"- Production = `{PRODUCTION_FINAL_ACTION}`",
            f"- Champion = `{CHAMPION_STATUS}`",
            f"- H13_C = `{H13C_STATUS}`",
            "- Broker Orders = 0",
            "- Holdout Accessed = false",
            "",
        ]
    )
    if best_block:
        rlines.extend(
            [
                "## Best composite candidate (not automatically an edge)",
                "",
                f"- id: `{best['strategy_id']}`",
                f"- status: {best_block['decision']['status']}",
                f"- n: {best_block['n_trades']}",
                f"- mean_r: {_fmt(best_block['metrics']['mean_r'])}",
                f"- pf: {_fmt(best_block['metrics']['profit_factor'])}",
                f"- max_dd: {_fmt(best_block['metrics']['max_drawdown_usd'])}",
                f"- rationale: {best_block['decision']['rationale']}",
                "",
            ]
        )
    results.write_text("\n".join(rlines) + "\n", encoding="utf-8")
    return {"plan": str(plan), "results": str(results)}


def main() -> int:
    start = datetime.now(timezone.utc)
    t0 = time.time()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log("Preflight ...")
    save_progress({"stage": "preflight", "completed_strategies": [], "completed_folds": [], "completed_robustness": [], "last_successful_operation": "start"}, REPORTS_DIR)

    bundle = load_bundle()
    safety = verify_safety(bundle, PROJECT_ROOT)
    if not safety["checks"]["all_pass"]:
        log("SAFETY VIOLATION — stopping")
        (REPORTS_DIR / "preflight.json").write_text(json.dumps(safety, indent=2) + "\n", encoding="utf-8")
        return 2

    preflight = {
        "recipe": RECIPE_ID,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "n_oos_timestamps": len(bundle["timestamps"]),
        "fold_counts": fold_counts(bundle["timestamps"]),
        "n_strategies": len(STRATEGY_PARAMS),
        "strategy_ids": list(STRATEGY_PARAMS.keys()),
        "safety_all_pass": True,
        "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (REPORTS_DIR / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    log("Preflight complete")

    log("Load approved historical data complete")
    log("Construct / evaluate all predeclared strategies ...")
    result = evaluate_all(bundle, reports_dir=REPORTS_DIR, resume=True)
    log("Write JSON reports ...")
    paths = write_json_reports(result, REPORTS_DIR)
    docs = write_docs(result, safety, preflight)

    end = datetime.now(timezone.utc)
    duration = time.time() - t0
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": duration,
        "DURATION": f"{duration/60.0:.2f} min",
    }
    (REPORTS_DIR / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")

    best = result["ranking"][0] if result["ranking"] else {}
    h = result["h13c_benchmark"]["metrics"]["score"]["pooled"]
    summary = {
        "phase_verdict": result["phase_verdict"],
        "best_candidate": best.get("strategy_id"),
        "best_n": best.get("n"),
        "best_mean_r": best.get("mean_r"),
        "best_pf": best.get("profit_factor"),
        "best_max_dd": best.get("max_drawdown_usd"),
        "h13c_mean_r": h.get("mean_r"),
        "h13c_pf": h.get("profit_factor"),
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "paths": paths,
        "docs": docs,
        "runtime": runtime,
    }
    print(json.dumps(summary, indent=2, default=str))
    log("Final verdict complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
