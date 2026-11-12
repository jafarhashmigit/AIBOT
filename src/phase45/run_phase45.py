"""Phase 45 runner — research architecture audit (no strategy evaluation)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase45.audits import (
    audit_data_execution,
    audit_decision_pipeline,
    audit_features,
    audit_learning,
    audit_prediction_targets,
    audit_statistics,
)
from phase45.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PHASE44_VALIDATION_DATES_LOCKED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    RETIRED_STRATEGIES,
    TELEGRAM_MESSAGES_SENT,
)
from phase45.experiment_registry import build_experiment_registry
from phase45.gaps import build_gap_analysis
from phase45.independent import verify_independent
from phase45.progress import write_json
from phase45.qualification import decide_verdict
from phase45.roadmap import build_roadmap
from phase45.taxonomy import build_failure_taxonomy

UTC = timezone.utc


def _report(
    *,
    registry: dict[str, Any],
    audits: dict[str, Any],
    taxonomy: dict[str, Any],
    gaps: dict[str, Any],
    roadmap: dict[str, Any],
    indep: dict[str, Any],
    verdict: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    lines = [
        "# Phase 45 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict.get('final_verdict')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## Executive finding",
        f"- Primary root cause: `{taxonomy.get('primary_root_cause')}`",
        f"- Also true: `{verdict.get('also_true')}`",
        f"- Reason: {verdict.get('reason')}",
        "",
        "## 1. Historical research audit",
        f"- Phase verdicts reloaded: `{registry.get('n_phase_verdicts_reloaded')}`",
        f"- Strategies registered: `{registry.get('n_strategies')}`",
        f"- Hypotheses registered: `{registry.get('n_hypotheses')}`",
        f"- Retired / do-not-revive count: `{len(registry.get('retired_do_not_revive') or [])}`",
        f"- Explicitly retired strategies: `{list(RETIRED_STRATEGIES)}`",
        "",
        "### Phase verdict timeline (reloaded)",
    ]
    for row in registry.get("phase_verdicts") or []:
        lines.append(
            f"- `{row.get('phase')}`: `{row.get('final_verdict')}` "
            f"(champion=`{row.get('champion')}`, production=`{row.get('production')}`)"
        )
    lines += ["", "### Research overlaps"]
    for o in registry.get("research_overlaps") or []:
        lines.append(f"- **{o['theme']}** — phases `{o['phases']}` — {o['information_gain_assessment']}")

    lines += ["", "## 2. Prediction target audit"]
    for f in (audits.get("prediction") or {}).get("findings") or []:
        lines.append(f"- {f.get('finding') or f}")
    lines.append(f"- Suitability: `{(audits.get('prediction') or {}).get('suitability_verdict')}`")
    lines.append(f"- Math note: `{(audits.get('prediction') or {}).get('math_note')}`")

    lines += ["", "## 3. Feature intelligence audit"]
    for f in (audits.get("features") or {}).get("findings") or []:
        if "category" in f:
            lines.append(f"- `{f['category']}`: {f.get('assessment')}")
        elif "leakage_risks" in f:
            lines.append(f"- Leakage risks: {f['leakage_risks']}")

    lines += ["", "## 4. Autonomous learning audit"]
    learn = audits.get("learning") or {}
    lines.append(f"- Genuinely adaptive: `{learn.get('genuinely_adaptive')}`")
    for f in learn.get("findings") or []:
        if "store" in f:
            lines.append(f"- Store `{f['store']}`: {f.get('status')} — {f.get('assessment')}")
        elif "finding" in f:
            lines.append(f"- {f['finding']}")

    lines += ["", "## 5. Decision intelligence audit"]
    for f in (audits.get("decision") or {}).get("findings") or []:
        lines.append(f"- `{f.get('stage')}`: {f.get('status')} — gap: {f.get('gap')}")
    lines.append(f"- Blocking missing: `{(audits.get('decision') or {}).get('blocking_missing_components')}`")

    lines += ["", "## 6. Data and execution audit"]
    for f in (audits.get("data") or {}).get("findings") or []:
        lines.append(f"- {f.get('finding')}")
    lines.append(f"- Data blocks research: `{(audits.get('data') or {}).get('data_blocks_research')}`")

    lines += ["", "## 7. Statistical integrity"]
    for f in (audits.get("statistics") or {}).get("findings") or []:
        lines.append(f"- {f}")

    lines += ["", "## Failure taxonomy"]
    for t in taxonomy.get("taxonomy") or []:
        lines.append(f"- `{t['id']}` ({t['severity']}): {t['name']} — {t['description']}")

    lines += ["", "## Architecture gaps"]
    for g in gaps.get("gaps") or []:
        lines.append(f"- `{g['gap_id']}` {g['title']} → {g['required_capability']}")

    lines += ["", "## Strategic roadmap (next milestones)"]
    for m in roadmap.get("milestones") or []:
        lines.append(f"### {m['id']}: {m['title']}")
        lines.append(f"- Problem: {m['problem']}")
        lines.append(f"- Why profit: {m['why_profitability']}")
        lines.append(f"- Success: {m['success_criteria']}")
        lines.append(f"- Failure: {m['failure_criteria']}")
        lines.append(f"- New independent data needed: `{m['needs_new_independent_data']}`")

    lines += [
        "",
        "## Locked resources",
        f"- Phase44 validation dates (forbidden for discovery): `{PHASE44_VALIDATION_DATES_LOCKED}`",
        f"- Retired strategies: `{list(RETIRED_STRATEGIES)}`",
        "",
        "## Independent verification",
        f"- OK: `{indep.get('ok')}` method=`{indep.get('method')}`",
        "",
        "## Safety",
        "- No Phase0–44 modifications; no strategy evaluation; no MT5 live; no orders; no packages; no holdout; no commits.",
        f"- Counters orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime: `{runtime.get('DURATION')}`",
        "",
        "## Final verdict",
        f"- `{verdict.get('final_verdict')}`",
        f"- {verdict.get('reason')}",
        "",
    ]
    return "\n".join(lines)


def _docs(verdict: dict[str, Any], roadmap: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_45_RESEARCH_ARCHITECTURE_AUDIT.md").write_text(
        "\n".join(
            [
                "# Phase 45 — Research Architecture Audit",
                "",
                "Forensic audit of Phases 0–44. No new strategy development.",
                "",
                f"**Verdict:** `{verdict.get('final_verdict')}`",
                f"**Redirect milestones:** `{roadmap.get('priority_order')}`",
                "",
                "## Non-negotiables",
                "- Champion remains NO_MODEL; Production remains WAIT.",
                "- Do not revive H13_C / mean_reversion / H42_* / H44_* rejects.",
                "- Phase44 validation dates stay closed for discovery.",
                "- Do not weaken statistical thresholds.",
                "- Stop indicator-permutation research; execute M1–M5 roadmap.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
                "See `reports/phase45/FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)

    registry = build_experiment_registry()
    audits = {
        "prediction": audit_prediction_targets(),
        "features": audit_features(),
        "learning": audit_learning(),
        "decision": audit_decision_pipeline(),
        "data": audit_data_execution(),
        "statistics": audit_statistics(),
    }
    write_json("audits_bundle.json", {k: {"ok": True} for k in audits})

    taxonomy = build_failure_taxonomy()
    gaps = build_gap_analysis(audits, taxonomy)
    roadmap = build_roadmap()

    indep = verify_independent(registry)
    write_json("independent_verification.json", indep)

    verdict = decide_verdict(
        taxonomy=taxonomy,
        learning=audits["learning"],
        data=audits["data"],
        gaps=gaps,
    )
    write_json("qualification.json", verdict)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 45,
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict.get("final_verdict"),
        "verdict_reason": verdict.get("reason"),
        "also_true": verdict.get("also_true"),
        "primary_root_cause": taxonomy.get("primary_root_cause"),
        "n_phase_verdicts": registry.get("n_phase_verdicts_reloaded"),
        "n_strategies": registry.get("n_strategies"),
        "n_hypotheses": registry.get("n_hypotheses"),
        "roadmap_priority": roadmap.get("priority_order"),
        "independent_ok": indep.get("ok"),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "no_strategy_evaluation": True,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "FINAL_REPORT.md").write_text(
        _report(
            registry=registry,
            audits=audits,
            taxonomy=taxonomy,
            gaps=gaps,
            roadmap=roadmap,
            indep=indep,
            verdict=verdict,
            runtime=runtime,
        )
        + "\n",
        encoding="utf-8",
    )
    _docs(verdict, roadmap)
    print(json.dumps(final, indent=2))
    return final


if __name__ == "__main__":
    main()
