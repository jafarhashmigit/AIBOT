"""Phase 58 runner — market intelligence research; CLI only."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase54.decision import NullPolicy
from phase58.audit import build_research_audit
from phase58.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase58.data import chronological_splits
from phase58.evaluation import evaluate_hypothesis
from phase58.events import build_events_for_days
from phase58.learning import evaluate_learning
from phase58.progress import write_json, write_text
from phase58.registry import HYPOTHESES, build_registry


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    results = payload.get("hypothesis_results") or []
    survivors = [r for r in results if r.get("survives_discovery") and r.get("survives_validation")]
    disc_only = [r for r in results if r.get("survives_discovery") and not r.get("survives_validation")]
    learning = payload.get("learning") or {}
    if survivors and payload.get("holdout_confirmed"):
        return (
            "MARKET_INTELLIGENCE_EDGE_VALIDATED",
            f"Holdout-confirmed survivors: {[s['hypothesis_id'] for s in survivors]}",
        )
    if survivors and not payload.get("holdout_opened"):
        return (
            "MARKET_INTELLIGENCE_PARTIAL",
            "Discovery+validation survivors exist but holdout not opened or not confirmed.",
        )
    if disc_only:
        return (
            "MARKET_INTELLIGENCE_PARTIAL",
            f"Discovery survivors failed validation: {[s['hypothesis_id'] for s in disc_only]}",
        )
    if all(r.get("fail_reasons") for r in results) and results:
        # all rejected
        if learning.get("demonstrates_learning"):
            return (
                "RESEARCH_INCONCLUSIVE",
                "No H58 family survived gates; learning CI positive but not promoted.",
            )
        return (
            "NO_INFORMATION_FAMILY_FOUND",
            "No preregistered H58 family survived Bonferroni date-block discovery gates vs WAIT/controls.",
        )
    return ("RESEARCH_INCONCLUSIVE", "Insufficient conclusive evidence.")


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    audit = build_research_audit()
    registry = build_registry()
    splits = chronological_splits()
    write_json(REPORTS_DIR / "research_audit.json", audit)
    write_json(REPORTS_DIR / "hypothesis_registry.json", registry)
    write_json(REPORTS_DIR / "dataset_splits.json", splits)

    disc_events = build_events_for_days(splits["discovery"])
    val_events = build_events_for_days(splits["validation"])
    manifest = {
        "discovery_n_events": len(disc_events),
        "validation_n_events": len(val_events),
        "discovery_days": splits["discovery"],
        "validation_days": splits["validation"],
        "holdout_sealed": splits["holdout_sealed"],
        "feature_version": "phase58_v1",
        "outcome_provenance": "phase49.build_outcome OBSERVED_BIDASK_ONLY",
    }
    manifest["manifest_sha256"] = canonical_json_sha256(manifest)
    write_json(REPORTS_DIR / "dataset_manifest.json", manifest)

    results = []
    for h in HYPOTHESES:
        results.append(evaluate_hypothesis(h["id"], disc_events, val_events))
    write_json(REPORTS_DIR / "hypothesis_results.json", results)

    survivors = [r for r in results if r.get("survives_discovery") and r.get("survives_validation")]
    holdout_opened = False
    holdout_confirmed = False
    holdout_detail = None
    if survivors and splits["holdout_sealed"]:
        # Open holdout only for survivors
        holdout_opened = True
        hold_events = build_events_for_days(splits["holdout_sealed"])
        holdout_detail = []
        for s in survivors:
            from phase58.policies import fit_thresholds
            from phase58.evaluation import run_policy, calibrate, date_block_bootstrap

            thr = fit_thresholds(disc_events)
            dec = run_policy(hold_events, s["hypothesis_id"], thr)
            cal = calibrate(dec)
            pairs = [(d["day"], float(d["net_r"])) for d in dec if d.get("net_r") is not None]
            boot = date_block_bootstrap(pairs, bonferroni_n=1)
            ok = bool(boot.get("ci95_excludes_zero") and (cal.get("expected_net_r_all_decisions") or 0) > 0)
            holdout_detail.append({"hypothesis_id": s["hypothesis_id"], "cal": cal, "bootstrap": boot, "ok": ok})
            if ok:
                holdout_confirmed = True
        write_json(REPORTS_DIR / "holdout_results.json", holdout_detail)
    else:
        write_json(
            REPORTS_DIR / "holdout_results.json",
            {"opened": False, "reason": "no_discovery_validation_survivors — holdout remains sealed"},
        )

    learning = evaluate_learning(disc_events + val_events)
    write_json(REPORTS_DIR / "learning_comparison.json", learning)

    null_ok = NullPolicy().version == "phase54_null_policy_v1"

    payload = {
        "hypothesis_results": results,
        "learning": learning,
        "holdout_opened": holdout_opened,
        "holdout_confirmed": holdout_confirmed,
        "holdout_detail": holdout_detail,
        "null_policy_ok": null_ok,
    }
    verdict, reason = choose_verdict(payload)
    champion = CHAMPION_STATUS
    if verdict == "MARKET_INTELLIGENCE_EDGE_VALIDATED" and holdout_confirmed:
        champion = survivors[0]["hypothesis_id"]  # evidence-driven only
    else:
        champion = "NO_MODEL"

    runtime_s = time.perf_counter() - t0
    machine = {
        "recipe": RECIPE_ID,
        "verdict": verdict,
        "verdict_reason": reason,
        "champion": champion,
        "production": PRODUCTION_FINAL_ACTION,
        "audit_sha256": audit.get("audit_sha256"),
        "registry_sha256": registry.get("registry_sha256"),
        "split_sha256": splits.get("split_sha256"),
        "manifest": manifest,
        "hypothesis_results": results,
        "learning": learning,
        "holdout_opened": holdout_opened,
        "holdout_confirmed": holdout_confirmed,
        "null_policy_ok": null_ok,
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
    }
    machine["sha256"] = canonical_json_sha256({k: machine[k] for k in machine if k != "sha256"})
    write_json(REPORTS_DIR / "validation_results.json", machine)
    write_json(REPORTS_DIR / "baseline_comparison.json", {r["hypothesis_id"]: r.get("baselines") for r in results})
    write_json(REPORTS_DIR / "statistical_tests.json", {r["hypothesis_id"]: {"bootstrap": r.get("bootstrap"), "lodo": r.get("lodo"), "fail": r.get("fail_reasons")} for r in results})
    write_json(REPORTS_DIR / "rejections.json", [{"id": r["hypothesis_id"], "fail": r["fail_reasons"]} for r in results])

    lines = [
        "# Phase 58 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{champion}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Reason:** {reason}",
        f"**Generated:** {_utc()}",
        "",
        "## Research audit summary",
        f"- Audit SHA: `{audit.get('audit_sha256')}`",
        f"- Do-not-repeat families enforced: `{len(audit.get('do_not_repeat') or [])}`",
        f"- Standing policy unchanged through Phase57.1: NO_MODEL / WAIT",
        "",
        "## Preregistered hypotheses (frozen before eval)",
        f"- Registry SHA: `{registry.get('registry_sha256')}`",
        *[f"- `{h['id']}`: {h['claim'][:120]}..." for h in HYPOTHESES],
        "",
        "## Dataset splits",
        f"- Discovery days ({len(splits['discovery'])}): `{splits['discovery']}`",
        f"- Validation days ({len(splits['validation'])}): `{splits['validation']}`",
        f"- Holdout sealed ({len(splits['holdout_sealed'])}): `{splits['holdout_sealed']}`",
        f"- Events: discovery={len(disc_events)}, validation={len(val_events)}",
        f"- Split SHA: `{splits.get('split_sha256')}`",
        "",
        "## Hypothesis outcomes",
    ]
    for r in results:
        lines.append(
            f"- `{r['hypothesis_id']}`: discovery_survive=`{r.get('survives_discovery')}` "
            f"validation_survive=`{r.get('survives_validation')}` fail=`{r.get('fail_reasons')}` "
            f"mean_all=`{(r.get('discovery') or {}).get('expected_net_r_all_decisions')}` "
            f"trades=`{(r.get('discovery') or {}).get('n_trades')}` "
            f"boot_bonf_excl0=`{(r.get('bootstrap') or {}).get('bonferroni_excludes_zero')}`"
        )
    lines += [
        "",
        "## Learning comparison",
        f"- Demonstrates learning: `{learning.get('demonstrates_learning')}`",
        f"- Incremental vs WAIT: `{learning.get('incremental_vs_wait')}`",
        f"- Incremental bootstrap: `{learning.get('incremental_bootstrap')}`",
        f"- Shadow meta: `{learning.get('shadow_meta')}`",
        f"- Dual note: `{learning.get('dual_note')}`",
        f"- Stores merged: `{learning.get('stores_merged')}`",
        "",
        "## Holdout",
        f"- Opened: `{holdout_opened}` Confirmed: `{holdout_confirmed}`",
        f"- Detail: `{holdout_detail}`",
        "",
        "## NullPolicy / safety",
        f"- NullPolicy default intact: `{null_ok}`",
        "- No live MT5, no broker orders, no auto-start.",
        "- Commission/slippage remain UNKNOWN (not invented).",
        "",
        "## Remaining risks / limitations",
        "- MetaQuotes-Demo bid/ask ≠ live execution.",
        "- Date-block dependence; events within a day are not independent.",
        "- Prior-session feature uses previous archived session (not calendar-1).",
        "- Shadow learning unevaluable or unaligned — not forced into an edge claim.",
        "- Phase53 recommendation against strategy churn on this substrate remains relevant if no survivor.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase58.run_phase58",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "No Phase59 started.",
        "",
    ]
    write_text(REPORTS_DIR / "FINAL_REPORT.md", "\n".join(lines))
    write_text(
        DOCS_DIR / "PHASE_58_MARKET_INTELLIGENCE_RESEARCH.md",
        "\n".join(
            [
                "# Phase 58 — Autonomous Market Intelligence Research",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{champion}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `reports/phase58/FINAL_REPORT.md` and `research_audit.json`.",
                "",
            ]
        ),
    )

    print(verdict, reason)
    print("champion", champion)
    print("report", REPORTS_DIR / "FINAL_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
