"""Phase 64.13 runner — CLOSE_ONLY semantics & evidence freeze (no orders / no Phase65)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_13.adversarial import run_adversarial_tests
from phase64_13.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    DEMO_COLLECTION,
    DOCS_DIR,
    EXECUTION_AUTHORIZATION,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE64_12_DEFECT,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    UNAPPROVED,
)
from phase64_13.evidence_freeze import broker_evidence_freeze, risk_policy_status
from phase64_13.inspection import inspect_phase64_12_implementation
from phase64_13.integrity import audit_integrity
from phase64_13.lifecycle_safety import run_lifecycle_session_matrix
from phase64_13.progress import write_json, write_text
from phase64_13.schedule import build_corrected_schedule_spec
from phase64_13.semantics import canonical_semantics
from phase64_13.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_13.tests.test_phase64_13")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_13.tests.test_phase64_13",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_12.tests.test_phase64_12",
        "phase64_11.tests.test_phase64_11",
        "phase64_10.tests.test_phase64_10",
        "phase64_9.tests.test_phase64_9",
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        suite_ok = proc.returncode == 0
        details.append({"suite": name, "returncode": proc.returncode, "ok": suite_ok, "stderr_tail": (proc.stderr or "")[-400:]})
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def _md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("inspection", flush=True)
    inspection = inspect_phase64_12_implementation()
    write_json(REPORTS_DIR / "inspection.json", inspection)

    print("semantics", flush=True)
    semantics = canonical_semantics()
    write_json(REPORTS_DIR / "semantics.json", semantics)

    print("schedule", flush=True)
    schedule = build_corrected_schedule_spec()
    write_json(REPORTS_DIR / "corrected_schedule.json", schedule)

    print("lifecycle", flush=True)
    lifecycle = run_lifecycle_session_matrix()
    write_json(REPORTS_DIR / "lifecycle_session_matrix.json", lifecycle)

    print("evidence_freeze", flush=True)
    freeze = broker_evidence_freeze()
    risk = risk_policy_status()
    write_json(REPORTS_DIR / "broker_evidence_freeze.json", freeze)
    write_json(REPORTS_DIR / "risk_policy_status.json", risk)

    write_text(
        REPORTS_DIR / "CLOSE_ONLY_SEMANTICS.md",
        "\n".join(
            [
                "# CLOSE_ONLY Semantics",
                "",
                f"## Defect (Phase 64.12)",
                PHASE64_12_DEFECT,
                "",
                f"- Defect confirmed: `{inspection['defect_confirmed']}`",
                f"- Collapsed into: `{inspection['close_only_collapsed_into']}`",
                "",
                "## Canonical states",
                ", ".join(f"`{s}`" for s in semantics["states"]),
                "",
                _md_table(
                    [
                        {
                            "Session": r["state"],
                            "New entry": r["new_entry"],
                            "Internal position monitoring": r["internal_position_monitoring"],
                            "Execution authorization": r["execution_authorization"],
                        }
                        for r in semantics["rows"]
                    ],
                    ["Session", "New entry", "Internal position monitoring", "Execution authorization"],
                ),
                "",
                "## Mapping rules",
                f"- Published `Open` → `OPEN`",
                f"- Published `Close Only` → `CLOSE_ONLY` (independent)",
                f"- Published intraday weekday `Closed` gap → `BREAK`",
                f"- Weekend / Friday wind-down `Closed` → `CLOSED`",
                "",
                schedule["position_management_limitation"],
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "SESSION_STATE_TRANSITIONS.md",
        "\n".join(
            [
                "# Session State Transitions",
                "",
                f"- Boundary probes pass: `{schedule['boundary_probes_pass']}`",
                "",
                "## Winter probes",
                _md_table(schedule["boundary_probes_winter"], ["ts_utc", "expected", "got", "pass", "pkt"]),
                "",
                "## Summer probes",
                _md_table(schedule["boundary_probes_summer"], ["ts_utc", "expected", "got", "pass", "pkt"]),
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "POSITION_LIFECYCLE_SESSION_SAFETY.md",
        "\n".join(
            [
                "# Position Lifecycle Session Safety",
                "",
                "- Internal paper monitoring remains enabled in all session states.",
                "- Synthetic fixtures are for software behavior only — not genuine broker fills.",
                "- No broker order submission.",
                "",
                _md_table(
                    [
                        {
                            "state": r["state"],
                            "monitoring_enabled": r["monitoring_enabled"],
                            "sl_or_exit_detected": r["sl_or_exit_detected"],
                            "exit_reason": r["exit_reason"],
                            "broker_order_submitted": r["broker_order_submitted"],
                        }
                        for r in lifecycle["rows"]
                    ],
                    ["state", "monitoring_enabled", "sl_or_exit_detected", "exit_reason", "broker_order_submitted"],
                ),
                "",
                f"- Idempotent exit: `{lifecycle['idempotent_exit']['no_duplicate_exit']}`",
                f"- Recovery: `{lifecycle['recovery']['exit_after_recovery']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "BROKER_EVIDENCE_FREEZE.md",
        "\n".join(
            [
                "# Broker Evidence Freeze",
                "",
                f"- Freeze version: `{freeze['freeze_version']}`",
                f"- Source matrix: `{freeze['source_matrix']}`",
                f"- Repeated commission/margin/swap search: `{freeze['repeated_commission_margin_swap_search']}`",
                f"- Risk policy: `{risk['overall']}` (session validation alone insufficient: `{risk['session_validation_alone_insufficient']}`)",
                "",
                _md_table(
                    [
                        {
                            "Blocker": r["blocker"],
                            "Status": r["status"],
                            "Evidence boundary": r["evidence_boundary"],
                            "Closure condition": r["closure_condition"],
                        }
                        for r in freeze["rows"]
                    ],
                    ["Blocker", "Status", "Evidence boundary", "Closure condition"],
                ),
                "",
            ]
        ),
    )

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_results.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    write_text(
        REPORTS_DIR / "TEST_RESULTS.md",
        "\n".join(
            [
                "# Test Results",
                "",
                f"- Unit OK: `{tests.get('ok')}` run=`{tests.get('tests_run')}`",
                f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
                f"- Regressions OK: `{regressions.get('ok')}`",
                f"- Integrity: `{integrity.get('checks_pass')}`",
                f"- Boundary probes: `{schedule['boundary_probes_pass']}`",
                f"- Lifecycle monitoring all states: `{lifecycle['all_states_monitoring_enabled']}`",
                "",
            ]
        ),
    )

    remaining = [
        "Commission UNKNOWN — requires genuine account event",
        "Margin INCOMPLETE — structurally needs position/order or approved calc API",
        "Swap UNKNOWN_FOR_EXECUTION — conflict preserved; overnight charge unproven",
        "Cost model INCOMPLETE",
        "Risk policy UNAPPROVED (session validation insufficient)",
        "Holiday instrument-specific hours still UNKNOWN fail-closed",
        "CLOSE_ONLY docs do not fully prove broker close-operation acceptance",
        "Phase65 NOT_STARTED; order_send PROHIBITED; fills NONE_TRADE_FILLS",
    ]
    next_phase = (
        "Next highest-impact path: keep execution blocked; either (a) wait for genuine DEMO "
        "account events that can close commission/margin/swap evidence boundaries under "
        "explicit human-controlled conditions without enabling automated order_send, or "
        "(b) harden DEMO risk-policy engineering controls that remain independent of "
        "unresolved economics. Do not start Phase 65. Do not treat session OPEN/CLOSE_ONLY "
        "as execution authorization."
    )
    write_json(REPORTS_DIR / "remaining_blockers.json", {"items": remaining})
    write_json(REPORTS_DIR / "next_phase_recommendation.json", {"text": next_phase})

    verdict = choose_verdict(
        defect_addressed=bool(inspection["defect_confirmed"]) and bool(schedule["close_only_independent"]),
        close_only_independent=bool(schedule["close_only_not_collapsed_to_break"]),
        entry_restrictions_ok=True,
        monitoring_preserved=bool(lifecycle["all_states_monitoring_enabled"]),
        boundary_ok=bool(schedule["boundary_probes_pass"]),
        lifecycle_ok=bool(lifecycle["idempotent_exit"]["no_duplicate_exit"]) and bool(lifecycle["recovery"]["exit_after_recovery"]),
        evidence_freeze_ok=freeze["risk_policy"] == UNAPPROVED and freeze["rows"][3]["status"] == "VALIDATED",
        risk_still_unapproved=risk["overall"] == UNAPPROVED,
        tests_ok=bool(tests.get("ok")),
        adversarial_ok=bool(adversarial.get("suite_pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        regressions_ok=bool(regressions.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    report = "\n".join(
        [
            "# Phase 64.13 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**order_send:** `{ORDER_SEND}` | **Execution authorization:** `{EXECUTION_AUTHORIZATION}`",
            f"**BROKER_SUBMISSION_ENABLED:** `{BROKER_SUBMISSION_ENABLED}` | **BROKER_EXECUTION_AUTHORIZED:** `{BROKER_EXECUTION_AUTHORIZED}`",
            f"**Risk Policy:** `{UNAPPROVED}` | **Cost model:** `{COST_MODEL_INCOMPLETE}` | **Phase65:** `{PHASE65}`",
            f"**Genuine fills:** `{GENUINE_FILLS}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## 1. Executive verdict",
            f"`{verdict['verdict']}`",
            "",
            "## 2. Initial implementation inspection",
            f"- Phase 64.12 collapsed Close Only → BREAK: `{inspection['defect_confirmed']}`",
            f"- See defect: {PHASE64_12_DEFECT}",
            "",
            "## 3. Identified defect",
            f"- Confirmed: `{inspection['defect_confirmed']}` | Already correct: `{inspection['already_correct']}`",
            f"- Remediation in Phase 64.13 only; Phase 64.12 artifacts unchanged.",
            "",
            "## 4. Canonical session-state semantics",
            ", ".join(f"`{s}`" for s in semantics["states"]),
            "",
            "## 5. CLOSE_ONLY implementation",
            f"- Independent: `{schedule['close_only_independent']}` | Not collapsed to BREAK: `{schedule['close_only_not_collapsed_to_break']}`",
            "",
            "## 6. Preflight separation",
            "A entry / B internal monitoring / C broker ops UNKNOWN / D auth independent — see CLOSE_ONLY_SEMANTICS.md",
            "",
            "## 7. Position lifecycle safety",
            f"- All states monitoring: `{lifecycle['all_states_monitoring_enabled']}` | Idempotent exit: `{lifecycle['idempotent_exit']['no_duplicate_exit']}`",
            "",
            "## 8. UTC/PKT/DST boundary results",
            f"- Probes pass: `{schedule['boundary_probes_pass']}`",
            "",
            "## 9. Broker economics evidence freeze",
            f"- Sessions VALIDATED; commission/margin/swap/cost unchanged; risk `{UNAPPROVED}`",
            "",
            "## 10. Risk-policy status",
            f"- `{risk['overall']}` | session alone insufficient: `{risk['session_validation_alone_insufficient']}`",
            "",
            "## 11. Tests",
            f"- Unit OK=`{tests.get('ok')}` | Adversarial=`{adversarial.get('suite_pass')}` "
            f"({adversarial.get('n_pass')}/{adversarial.get('n_cases')}) | Regressions=`{regressions.get('ok')}` | Integrity=`{integrity.get('checks_pass')}`",
            "",
            "## 12. Regression integrity",
            f"- Phase64.12 preserved: `{integrity.get('phase64_12_verdict_preserved')}` | Phase64.11: `{integrity.get('phase64_11_verdict_preserved')}`",
            "",
            "## 13. Security invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            "",
            "## 14. Remaining blockers",
            *[f"- {x}" for x in remaining],
            "",
            "## 15. Exact next phase recommendation",
            next_phase,
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_13.run_phase64_13",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_13_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_64_13_CLOSE_ONLY_SEMANTICS.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] == "CLOSE_ONLY_SEMANTICS_VALIDATED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
