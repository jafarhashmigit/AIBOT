"""Phase 64.2 runner — intent/identity/WAIT durability hardening; paper only."""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase64_2.adversarial import run_adversarial_tests
from phase64_2.constants import (
    AUTOMATED_ORDERS,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STATUS_PAPER_FINALIZED,
    STATUS_WAIT_FINALIZED,
    file_sha256,
)
from phase64_2.crash_suite import run_crash_matrix
from phase64_2.engine import make_hardened_engine
from phase64_2.integrity import audit_integrity
from phase64_2.progress import write_json, write_text
from phase64_2.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_2.tests.test_phase64_2")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_2.tests.test_phase64_2",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _before_after_demo() -> dict[str, Any]:
    """Show Phase64.1-style PENDING leak vs Phase64.2 finalized status (fixture)."""
    day, m5, h1, by = clean_bundle(day="2099-11-05", move_after_entry=-3.0)
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        eng = make_hardened_engine(
            work=work,
            policy=EngineeringTestPolicy(["BUY"]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
        )
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        buy_status = (out.get("intent") or {}).get("intent_status")
        audit = out.get("intent_audit") or {}
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        eng = make_hardened_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        outw = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        wait_status = (outw.get("intent") or {}).get("intent_status")
        wait_durable = outw.get("wait_durable") or {}
    return {
        "before": {
            "closed_paper_intent_status": "PENDING",
            "note": "Phase64.1 linked OUTCOME/EXPERIENCE with intent_status=None — status stayed PENDING",
        },
        "after": {
            "closed_paper_intent_status": buy_status,
            "wait_intent_status": wait_status,
            "wait_experience_deterministic": wait_durable.get("experience_id"),
            "audit_consistent": audit.get("consistent"),
        },
        "consistency_ok": buy_status == STATUS_PAPER_FINALIZED
        and wait_status == STATUS_WAIT_FINALIZED
        and audit.get("consistent") is True,
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("before_after_consistency", flush=True)
    ba = _before_after_demo()
    write_json(REPORTS_DIR / "intent_state_before_after.json", ba)

    print("crash_matrix", flush=True)
    crash = run_crash_matrix()
    write_json(REPORTS_DIR / "crash_recovery_matrix.json", crash)

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
        crash_ok=bool(crash.get("suite_pass")),
        adversarial_ok=bool(adv.get("pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        tests_ok=bool(tests.get("ok")),
        null_ok=null_ok,
        consistency_ok=bool(ba.get("consistency_ok")),
    )

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
        "genuine_broker_evidence": False,
        "phase65_started": False,
    }
    artifacts = [
        "intent_state_before_after.json",
        "crash_recovery_matrix.json",
        "adversarial_audit.json",
        "phase_integrity_audit.json",
        "test_results.json",
    ]
    validation["artifact_sha256"] = {n: file_sha256(REPORTS_DIR / n) for n in artifacts}
    write_json(REPORTS_DIR / "validation_results.json", validation)

    md = [
        "# Phase 64.2 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
        f"**Broker execution ready:** `False`",
        f"**Reason:** {reason}",
        f"**Generated:** `{now}`",
        "",
        "## Root causes and fixes",
        "1. **Intent stayed PENDING after close** — Phase64.1 `link_intent_outcome/experience` committed with `intent_status=None`, so `_apply` never advanced status. **Fix:** `finalize_paper_intent` → `PAPER_FINALIZED` after durable close; recovery repairs incomplete states.",
        "2. **WAIT non-durable** — Phase54 `record_agent_shadow` used random `experience_id`. **Fix:** deterministic `wait_experience_id(decision_id)` + `WAIT_FINALIZED` intent; idempotent append.",
        "3. **Identity retry risk** — no bar-level snapshot conflict guard. **Fix:** `ONE_LOGICAL_DECISION_PER_BAR` via `bar_decisions` map; conflicting snapshot hash raises; historical IDs never rewritten.",
        "",
        "## Before / after intent-state consistency",
        f"- Before (64.1 closed paper): `{ba['before']}`",
        f"- After (64.2): `{ba['after']}`",
        "",
        "## Canonical identity",
        "- Policy: **one logical decision per M5 bar** (`day:idx`)",
        "- Duplicate observations / restarts reuse the same canonical id when snapshot hash matches",
        "- Changed snapshot hash on the same bar → `IdentityConflictError`",
        "- One intent per canonical decision (unchanged ensure_execution_intent)",
        "",
        "## WAIT recovery",
        f"- Status after durable WAIT: `{STATUS_WAIT_FINALIZED}`",
        f"- Deterministic experience id sample: `{ba['after'].get('wait_experience_deterministic')}`",
        "- Hist store untouched; shadow-only WAIT experiences",
        "",
        "## Crash matrix",
        f"- Suite pass: `{crash.get('suite_pass')}` (`{crash.get('n_pass')}`/`{crash.get('n_cases')}`)",
        f"- Cases: `{[c.get('case') for c in (crash.get('cases') or [])]}`",
        "",
        "## Tests",
        f"- Unit: OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}`",
        f"- Adversarial: `{adv.get('pass')}` (`{adv.get('n_pass')}`/`{adv.get('n_cases')}`)",
        "",
        "## Files changed",
        "- `src/phase64_2/**` (new)",
        "- `tests/phase64_2/**` (new)",
        "- `reports/phase64_2/**` (new)",
        "- `docs/agent/PHASE_64_2_INTENT_IDENTITY_WAIT.md` (new)",
        "",
        "## Phase 0–64.1 immutability",
        f"- Source modified: `{integrity.get('phase0_64_1_source_modified')}`",
        f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
        f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
        f"- Stores merged: `{integrity.get('stores_merged')}`",
        f"- Phase58 sealed: `{integrity.get('phase58_holdout_sealed')}`",
        "",
        "## Remaining defects",
        "### High",
        "- Still no genuine broker decision↔deal linkage; FUTURE_BROKER_ORDER unauthorized",
        "### Medium",
        "- Open positions correctly remain PENDING until close — multi-bar open monitoring relies on later finalize/repair",
        "- Phase64.1 engines without 64.2 hardening still exhibit PENDING-after-close if used directly",
        "### Low",
        "- Extended statuses live in HardenedIntentJournal subclass (not in Phase64 constants)",
        "",
        "## Next recommended action",
        "1. Use `HardenedLifecycleEngine` / `make_hardened_engine` for paper runs going forward.",
        "2. Keep Automated Orders DISABLED; do not start Phase65 until genuine XAUUSDm fills exist to link.",
        "3. Keep Champion NO_MODEL / Production WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase64_2.run_phase64_2",
        ".\\.venv\\Scripts\\python.exe -m unittest phase64_2.tests.test_phase64_2 phase64_1.tests.test_phase64_1 phase64.tests.test_phase64 phase57_1.tests.test_phase57_1 phase63.tests.test_phase63",
        "```",
        "",
        f"Runtime s: `{time.perf_counter() - t0}`",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE64_2_FINAL_REPORT.md", "\n".join(md))
    write_text(
        DOCS_DIR / "PHASE_64_2_INTENT_IDENTITY_WAIT.md",
        "Phase 64.2 hardening. See reports/phase64_2/PHASE64_2_FINAL_REPORT.md.\n",
    )
    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_2_FINAL_REPORT.md'}", flush=True)
    ok = bool(tests.get("ok") and adv.get("pass") and crash.get("suite_pass") and ba.get("consistency_ok"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
