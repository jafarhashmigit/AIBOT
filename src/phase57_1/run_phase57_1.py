"""Phase 57.1 runner — CLI only, no auto-start."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase57_1.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase57_1.progress import write_json, write_text
from phase57_1.suite import choose_verdict, run_full_suite


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromName("phase57_1.tests.test_phase57_1"))
    suite.addTests(loader.loadTestsFromName("phase57.tests.test_phase57"))
    suite.addTests(loader.loadTestsFromName("phase56.tests.test_phase56"))
    suite.addTests(loader.loadTestsFromName("phase55.tests.test_phase55"))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
        "failure_details": [{"test": str(t), "detail": str(d)[:800]} for t, d in result.failures[:15]],
        "error_details": [{"test": str(t), "detail": str(d)[:800]} for t, d in result.errors[:15]],
    }


def build_report(p: dict[str, Any], tests: dict[str, Any], runtime_s: float) -> str:
    lines = [
        "# Phase 57.1 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{p.get('verdict')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Reason:** {p.get('verdict_reason')}",
        f"**Generated:** {_utc()}",
        "",
        "## Root cause",
        "- Phase56/57 treated derived `experiences.jsonl` as outcome truth while `closed_position_ids` held only IDs.",
        "- State and experience are separate files; wiping experience after close left unrecoverable outcomes.",
        "- See `docs/agent/PHASE_57_1_ROOT_CAUSE.md`.",
        "",
        "## Architecture",
        "- Append-only `TradeLifecycleJournal` with WAL + checksum + quarantine.",
        "- Stages: POSITION_OPEN → EXIT_DETECTED → EXIT_COMMITTED → OUTCOME_DERIVED → EXPERIENCE_COMMITTED.",
        "- `DurableLifecycleEngine` subclasses Phase56 without modifying Phase0–57.",
        "- Deterministic `experience_id` from `txn_id`; rebuild is idempotent.",
        "",
        "## Before / after integrity (Phase57 gap)",
        f"- `{p.get('gap')}`",
        "",
        "## Rebuild adversarial",
        f"- ok: `{p.get('rebuild_ok')}`",
        f"- cases: `{(p.get('rebuild') or {}).get('cases')}`",
        "",
        "## Injected failures",
        f"- `{p.get('inject')}`",
        "",
        "## Subprocess crash/restart",
        f"- `{p.get('subprocess')}`",
        "",
        "## Reconciliation",
        f"- gap reconcile: `{(p.get('gap') or {}).get('reconcile')}`",
        f"- reconcile_ok: `{p.get('reconcile_ok')}`",
        "",
        "## NullPolicy",
        f"- `{p.get('null_policy')}`",
        "",
        "## Tests / regressions",
        f"- `{tests}`",
        "",
        "## Persistence guarantees and limitations",
        "- EXIT_COMMITTED is durable before closed_ids / experience finalization.",
        "- Derived stores are reconstructible from journal; hist and shadow never merged.",
        "- Journal append uses WAL + fsync best-effort; not a full ACID database.",
        "- Mid-process OS kill covered for critical exit/experience boundaries via subprocess tests.",
        "- Commission/slippage remain UNKNOWN when not in evidence.",
        "",
        "## Remaining risks",
        "- Historical/synthetic fixtures only; not live MT5.",
        "- Hypothetical hist counterfactuals are not the Phase57 HIGH gap; paper shadow is journal-backed.",
        "- Partial physical disk failure beyond process crash is out of scope.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase57_1.run_phase57_1",
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
    payload["tests"] = tests
    verdict, reason = choose_verdict(payload)
    payload["verdict"] = verdict
    payload["verdict_reason"] = reason

    runtime_s = time.perf_counter() - t0
    machine = {
        "recipe": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "verdict": verdict,
        "verdict_reason": reason,
        "gap": payload.get("gap"),
        "rebuild": payload.get("rebuild"),
        "inject": {k: payload["inject"][k] for k in ("n", "all_ok", "stages") if k in (payload.get("inject") or {})},
        "subprocess": payload.get("subprocess"),
        "null_policy": payload.get("null_policy"),
        "flags": {
            "gap_fixed": payload.get("gap_fixed"),
            "rebuild_ok": payload.get("rebuild_ok"),
            "inject_ok": payload.get("inject_ok"),
            "subprocess_ok": payload.get("subprocess_ok"),
            "reconcile_ok": payload.get("reconcile_ok"),
            "null_ok": payload.get("null_ok"),
        },
        "tests": tests,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
    }
    machine["sha256"] = canonical_json_sha256({k: machine[k] for k in machine if k != "sha256"})

    write_json(REPORTS_DIR / "validation_results.json", machine)
    write_json(REPORTS_DIR / "gap_before_after.json", payload.get("gap") or {})
    write_json(REPORTS_DIR / "rebuild_adversarial.json", payload.get("rebuild") or {})
    write_json(REPORTS_DIR / "inject_failures.json", payload.get("inject") or {})
    write_json(REPORTS_DIR / "subprocess_crashes.json", payload.get("subprocess") or {})
    write_json(REPORTS_DIR / "tests.json", tests)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", build_report(payload, tests, runtime_s))
    write_text(
        DOCS_DIR / "PHASE_57_1_DURABLE_EXPERIENCE_RECOVERY.md",
        "\n".join(
            [
                "# Phase 57.1 — Durable Experience Recovery",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `docs/agent/PHASE_57_1_ROOT_CAUSE.md` and `reports/phase57_1/FINAL_REPORT.md`.",
                "",
            ]
        ),
    )

    print(verdict, reason)
    print("tests", tests)
    print("report", REPORTS_DIR / "FINAL_REPORT.md")
    return 0 if verdict != "DURABLE_EXPERIENCE_RECOVERY_FAILED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
