"""Phase 59 runner — data quality & execution economics; CLI only."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from phase54.decision import NullPolicy
from phase59.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    PHASE58_SPLITS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase59.costs import build_cost_classification
from phase59.coverage import build_coverage_manifest
from phase59.experience import reconcile_experience
from phase59.inventory import build_inventory, phase58_holdout
from phase59.observability import build_observability
from phase59.pipeline import integrity_from_cache, scan_days, spread_from_cache
from phase59.progress import write_json, write_text
from phase59.stress import run_stress
from phase59.sufficiency import build_sufficiency, choose_verdict
from phase59.wait_econ import analyze_wait


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    inventory = build_inventory()
    holdout = set(phase58_holdout())
    all_days = list(inventory.get("union_days") or [])
    # Prefer phase43/49/53 days for deep tick economics; still inventory all sources
    preferred_roots = ("phase53", "phase49", "phase43")
    preferred = []
    for name in preferred_roots:
        preferred.extend((inventory.get("sources") or {}).get(name, {}).get("days") or [])
    preferred = sorted(set(preferred))
    if not preferred:
        preferred = all_days
    # Integrity on preferred ∪ holdout-in-union (coverage), not phase38/40 duplicates alone
    integrity_days = sorted(set(preferred) | set(inventory.get("phase58_holdout_in_union") or []))
    print("scanning_days", len(integrity_days), flush=True)
    cache = scan_days(integrity_days)
    integrity = integrity_from_cache(cache)
    # Research economics: exclude Phase58 sealed holdout
    research_days = [d for d in preferred if d not in holdout]
    spread = spread_from_cache(cache, research_days)
    costs = build_cost_classification()
    # Bound stress/wait cost: chronological sample of research days
    stress_days = research_days[:12]
    print("stress_days", len(stress_days), flush=True)
    stress = run_stress(stress_days)
    observability = build_observability(research_days)
    # WAIT economics: discovery+validation from Phase58 if available (no holdout)
    wait_days = research_days[:12]
    if PHASE58_SPLITS.is_file():
        splits = json.loads(PHASE58_SPLITS.read_text(encoding="utf-8"))
        wait_days = [d for d in (list(splits.get("discovery") or []) + list(splits.get("validation") or [])) if d in set(research_days)][:12]
    print("wait_days", len(wait_days), flush=True)
    wait = analyze_wait(wait_days)
    experience = reconcile_experience()
    sufficiency = build_sufficiency(
        inventory=inventory,
        integrity=integrity,
        spread=spread,
        costs=costs,
        stress=stress,
        observability=observability,
        wait=wait,
        experience=experience,
    )
    coverage = build_coverage_manifest(
        inventory,
        integrity,
        research_days=research_days,
        stress_days=stress_days,
        wait_days=wait_days,
        holdout=sorted(holdout),
    )

    holdout_sealed = True
    # Verify we did not open holdout for wait/stress fitting
    if any(d in holdout for d in (wait.get("days_used") or [])):
        holdout_sealed = False
    # Explicit: stress/wait flag
    if not stress.get("holdout_excluded") or wait.get("holdout_used"):
        holdout_sealed = False

    null_ok = NullPolicy().version == EXPECTED_NULL_POLICY
    verdict, reason = choose_verdict(
        integrity=integrity, spread=spread, sufficiency=sufficiency, holdout_sealed=holdout_sealed and null_ok
    )

    # Persist reports
    write_json(REPORTS_DIR / "dataset_inventory.json", inventory)
    write_json(REPORTS_DIR / "dataset_integrity.json", {k: v for k, v in integrity.items() if k != "rows"})
    write_json(REPORTS_DIR / "dataset_integrity_full.json", integrity)
    write_json(REPORTS_DIR / "data_coverage_manifest.json", coverage)
    write_json(REPORTS_DIR / "spread_distributions.json", spread)
    write_json(REPORTS_DIR / "execution_cost_classification.json", costs)
    write_json(REPORTS_DIR / "execution_stress.json", stress)
    write_json(REPORTS_DIR / "market_observability.json", observability)
    write_json(REPORTS_DIR / "wait_economics.json", wait)
    write_json(REPORTS_DIR / "experience_reconciliation.json", experience)
    write_json(REPORTS_DIR / "data_sufficiency_matrix.json", sufficiency)

    runtime_s = time.perf_counter() - t0
    machine = {
        "recipe": RECIPE_ID,
        "verdict": verdict,
        "verdict_reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "null_policy_ok": null_ok,
        "holdout_sealed": holdout_sealed,
        "phase58_holdout": sorted(holdout),
        "inventory_sha256": inventory.get("inventory_sha256"),
        "integrity_sha256": integrity.get("integrity_sha256"),
        "coverage_sha256": coverage.get("coverage_sha256"),
        "spread_sha256": spread.get("spread_sha256"),
        "cost_sha256": costs.get("cost_sha256"),
        "stress_sha256": stress.get("stress_sha256"),
        "observability_sha256": observability.get("observability_sha256"),
        "wait_sha256": wait.get("wait_sha256"),
        "experience_sha256": experience.get("experience_sha256"),
        "sufficiency_sha256": sufficiency.get("sufficiency_sha256"),
        "summary": {
            "union_days": inventory.get("union_n_days"),
            "integrity_ok_days": integrity.get("n_ok"),
            "observable_spread_bars": spread.get("observable_bars"),
            "unobservable_bars": spread.get("unobservable_bars_no_ticks"),
            "spread_overall": spread.get("overall"),
            "commission": "UNKNOWN",
            "slippage": "UNKNOWN",
            "shadow_n": (experience.get("agent_shadow") or {}).get("n"),
            "hist_n": (experience.get("historical_hypothetical") or {}).get("n"),
        },
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
    }
    machine["sha256"] = canonical_json_sha256({k: machine[k] for k in machine if k != "sha256"})
    write_json(REPORTS_DIR / "validation_results.json", machine)

    lines = [
        "# Phase 59 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Reason:** {reason}",
        f"**Generated:** {_utc()}",
        "",
        "## What we know",
        f"- Archive union days: `{inventory.get('union_n_days')}` ({inventory.get('date_min')} → {inventory.get('date_max')})",
        f"- Integrity OK days: `{integrity.get('n_ok')}` / `{integrity.get('n_days')}`",
        f"- Total M5 bars audited: `{integrity.get('total_m5_bars')}`; ticks: `{integrity.get('total_ticks')}`",
        f"- Observable spread bars: `{spread.get('observable_bars')}`; unobservable (no ticks): `{spread.get('unobservable_bars_no_ticks')}`",
        f"- Overall spread (observed): mean=`{(spread.get('overall') or {}).get('mean')}`, "
        f"median=`{(spread.get('overall') or {}).get('median')}`, "
        f"p95=`{(spread.get('overall') or {}).get('p95')}`, max=`{(spread.get('overall') or {}).get('max')}`",
        f"- Spread/ATR: `{(spread.get('spread_over_atr') or {})}`",
        f"- By session: `{spread.get('by_session')}`",
        "",
        "## What we do not know",
        "- Broker **commission**: UNKNOWN (not invented, not treated as zero).",
        "- **Slippage**: UNKNOWN (stress proxies are labeled hypothetical only).",
        "- Execution delay / adverse selection: UNKNOWN.",
        "- Live broker economics ≠ MetaQuotes-Demo.",
        "",
        "## Dataset integrity",
        f"- Dup-timestamp days: `{integrity.get('n_dup_ts_days')}`",
        f"- OHLC-error days: `{integrity.get('n_ohlc_error_days')}`",
        f"- Gap days (>5m): `{integrity.get('n_gap_days')}`",
        f"- Days without ticks: `{integrity.get('days_without_ticks')}`",
        f"- SHA: `{integrity.get('integrity_sha256')}`",
        "",
        "## Data coverage manifest",
        f"- Deep tick audit days: `{coverage.get('deep_tick_audit_days_n')}` / union `{coverage.get('union_n_days')}`",
        f"- Union days not deep-audited: `{coverage.get('union_days_not_in_deep_audit_n')}`",
        f"- Excluded observation segments: `{len(coverage.get('excluded_observation_segments') or [])}`",
        f"- Source silently repaired: `{coverage.get('source_data_silently_repaired')}`",
        f"- Artifact: `reports/phase59/data_coverage_manifest.json`",
        f"- SHA: `{coverage.get('coverage_sha256')}`",
        "",
        "## Execution cost classification",
        f"- `{costs.get('components')}`",
        f"- Scenarios: `{list((costs.get('scenarios_from_phase46') or {}).keys())}`",
        "",
        "## Execution stress (holdout excluded)",
        f"- Events: `{stress.get('n_events')}`",
        f"- By scenario: `{stress.get('by_scenario')}`",
        f"- Observed elevated vs normal spread/ATR: `{stress.get('observed_regime_split')}`",
        "",
        "## Market observability",
        f"- `{observability}`",
        "",
        "## WAIT economics (no holdout; no filter optimization)",
        f"- `{wait}`",
        "",
        "## Historical vs shadow experience",
        f"- Hist n: `{(experience.get('historical_hypothetical') or {}).get('n')}`",
        f"- Shadow n: `{(experience.get('agent_shadow') or {}).get('n')}`",
        f"- Merged: `{experience.get('stores_merged')}`",
        f"- Force-aligned to edge: `{experience.get('phase58_shadow_force_align')}`",
        "",
        "## Data sufficiency matrix",
        *[f"- `{m['capability']}`: **{m['status']}** — {m['basis']}" for m in (sufficiency.get("matrix") or [])],
        "",
        "## Phase58 holdout",
        f"- Sealed: `{holdout_sealed}`",
        f"- Holdout days: `{sorted(holdout)}`",
        "",
        "## NullPolicy / safety",
        f"- NullPolicy: `{null_ok}`",
        "- No live MT5, no broker orders, no auto-start, Phase0–58 unmodified.",
        "",
        "## Additional evidence required before next intelligence phase",
        "1. Measured or broker-documented commission schedule (or explicit acceptance of UNKNOWN).",
        "2. Slippage study vs intended price on the target venue (not demo proxies presented as truth).",
        "3. Broader regime/disruption labeling if edge research resumes.",
        "4. Continue treating Phase58 holdout as sealed until a preregistered survivor exists.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase59.run_phase59",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "No Phase60 started.",
        "",
    ]
    write_text(REPORTS_DIR / "FINAL_REPORT.md", "\n".join(lines))
    write_text(
        DOCS_DIR / "PHASE_59_EXECUTION_ECONOMICS.md",
        "\n".join(
            [
                "# Phase 59 — Market Data Quality & Execution Economics",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `reports/phase59/FINAL_REPORT.md`.",
                "",
            ]
        ),
    )

    print(verdict, reason)
    print("report", REPORTS_DIR / "FINAL_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
