"""Prompt 7 — independent strategy discovery orchestrator.

No production promotion. No Phase58 holdout access. No Prompt 8.
Does not stop the Prompt5 collector.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_bot.discovery.audit import build_research_audit
from signal_bot.discovery.candidates import preregistered_candidates, select_candidate
from signal_bot.discovery.constants import (
    CHAMPION_STATUS,
    DISCORD_ACTIONABLE,
    EVIDENCE_CLASS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    REGISTRY_PATH,
    REPORTS,
)
from signal_bot.discovery.data_feasibility import build_data_feasibility
from signal_bot.discovery.evaluation import (
    build_statistical_evaluation,
    dual_experience_architecture_note,
    load_h70_prompt04_stats,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.discover(
        str(PROJECT_ROOT / "src" / "signal_bot" / "discovery" / "tests"),
        top_level_dir=str(PROJECT_ROOT / "src"),
    )
    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "failure_names": [str(f[0]) for f in result.failures[:20]],
        "error_names": [str(e[0]) for e in result.errors[:20]],
    }


def build_bundle() -> dict[str, Any]:
    audit = build_research_audit()
    feasibility = build_data_feasibility()
    candidates = preregistered_candidates()
    selection = select_candidate(feasibility)
    stats_eval = build_statistical_evaluation(selection, feasibility)
    dual = dual_experience_architecture_note()
    h70 = load_h70_prompt04_stats()
    return {
        "generated_utc": _utc(),
        "prompt": "PROMPT_07",
        "champion": CHAMPION_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "order_send": ORDER_SEND,
        "discord_actionable": DISCORD_ACTIONABLE,
        "evidence_class": EVIDENCE_CLASS,
        "audit": audit,
        "feasibility": feasibility,
        "candidates": candidates,
        "selection": selection,
        "statistical_evaluation": stats_eval,
        "dual_experience": dual,
        "h70_reference": h70,
        "phase58_holdout_accessed": False,
        "implementation": selection.get("implementation"),
        "collector_modified": False,
        "prompt08_started": False,
    }


def write_reports(bundle: dict[str, Any], test_results: dict[str, Any]) -> list[str]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    audit = bundle["audit"]
    feas = bundle["feasibility"]
    sel = bundle["selection"]
    stat = bundle["statistical_evaluation"]
    live = feas.get("genuine_live_exness_xauusdm") or {}
    mq = feas.get("metaquotes_xauusd_archives") or {}
    created: list[str] = []

    # Registry JSON
    registry = {
        "prompt": "PROMPT_07",
        "generated_utc": bundle["generated_utc"],
        "primary_verdict": sel.get("primary_verdict"),
        "surviving_candidate_id": sel.get("surviving_candidate_id"),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "candidates": bundle["candidates"],
        "selection": sel,
        "evidence_class": EVIDENCE_CLASS,
        "independent_profitability_evidence": False,
        "implementation": "NONE",
        "phase58_holdout_accessed": False,
    }
    _json(REGISTRY_PATH, registry)
    created.append(str(REGISTRY_PATH))
    _json(REPORTS / "PROMPT_07_DISCOVERY_BUNDLE.json", {**bundle, "test_results": test_results})
    created.append(str(REPORTS / "PROMPT_07_DISCOVERY_BUNDLE.json"))

    p1 = REPORTS / "PROMPT_07_RESEARCH_AUDIT.md"
    _write(
        p1,
        "\n".join(
            [
                "# PROMPT 07 — Research Audit",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "## Verdict context",
                "",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- Accepted validated edge hypotheses: **{audit.get('n_accepted', 0)}**",
                f"- Phase45 rejected hypotheses: **{audit.get('n_rejected_phase45')}**",
                f"- Retired do-not-revive: **{audit.get('n_retired_do_not_revive')}**",
                "",
                "## Accepted hypotheses",
                "",
                "_None. No accepted validated trading edge exists in the registry._",
                "",
                "## Active production policy",
                "",
                f"`{audit.get('active_production_policy')}`",
                "",
                "## H70 status (excluded from revival)",
                "",
                "```json",
                json.dumps(audit.get("h70"), indent=2),
                "```",
                "",
                "## Excluded families for Prompt7",
                "",
                "```json",
                json.dumps(audit.get("excluded_families_for_prompt07"), indent=2),
                "```",
                "",
                "## Retired do-not-revive list",
                "",
                "```json",
                json.dumps(audit.get("retired_do_not_revive"), indent=2),
                "```",
                "",
                "## Preregistered unvalidated (Phase69)",
                "",
                "```json",
                json.dumps(audit.get("preregistered_unvalidated"), indent=2),
                "```",
                "",
                "## Previously tested feature themes",
                "",
                "\n".join(f"- {t}" for t in (audit.get("previously_tested_feature_themes") or [])),
                "",
                "## Phase58 holdout",
                "",
                f"- Sealed dates: `{audit.get('phase58_holdout_sealed')}`",
                f"- Accessed: `{audit.get('phase58_holdout_accessed')}`",
                "",
                "## Note",
                "",
                str(audit.get("note")),
                "",
            ]
        ),
    )
    created.append(str(p1))

    p2 = REPORTS / "PROMPT_07_DATA_FEASIBILITY.md"
    _write(
        p2,
        "\n".join(
            [
                "# PROMPT 07 — Data Feasibility",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "## Primary classification",
                "",
                f"- Evidence class for discovery: `{feas.get('evidence_class_for_discovery')}`",
                f"- Sufficient for independent validation: `{feas.get('sufficient_for_independent_validation')}`",
                "",
                "## Genuine live Exness XAUUSDm",
                "",
                "```json",
                json.dumps(live, indent=2),
                "```",
                "",
                "## Historical Exness backfill (journal)",
                "",
                "```json",
                json.dumps(feas.get("historical_exness_backfill_in_journal"), indent=2),
                "```",
                "",
                "## MetaQuotes XAUUSD archives (consumed)",
                "",
                "```json",
                json.dumps(mq, indent=2),
                "```",
                "",
                f"- Eligible consumed Phase53 days: **{mq.get('n_eligible_consumed')}**",
                f"- Dates: `{mq.get('phase53_eligible_consumed_days')}`",
                "",
                "## Sealed / inaccessible",
                "",
                "```json",
                json.dumps(feas.get("sealed_inaccessible"), indent=2),
                "```",
                "",
                "## Limitation",
                "",
                str(feas.get("limitation")),
                "",
                "## Collector",
                "",
                str(feas.get("collector_note")),
                "",
                "_Partial live bars / incomplete sessions are not an independent validation dataset._",
                "",
            ]
        ),
    )
    created.append(str(p2))

    p3 = REPORTS / "PROMPT_07_CANDIDATE_DISCOVERY.md"
    lines = [
        "# PROMPT 07 — Candidate Discovery",
        "",
        f"Generated: `{bundle['generated_utc']}`",
        "",
        "## Process",
        "",
        "- Hypotheses preregistered before outcome cherry-picking.",
        "- Rejected families not renamed or re-screened as new edges.",
        "- Archive confirmation forbidden; live independent sample insufficient.",
        "",
        f"## Candidates considered: {len(bundle['candidates'])}",
        "",
    ]
    for c in bundle["candidates"]:
        lines.extend(
            [
                f"### {c['candidate_id']} — {c['theme']}",
                "",
                f"1. **Economic rationale:** {c['economic_rationale']}",
                f"2. **Expected behavior:** {c['expected_behavior']}",
                f"3. **Persistence:** {c['persistence_argument']}",
                f"4. **Why not already rejected:** {c['why_not_already_rejected']}",
                f"5. **Required data:** {c['required_data']}",
                f"6. **Objective rules sketch:** {c['objective_rules_sketch']}",
                f"7. **Failure conditions:** {c['failure_conditions']}",
                f"8. **Expected frequency:** {c['expected_frequency']}",
                f"9. **Cost sensitivity:** {c['cost_sensitivity']}",
                f"- Disposition: `{c['preregister_disposition']}`",
            ]
        )
        if c.get("reject_reason"):
            lines.append(f"- Reject reason: {c['reject_reason']}")
        lines.append("")
    _write(p3, "\n".join(lines))
    created.append(str(p3))

    p4 = REPORTS / "PROMPT_07_STATISTICAL_EVALUATION.md"
    _write(
        p4,
        "\n".join(
            [
                "# PROMPT 07 — Statistical Evaluation",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"- Evidence class: `{stat.get('evidence_class')}`",
                f"- New candidates statistically evaluated as edge: **{stat.get('candidates_statistically_evaluated_as_new_edge')}**",
                "",
                "## Why no new formal screen",
                "",
                str(stat.get("reason")),
                "",
                "## H70 reference only (not revived)",
                "",
                "```json",
                json.dumps(stat.get("h70_reference_only_not_revived"), indent=2),
                "```",
                "",
                "## Costs",
                "",
                "```json",
                json.dumps(stat.get("cost_sensitivity"), indent=2),
                "```",
                "",
                f"- Independent profitability evidence: `{stat.get('independent_profitability_evidence')}`",
                f"- Phase58 holdout accessed: `{stat.get('phase58_holdout_accessed')}`",
                "",
                "## Multiple-testing control",
                "",
                str(stat.get("multiple_testing_control")),
                "",
            ]
        ),
    )
    created.append(str(p4))

    p5 = REPORTS / "PROMPT_07_CANDIDATE_SELECTION.md"
    _write(
        p5,
        "\n".join(
            [
                "# PROMPT 07 — Candidate Selection",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"## Primary verdict: `{sel.get('primary_verdict')}`",
                "",
                f"- Surviving candidate: `{sel.get('surviving_candidate_id')}`",
                f"- Champion: `{sel.get('champion')}`",
                f"- Production: `{sel.get('production')}`",
                f"- Evidence class: `{sel.get('evidence_class')}`",
                f"- Net profitability: `{sel.get('net_profitability')}`",
                f"- Independent profitability evidence: `{sel.get('independent_profitability_evidence')}`",
                f"- Implementation: `{sel.get('implementation')}`",
                "",
                f"- Hypotheses investigated: **{sel.get('n_hypotheses_investigated')}**",
                f"- Rejected: **{sel.get('n_rejected')}**",
                f"- Held pending data: **{sel.get('n_held_pending_data')}** `{sel.get('held_ids')}`",
                "",
                "## Rejected IDs",
                "",
                "```json",
                json.dumps(sel.get("rejected_ids"), indent=2),
                "```",
                "",
                "## Rationale",
                "",
                str(sel.get("rationale")),
                "",
                "## Dual-experience architecture (preserved)",
                "",
                "```json",
                json.dumps(bundle.get("dual_experience"), indent=2),
                "```",
                "",
                "## Safety invariants",
                "",
                f"- order_send: `{ORDER_SEND}`",
                f"- Discord actionable: `{DISCORD_ACTIONABLE}`",
                "- Live trading: NOT_AUTHORIZED",
                "- Automated orders: DISABLED",
                "- Broker collection: READ_ONLY",
                "- Risk policy: UNAPPROVED",
                "",
                "_Prompt 8 not started._",
                "",
            ]
        ),
    )
    created.append(str(p5))

    p6 = REPORTS / "PROMPT_07_TEST_RESULTS.md"
    _write(
        p6,
        "\n".join(
            [
                "# PROMPT 07 — Test Results",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(test_results, indent=2),
                "```",
                "",
                "## Commands",
                "",
                "```text",
                "python -m signal_bot.discovery.run_prompt07",
                "python -m unittest discover -s src/signal_bot/discovery/tests -t src",
                "```",
                "",
                f"- Collector modified: `{bundle.get('collector_modified')}`",
                f"- Prompt8 started: `{bundle.get('prompt08_started')}`",
                f"- Artificial strategy module created: `False`",
                "",
            ]
        ),
    )
    created.append(str(p6))
    return created


def main() -> int:
    if str(PROJECT_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
    bundle = build_bundle()
    test_results = _run_tests()
    created = write_reports(bundle, test_results)
    print(
        json.dumps(
            {
                "primary_verdict": bundle["selection"]["primary_verdict"],
                "surviving_candidate_id": bundle["selection"]["surviving_candidate_id"],
                "champion": CHAMPION_STATUS,
                "tests_ok": test_results.get("ok"),
                "files": created,
            },
            indent=2,
        )
    )
    return 0 if test_results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
