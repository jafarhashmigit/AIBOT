"""Prompt 9 — final candidate audit & selection. No Prompt 10 auto-start. No fake champion."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_bot.final_selection.audit_matrix import build_candidate_evidence_matrix
from signal_bot.final_selection.c07_evaluation import evaluate_c07_a
from signal_bot.final_selection.constants import (
    CHAMPION_STATUS,
    DISCORD_ACTIONABLE,
    H70_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    REPORTS,
    RISK_POLICY,
    VERDICT_NONE,
)
from signal_bot.final_selection.selection import select_champion
from signal_bot.final_selection.validation import (
    build_cost_and_risk_assessment,
    build_validation_results,
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
    suite = unittest.TestSuite()
    roots = [
        PROJECT_ROOT / "src" / "signal_bot" / "final_selection" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "execution_economics" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "orchestrator" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "discovery" / "tests",
        PROJECT_ROOT / "src" / "phase54" / "tests",
        PROJECT_ROOT / "src" / "phase56" / "tests",
        PROJECT_ROOT / "src" / "phase67" / "tests",
    ]
    p69 = PROJECT_ROOT / "src" / "phase69" / "tests"
    if p69.is_dir():
        roots.append(p69)
    for root in roots:
        if root.is_dir():
            suite.addTests(loader.discover(str(root), top_level_dir=str(PROJECT_ROOT / "src")))
    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "failure_names": [str(f[0]) for f in result.failures[:25]],
        "error_names": [str(e[0]) for e in result.errors[:25]],
    }


def build_bundle() -> dict[str, Any]:
    matrix = build_candidate_evidence_matrix()
    data = matrix.get("data") or {}
    economics = matrix.get("execution_economics") or {}
    c07 = evaluate_c07_a(
        live_complete_dates=int(data.get("complete_independent_asia_london_dates") or 0),
        live_m5=int(data.get("live_m5") or 0),
    )
    live = {
        "n_complete_independent_live_dates": data.get("complete_independent_asia_london_dates"),
        "unique_newly_closed_live_m5_bars": data.get("live_m5"),
        "live_quote_observations": data.get("live_quotes"),
    }
    validation = build_validation_results(c07=c07, economics=economics, live=live)
    selection = select_champion(matrix=matrix, c07=c07, economics=economics)
    cost_risk = build_cost_and_risk_assessment(economics, selection)

    # Spec document: either frozen rules or explicit rejection
    spec = {
        "candidate_id": "C07_A_SESSION_OPEN_DISCOVERY",
        "status": c07.get("disposition"),
        "frozen_rules": None,
        "unresolved_parameters": c07.get("unresolved_parameters"),
        "reason": c07.get("reason"),
        "champion": CHAMPION_STATUS,
    }

    impl = {
        "champion_module_implemented": False,
        "null_policy_retained": True,
        "phase54_integration": "unchanged — NullPolicy WAIT",
        "prompt6_orchestrator": "shadow/WAIT only; actionable gate remains closed",
        "discord_actionable": DISCORD_ACTIONABLE,
        "fake_champion_avoided": True,
        "policies_dir_created": False,
    }

    handoff = {
        "prompt10_may_safely_deliver": [
            "Operational packaging of READ_ONLY collector + shadow orchestrator",
            "Documentation of NO_MODEL / WAIT production posture",
            "Test harness and report archive consolidation",
            "Explicit blocker list for any future research (outside 10-prompt plan)",
        ],
        "prompt10_must_not": [
            "Promote a champion without new independent evidence",
            "Enable actionable Discord BUY/SELL",
            "Enable order_send or live/demo orders",
            "Access Phase58 holdout",
            "Treat unknown costs as zero",
            "Claim profitability",
        ],
        "blocked_for_signal_delivery": [
            "No qualified strategy",
            "Champion NO_MODEL",
            "NET_PROFITABILITY NOT_ESTABLISHED",
            "Risk policy UNAPPROVED",
            "Discord actionable DISABLED",
            "0 complete independent Asia+London live dates",
            "C07_A unimplementable from evidence",
        ],
        "primary_verdict": selection.get("primary_verdict"),
    }

    return {
        "generated_utc": _utc(),
        "prompt": "PROMPT_09",
        "primary_verdict": selection.get("primary_verdict"),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "h70": H70_STATUS,
        "order_send": ORDER_SEND,
        "risk_policy": RISK_POLICY,
        "discord_actionable": DISCORD_ACTIONABLE,
        "matrix": matrix,
        "c07": c07,
        "specification": spec,
        "validation": validation,
        "cost_risk": cost_risk,
        "selection": selection,
        "implementation": impl,
        "handoff": handoff,
        "prompt10_started": False,
    }


def write_reports(bundle: dict[str, Any], tests: dict[str, Any]) -> list[str]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    _json(REPORTS / "PROMPT_09_BUNDLE.json", {**bundle, "test_results": tests})
    created.append(str(REPORTS / "PROMPT_09_BUNDLE.json"))

    m = bundle["matrix"]
    c07 = bundle["c07"]
    sel = bundle["selection"]
    val = bundle["validation"]
    cr = bundle["cost_risk"]
    impl = bundle["implementation"]
    hand = bundle["handoff"]
    spec = bundle["specification"]

    files = {
        "PROMPT_09_FINAL_CANDIDATE_AUDIT.md": "\n".join(
            [
                "# PROMPT 09 — Final Candidate Audit",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Primary verdict: `{bundle['primary_verdict']}`",
                "",
                "## Accepted validated edges",
                "",
                f"**{m.get('n_accepted_validated_edges')}** — none.",
                "",
                "## Candidate / evidence matrix",
                "",
                "```json",
                json.dumps(m.get("matrix_rows"), indent=2),
                "```",
                "",
                "## Data",
                "",
                "```json",
                json.dumps(m.get("data"), indent=2),
                "```",
                "",
                "## Execution economics snapshot",
                "",
                "```json",
                json.dumps(m.get("execution_economics"), indent=2),
                "```",
                "",
                f"- Phase58 holdout sealed: `{m.get('phase58_holdout_sealed')}`",
                f"- Holdout accessed: `False`",
                "",
            ]
        ),
        "PROMPT_09_STRATEGY_SPECIFICATION.md": "\n".join(
            [
                "# PROMPT 09 — Strategy Specification",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"## C07_A status: `{spec.get('status')}`",
                "",
                "No frozen production strategy specification exists.",
                "",
                "```json",
                json.dumps(spec, indent=2),
                "```",
                "",
                "### Unresolved parameters (cannot invent)",
                "",
                "\n".join(f"- `{p}`" for p in (spec.get("unresolved_parameters") or [])),
                "",
                f"Champion remains `{CHAMPION_STATUS}`. Production remains `{PRODUCTION_FINAL_ACTION}`.",
                "",
            ]
        ),
        "PROMPT_09_VALIDATION_RESULTS.md": "\n".join(
            [
                "# PROMPT 09 — Validation Results",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(val, indent=2),
                "```",
                "",
                "Confirmatory validation was **not** executed for C07_A because rules are not "
                "evidence-derivable and independent live sample is below floor. "
                "Consumed MetaQuotes archives were **not** used as confirmation.",
                "",
            ]
        ),
        "PROMPT_09_COST_AND_RISK_ASSESSMENT.md": "\n".join(
            [
                "# PROMPT 09 — Cost and Risk Assessment",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(cr, indent=2),
                "```",
                "",
            ]
        ),
        "PROMPT_09_CHAMPION_SELECTION.md": "\n".join(
            [
                "# PROMPT 09 — Champion Selection",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"## Primary verdict: `{sel.get('primary_verdict')}`",
                "",
                f"- Champion candidate: `{sel.get('champion_candidate_id')}`",
                f"- Champion status: `{sel.get('champion_status')}`",
                f"- Production: `{sel.get('production')}`",
                f"- Thresholds lowered: `{sel.get('thresholds_lowered')}`",
                "",
                "## Checklist",
                "",
                "```json",
                json.dumps(sel.get("checklist"), indent=2),
                "```",
                "",
                "## C07 disposition",
                "",
                f"`{sel.get('c07_disposition')}`",
                "",
                str(sel.get("c07_reason")),
                "",
                "## Alternates",
                "",
                "```json",
                json.dumps(sel.get("alternates_considered"), indent=2),
                "```",
                "",
                "## Rationale",
                "",
                str(sel.get("rationale")),
                "",
            ]
        ),
        "PROMPT_09_IMPLEMENTATION_REPORT.md": "\n".join(
            [
                "# PROMPT 09 — Implementation Report",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(impl, indent=2),
                "```",
                "",
                "No champion strategy module was created. Phase54 NullPolicy and Prompt6 shadow gate unchanged.",
                "",
            ]
        ),
        "PROMPT_09_TEST_RESULTS.md": "\n".join(
            [
                "# PROMPT 09 — Test Results",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(tests, indent=2),
                "```",
                "",
                "## Commands",
                "",
                "```text",
                ".venv\\Scripts\\python.exe -m signal_bot.final_selection.run_prompt09",
                "```",
                "",
                f"- Prompt10 started: `{bundle.get('prompt10_started')}`",
                "",
            ]
        ),
        "PROMPT_09_HANDOFF_TO_PROMPT10.md": "\n".join(
            [
                "# PROMPT 09 — Handoff to Prompt 10",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Primary verdict: `{bundle['primary_verdict']}`",
                "",
                "## What Prompt10 can safely deliver",
                "",
                "\n".join(f"- {x}" for x in (hand.get("prompt10_may_safely_deliver") or [])),
                "",
                "## What Prompt10 must not do",
                "",
                "\n".join(f"- {x}" for x in (hand.get("prompt10_must_not") or [])),
                "",
                "## Blocked for actionable signal delivery",
                "",
                "\n".join(f"- {x}" for x in (hand.get("blocked_for_signal_delivery") or [])),
                "",
                "## Safety snapshot",
                "",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- order_send: `{ORDER_SEND}`",
                f"- Discord actionable: `{DISCORD_ACTIONABLE}`",
                f"- Risk: `{RISK_POLICY}`",
                f"- H70: `{H70_STATUS}`",
                "",
                "_Do not start Prompt10 automatically from this package._",
                "",
            ]
        ),
    }

    for name, body in files.items():
        path = REPORTS / name
        _write(path, body)
        created.append(str(path))
    return created


def main() -> int:
    if str(PROJECT_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
    bundle = build_bundle()
    assert bundle["primary_verdict"] in (
        "QUALIFIED_CANDIDATE_READY_FOR_FINAL_AUDIT",
        "NO_QUALIFIED_STRATEGY",
        "INSUFFICIENT_EVIDENCE",
        "SAFETY_INVARIANT_FAILURE",
    )
    tests = _run_tests()
    files = write_reports(bundle, tests)
    print(
        json.dumps(
            {
                "primary_verdict": bundle["primary_verdict"],
                "champion": bundle["champion"],
                "c07_disposition": bundle["c07"]["disposition"],
                "implementation": bundle["implementation"]["champion_module_implemented"],
                "tests_ok": tests.get("ok"),
                "tests_run": tests.get("tests_run"),
                "files": files,
            },
            indent=2,
        )
    )
    return 0 if tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
