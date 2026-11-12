"""Phase 57 — independent reliability & execution integrity validation runner."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase57.constants import (
    CHAMPION_STATUS,
    CRITICAL_INVARIANTS,
    DOCS_DIR,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase57.progress import write_json, write_text
from phase57.suite import run_full_suite


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromName("phase57.tests.test_phase57"))
    # Regression: prior phases must remain green (do not weaken)
    suite.addTests(loader.loadTestsFromName("phase56.tests.test_phase56"))
    suite.addTests(loader.loadTestsFromName("phase55.tests.test_phase55"))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    failures = [{"test": str(t), "detail": str(d)} for t, d in result.failures]
    errors = [{"test": str(t), "detail": str(d)} for t, d in result.errors]
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
        "failure_details": failures[:20],
        "error_details": errors[:20],
    }


def build_final_report(payload: dict[str, Any], tests: dict[str, Any], runtime_s: float) -> str:
    crit = payload.get("critical_invariants") or {}
    lines = [
        "# Phase 57 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{payload.get('verdict')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Reason:** {payload.get('verdict_reason')}",
        f"**Generated:** {_utc()}",
        "",
        "## Critical invariants",
        "",
    ]
    for k in CRITICAL_INVARIANTS:
        v = crit.get(k) or {}
        mark = "PASS" if v.get("ok") else "FAIL"
        lines.append(f"- `{k}`: **{mark}** — `{v}`")
    lines += [
        "",
        "## Lifecycle integrity",
        f"- ok: `{payload.get('lifecycle', {}).get('ok')}`",
        f"- actions: `{payload.get('lifecycle', {}).get('actions')}`",
        f"- closed_n: `{payload.get('lifecycle', {}).get('closed_n')}`",
        "",
        "## Crash & recovery",
        f"- stages: `{payload.get('crash', {}).get('stages')}`",
        f"- all_ok: `{payload.get('crash', {}).get('all_ok')}`",
        f"- outcome_gap_stages: `{(payload.get('critical_invariants') or {}).get('restart_no_duplicate_entry', {}).get('outcome_gap_stages')}`",
        "",
        "## Execution integrity",
        f"- ok: `{payload.get('execution', {}).get('ok')}`",
        f"- cases: `{payload.get('execution', {}).get('cases')}`",
        "",
        "## Data-quality protection",
        f"- stale_blocks_entry: `{(payload.get('execution') or {}).get('cases', {}).get('stale_blocks_entry')}`",
        f"- daily_loss_blocks_entry: `{(payload.get('execution') or {}).get('cases', {}).get('daily_loss_blocks_entry')}`",
        "",
        "## Experience-store integrity",
        f"- separation: `{(payload.get('lifecycle') or {}).get('invariants', {}).get('experience_stores_separated')}`",
        "",
        "## Deterministic replay",
        f"- `{(payload.get('stress') or {}).get('evidence', {}).get('deterministic')}`",
        "",
        "## Stress",
        f"- ok: `{payload.get('stress', {}).get('ok')}`",
        f"- evidence: `{payload.get('stress', {}).get('evidence')}`",
        "",
        "## Failures",
        f"- `{payload.get('failures')}`",
        "",
        "## Tests",
        f"- `{tests}`",
        "",
        "## Remaining risks and limitations",
        "- Historical/synthetic fixtures only — not live MT5 or streaming realism.",
        "- Mid-`process_bar` crashes are approximated (observe/decide/risk staged; entry/exit use real engine path).",
        "- Experience rebuild from `closed_position_ids` alone is **not** supported; wiping experience after close leaves a durable gap (detected in `after_exit_before_outcome`).",
        "- Commission/slippage remain UNKNOWN (`None`) — never invented.",
        "- NullPolicy remains production default; EngineeringTestPolicy is validation-only.",
        "- No profitability or edge claim.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase57.run_phase57",
        ".\\.venv\\Scripts\\python.exe -m phase57.cli --run",
        ".\\.venv\\Scripts\\python.exe -m unittest phase57.tests.test_phase57 -v",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "No Phase58 started.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    payload = run_full_suite()
    tests = _run_tests()
    # Tests failing must prevent a successful verdict even if suite invariants passed
    if not tests.get("ok") and payload.get("verdict") == "AUTONOMOUS_RELIABILITY_VALIDATED":
        payload["verdict"] = "AUTONOMOUS_RELIABILITY_PARTIAL"
        payload["verdict_reason"] = (
            payload.get("verdict_reason") or ""
        ) + " | unittest regressions failed — cannot fully validate."
        payload["failures"] = list(payload.get("failures") or []) + [
            {"id": "unittest_suite", "severity": "CRITICAL", "detail": tests}
        ]

    runtime_s = time.perf_counter() - t0
    machine = {
        "recipe": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "verdict": payload.get("verdict"),
        "verdict_reason": payload.get("verdict_reason"),
        "critical_invariants": payload.get("critical_invariants"),
        "critical_ok": payload.get("critical_ok"),
        "lifecycle": payload.get("lifecycle"),
        "crash": payload.get("crash"),
        "execution": payload.get("execution"),
        "stress": payload.get("stress"),
        "failures": payload.get("failures"),
        "tests": tests,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
    }
    machine["sha256"] = canonical_json_sha256(
        {k: machine[k] for k in machine if k != "sha256"}
    )

    write_json(REPORTS_DIR / "validation_results.json", machine)
    write_json(REPORTS_DIR / "critical_invariants.json", payload.get("critical_invariants") or {})
    write_json(REPORTS_DIR / "crash_recovery.json", payload.get("crash_full") or {})
    write_json(REPORTS_DIR / "execution_integrity.json", payload.get("execution") or {})
    write_json(REPORTS_DIR / "stress.json", payload.get("stress") or {})
    write_json(REPORTS_DIR / "lifecycle.json", payload.get("lifecycle") or {})
    write_json(REPORTS_DIR / "failures.json", payload.get("failures") or [])
    write_json(REPORTS_DIR / "tests.json", tests)

    report = build_final_report(payload, tests, runtime_s)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", report)

    doc = "\n".join(
        [
            "# Phase 57 — Autonomous Reliability & Execution Integrity",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{payload.get('verdict')}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
            "",
            payload.get("verdict_reason") or "",
            "",
            "Independent validation of Phase56 under `src/phase57/` only. Phase0–56 unmodified.",
            "",
            "## Commands",
            "",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase57.run_phase57",
            "```",
            "",
            "See `reports/phase57/FINAL_REPORT.md`.",
            "",
        ]
    )
    write_text(DOCS_DIR / "PHASE_57_AUTONOMOUS_RELIABILITY.md", doc)

    print(payload.get("verdict"), payload.get("verdict_reason"))
    print("tests", tests)
    print("report", REPORTS_DIR / "FINAL_REPORT.md")
    return 0 if payload.get("verdict") != "AUTONOMOUS_RELIABILITY_FAILED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
