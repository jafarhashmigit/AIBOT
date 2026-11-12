"""Phase 64.3 runner — approved hardened paper runtime adoption validation."""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase64_3.adversarial import run_adversarial_tests
from phase64_3.approved_runtime import assert_hardened_runtime, make_approved_paper_engine, summarize_engine_counts
from phase64_3.constants import (
    AUTOMATED_ORDERS,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    file_sha256,
)
from phase64_3.entrypoint_audit import audit_entry_points
from phase64_3.integrity import audit_integrity
from phase64_3.multibar_suite import run_multibar_suite
from phase64_3.progress import write_json, write_text
from phase64_3.recovery_suite import run_recovery_suite
from phase64_3.verdict import choose_verdict
from phase64_3.xauusdm_profile import audit_xauusdm_integrity


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_3.tests.test_phase64_3")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_3.tests.test_phase64_3",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _smoke_approved_run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = directional_path(day="2099-12-20", n_bars=100, move_after_entry=-3.0)
        eng = make_approved_paper_engine(
            work=work,
            policy=EngineeringTestPolicy(["BUY"]),
            immediate_monitor_through_horizon=True,
        )
        guard = assert_hardened_runtime(eng)
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        counts = summarize_engine_counts(eng)
        return {
            "runtime_guard": guard,
            "action": (out.get("decision") or {}).get("action"),
            "intent_status": (out.get("intent") or {}).get("intent_status"),
            "counts": counts,
            "simulated_paper_only": True,
            "genuine_broker_deals": 0,
        }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("entrypoint_audit", flush=True)
    entries = audit_entry_points()
    write_json(REPORTS_DIR / "runtime_entrypoint_audit.json", entries)

    print("xauusdm_integrity", flush=True)
    xau = audit_xauusdm_integrity()
    write_json(REPORTS_DIR / "xauusdm_configuration_integrity.json", xau)

    print("smoke_approved_run", flush=True)
    smoke = _smoke_approved_run()
    write_json(REPORTS_DIR / "approved_runtime_smoke.json", smoke)

    print("multibar_suite", flush=True)
    multi = run_multibar_suite()
    write_json(REPORTS_DIR / "multibar_lifecycle_results.json", multi)

    print("recovery_suite", flush=True)
    recovery = run_recovery_suite()
    write_json(REPORTS_DIR / "recovery_idempotency_matrix.json", recovery)

    print("adversarial", flush=True)
    adv = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adv)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    null_ok = NullPolicy().version == EXPECTED_NULL_POLICY
    verdict, reason = choose_verdict(
        adoption_ok=bool(adv.get("pass")) and entries.get("n_approved", 0) >= 1,
        multibar_ok=bool(multi.get("suite_pass")),
        recovery_ok=bool(recovery.get("suite_pass")),
        xau_ok=bool(xau.get("pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        tests_ok=bool(tests.get("ok")),
        null_ok=null_ok,
    )

    changed_files = [
        "src/phase64_3/** (new)",
        "tests/phase64_3/** (new)",
        "reports/phase64_3/** (new)",
        "docs/agent/PHASE_64_3_HARDENED_RUNTIME_ADOPTION.md (new)",
    ]

    validation = {
        "recipe_id": RECIPE_ID,
        "generated_utc": now,
        "verdict": verdict,
        "reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "demo_collection": DEMO_COLLECTION,
        "broker_execution_ready": False,
        "genuine_broker_deals": 0,
        "phase65_started": False,
        "changed_files": changed_files,
    }
    artifacts = [
        "runtime_entrypoint_audit.json",
        "xauusdm_configuration_integrity.json",
        "approved_runtime_smoke.json",
        "multibar_lifecycle_results.json",
        "recovery_idempotency_matrix.json",
        "adversarial_audit.json",
        "phase_integrity_audit.json",
        "test_results.json",
    ]
    validation["artifact_sha256"] = {n: file_sha256(REPORTS_DIR / n) for n in artifacts}
    write_json(REPORTS_DIR / "validation_results.json", validation)

    md = [
        "# Phase 64.3 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
        f"**Broker Execution Ready:** `False`",
        f"**Reason:** {reason}",
        f"**Generated:** `{now}`",
        "",
        "## Runtime entry points (before → after)",
        f"- Discovered entry points: `{entries.get('n_entry_points')}`",
        f"- Approved: `{entries.get('n_approved')}` | Legacy explicit: `{entries.get('n_legacy_explicit')}` | High bypass risk legacy: `{entries.get('n_high_bypass_risk_legacy')}`",
        f"- Before: `{entries.get('remediation', {}).get('before')}`",
        f"- After: `{entries.get('remediation', {}).get('after')}`",
        f"- Strategy (Phase0–64.2 immutable): `{entries.get('remediation', {}).get('strategy')}`",
        "",
        "## Legacy bypass findings",
        "- Phase54/56/57/57.1/64.1 factories remain importable for regression immutability but are **LEGACY_EXPLICIT**.",
        "- New paper runs must use `phase64_3.approved_runtime.make_approved_paper_engine`.",
        "- Runtime guard asserts `HardenedLifecycleEngine` + `approved_paper_runtime` marker.",
        "- Superseded `XAUUSD` profile rejected by approved factory.",
        "",
        "## Smoke / counts (simulated paper)",
        f"- Guard: `{smoke.get('runtime_guard')}`",
        f"- Counts: `{smoke.get('counts')}`",
        f"- Genuine broker deals: `0` (explicit)",
        "",
        "## Multi-bar lifecycle",
        f"- Suite pass: `{multi.get('suite_pass')}` (`{multi.get('n_pass')}`/`{multi.get('n_cases')}`)",
        f"- Cases: `{[c.get('name') for c in (multi.get('cases') or [])]}`",
        f"- Evidence type: `{multi.get('evidence_type')}`",
        "",
        "## Recovery / idempotency",
        f"- Suite pass: `{recovery.get('suite_pass')}` (`{recovery.get('n_pass')}`/`{recovery.get('n_cases')}`)",
        f"- Subprocess executed: `{recovery.get('subprocess_executed')}`",
        f"- Cases: `{[c.get('case') for c in (recovery.get('cases') or [])]}`",
        "",
        "## XAUUSDm configuration",
        f"- Pass: `{xau.get('pass')}` active=`{xau.get('active_symbol')}` digits=`{xau.get('digits')}`",
        f"- Unknown fields intact: `{xau.get('unknown_fields_intact')}`",
        f"- No XAUUSD fallback: `{xau.get('no_silent_xauusd_fallback')}`",
        "",
        "## Tests",
        f"- Unit: OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}`",
        f"- Adversarial: `{adv.get('pass')}`",
        "",
        "## Changed files",
    ]
    md.extend(f"- `{f}`" for f in changed_files)
    md += [
        "",
        "## Phase 0–64.2 immutability",
        f"- Source modified: `{integrity.get('phase0_64_2_source_modified')}`",
        f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
        f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
        f"- Stores merged: `{integrity.get('stores_merged')}`",
        f"- Phase58 sealed: `{integrity.get('phase58_holdout_sealed')}`",
        "",
        "## Remaining defects",
        "### High",
        "- Legacy CLIs (phase54/56/57/57.1/64.1) remain executable if invoked directly — classified LEGACY_EXPLICIT; not rewritten (immutability).",
        "- No genuine broker fills; paper outcomes are simulated only.",
        "### Medium",
        "- Multi-bar suite uses synthetic fixtures (`SIMULATED_PAPER_FIXTURE`), not live market clocks.",
        "- Open PENDING across many bars depends on SL/TP fixture geometry.",
        "### Low",
        "- Phase64.2 `make_hardened_engine` still callable without 64.3 wrapper (HARDENED_INTERNAL).",
        "",
        "## Next recommended action",
        "1. Use only `python -m phase64_3.run_phase64_3` / `make_approved_paper_engine` for new paper work.",
        "2. Treat older phase runners as historical regression tooling, not production paper entry.",
        "3. Keep Automated Orders DISABLED; do not start Phase65 until genuine XAUUSDm demo fills exist.",
        "4. Keep Champion NO_MODEL / Production WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase64_3.run_phase64_3",
        ".\\.venv\\Scripts\\python.exe -m unittest phase64_3.tests.test_phase64_3 phase64_2.tests.test_phase64_2 phase64_1.tests.test_phase64_1 phase63.tests.test_phase63",
        "```",
        "",
        f"Runtime s: `{time.perf_counter() - t0}`",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE64_3_FINAL_REPORT.md", "\n".join(md))
    write_text(
        DOCS_DIR / "PHASE_64_3_HARDENED_RUNTIME_ADOPTION.md",
        "Phase 64.3 hardened paper runtime adoption. See reports/phase64_3/PHASE64_3_FINAL_REPORT.md.\n",
    )
    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_3_FINAL_REPORT.md'}", flush=True)
    ok = bool(
        tests.get("ok")
        and adv.get("pass")
        and multi.get("suite_pass")
        and recovery.get("suite_pass")
        and xau.get("pass")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
