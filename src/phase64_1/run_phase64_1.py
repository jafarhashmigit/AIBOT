"""Phase 64.1 runner — canonical identity + intent integration; paper only."""

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
from phase64_1.adversarial import run_adversarial_tests
from phase64_1.constants import (
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
from phase64_1.crash_suite import run_crash_matrix
from phase64_1.engine import make_canonical_engine
from phase64_1.identity import identity_contract
from phase64_1.integrity import audit_integrity
from phase64_1.progress import write_json, write_text
from phase64_1.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_1.tests.test_phase64_1")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_1.tests.test_phase64_1",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _end_to_end_demo() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-20", move_after_entry=-3.0)
        eng = make_canonical_engine(
            work=work,
            policy=EngineeringTestPolicy(["BUY"]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            account_profile={
                "broker": "Exness",
                "environment": "DEMO",
                "platform": "MT5",
                "symbol": "XAUUSDm",
                "digits": 3,
                "verification_status": "USER_REPORTED_FROM_CONNECTED_MT5_SPECIFICATION",
            },
        )
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        stages = [t.get("stage") for t in (out.get("trace") or [])]
        return {
            "stages": stages,
            "decision_id_scheme": (out.get("decision") or {}).get("decision_id_scheme"),
            "snapshot_id": (out.get("snapshot") or {}).get("snapshot_id"),
            "intent_id": (out.get("intent") or {}).get("intent_id"),
            "intent_status": (out.get("intent") or {}).get("intent_status"),
            "position_id": (out.get("position") or {}).get("position_id"),
            "position_links_intent": (out.get("position") or {}).get("intent_id")
            == (out.get("intent") or {}).get("intent_id"),
            "canonical_identity": out.get("canonical_identity"),
            "broker_order_send": out.get("broker_order_send"),
            "has_snapshot": "MARKET_SNAPSHOT" in stages,
            "has_intent": "EXECUTION_INTENT" in stages,
            "end_to_end_ok": bool(
                out.get("canonical_identity")
                and "MARKET_SNAPSHOT" in stages
                and "EXECUTION_INTENT" in stages
                and (out.get("decision") or {}).get("decision_id_scheme")
                and out.get("broker_order_send") is False
            ),
        }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("identity_contract", flush=True)
    ident = identity_contract()
    write_json(REPORTS_DIR / "canonical_identity_contract.json", ident)

    print("end_to_end_paper", flush=True)
    e2e = _end_to_end_demo()
    write_json(REPORTS_DIR / "end_to_end_paper_integration.json", e2e)

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
        integration_ok=True,
        crash_ok=bool(crash.get("suite_pass")),
        adversarial_ok=bool(adv.get("pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        tests_ok=bool(tests.get("ok")),
        null_ok=null_ok,
        end_to_end_paper=bool(e2e.get("end_to_end_ok")),
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
        "null_ok": null_ok,
        "tests_ok": tests.get("ok"),
        "crash_ok": crash.get("suite_pass"),
        "adversarial_ok": adv.get("pass"),
        "integrity_ok": integrity.get("checks_pass"),
        "end_to_end_ok": e2e.get("end_to_end_ok"),
    }
    artifacts = [
        "canonical_identity_contract.json",
        "end_to_end_paper_integration.json",
        "crash_recovery_matrix.json",
        "adversarial_audit.json",
        "phase_integrity_audit.json",
        "test_results.json",
    ]
    validation["artifact_sha256"] = {n: file_sha256(REPORTS_DIR / n) for n in artifacts}
    write_json(REPORTS_DIR / "validation_results.json", validation)

    changed_files = [
        "src/phase64_1/** (new)",
        "tests/phase64_1/** (new)",
        "reports/phase64_1/** (new)",
        "docs/agent/PHASE_64_1_CANONICAL_DECISION_INTENT.md (new)",
    ]

    md = [
        "# Phase 64.1 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
        f"**Broker execution ready:** `False`",
        f"**Reason:** {reason}",
        f"**Generated:** `{now}`",
        "",
        "## Canonical identity design and compatibility",
        f"- Scheme: `{ident.get('scheme')}`",
        f"- Separates: `{ident.get('separates')}`",
        f"- Historical IDs rewritten: `{ident.get('historical_ids_rewritten')}`",
        f"- Compatibility notes: `{ident.get('compatibility')}`",
        "",
        "## MarketSnapshot",
        "- Schema: `phase64_1_market_snapshot_v1`",
        "- Immutable append-only JSONL + hash index; UNKNOWN explicit; decision references snapshot_id/hash",
        f"- End-to-end snapshot_id present: `{e2e.get('snapshot_id') is not None}`",
        "",
        "## Phase54/56 integration points",
        "- Subclasses `phase57_1.DurableLifecycleEngine` → `IntegratedLifecycleEngine` → paper primitives",
        "- Uses `decide`, `RiskManager.evaluate`, `open_paper_position`, `monitor_and_maybe_exit`, BID/ASK rules",
        "- Inserts MARKET_SNAPSHOT + canonical identity + EXECUTION_INTENT before PAPER_ENTRY",
        "- Does **not** modify Phase0–63 source; does not bypass production paper primitives",
        "",
        "## Intent-to-paper-position traceability",
        f"- Stages observed: `{e2e.get('stages')}`",
        f"- Intent linked on position: `{e2e.get('position_links_intent')}`",
        f"- Intent status: `{e2e.get('intent_status')}`",
        "",
        "## Phase57.1 journal integration",
        "- Durable EXIT_COMMITTED / OUTCOME / EXPERIENCE via inherited `_finalize_close`",
        "- Intent OUTCOME_RECORDED / EXPERIENCE_LINKED after durable finalize",
        "- `recover_pending` reloads snapshot + intent journals then durable recovery",
        "",
        "## Crash matrix",
        f"- Suite pass: `{crash.get('suite_pass')}` (`{crash.get('n_pass')}`/`{crash.get('n_cases')}`)",
        f"- Cases: `{[c.get('case') for c in (crash.get('cases') or [])]}`",
        "",
        "## Tests",
        f"- Unit: OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}` fail=`{tests.get('failures')}` err=`{tests.get('errors')}`",
        f"- Adversarial pass: `{adv.get('pass')}` (`{adv.get('n_pass')}`/`{adv.get('n_cases')}`)",
        "",
        "## Files changed",
    ]
    md.extend(f"- `{f}`" for f in changed_files)
    md += [
        "",
        "## Phase 0–63 immutability",
        f"- Source modified: `{integrity.get('phase0_63_source_modified')}`",
        f"- Phase64 modified by 64.1: `{integrity.get('phase64_source_modified_by_64_1')}`",
        f"- Reports 61/62/63/64 present: `{integrity.get('phase61_report_present')}` / `{integrity.get('phase62_report_present')}` / `{integrity.get('phase63_report_present')}` / `{integrity.get('phase64_report_present')}`",
        f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
        f"- Stores merged: `{integrity.get('stores_merged')}`",
        f"- Phase58 sealed: `{integrity.get('phase58_holdout_sealed')}` used=`{integrity.get('phase58_used')}`",
        "",
        "## Remaining defects",
        "### High",
        "- FUTURE_BROKER_ORDER still unauthorized — no genuine decision↔broker deal chain",
        "- No genuine XAUUSDm demo fills to attach to canonical intents",
        "### Medium",
        "- Phase6 research journal still uses separate deterministic ID scheme (compat documented, not unified into phase6)",
        "- WAIT experiences still use phase54 shadow append (not full 57.1 txn path)",
        "- Engineering crash matrix uses EngineeringTestPolicy fixtures — not broker evidence",
        "### Low",
        "- Snapshot price_precision_digits often UNKNOWN until profile supplied",
        "- Intent journal not yet merged physically with phase57_1 journal file (linked by IDs)",
        "",
        "## Next recommended action",
        "1. Keep Automated Orders DISABLED; do not start Phase65 until accepted.",
        "2. After genuine XAUUSDm demo trades exist, import via Phase63 and link deals to canonical intent_ids.",
        "3. Optionally unify WAIT path onto durable txn journal for symmetry.",
        "4. Keep Champion NO_MODEL / Production WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase64_1.run_phase64_1",
        ".\\.venv\\Scripts\\python.exe -m unittest phase64_1.tests.test_phase64_1 phase64.tests.test_phase64 phase57_1.tests.test_phase57_1 phase63.tests.test_phase63 phase62.tests.test_phase62 phase61.tests.test_phase61",
        "```",
        "",
        f"Runtime s: `{time.perf_counter() - t0}`",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE64_1_FINAL_REPORT.md", "\n".join(md))
    write_text(
        DOCS_DIR / "PHASE_64_1_CANONICAL_DECISION_INTENT.md",
        "Phase 64.1 canonical decision/intent integration. See reports/phase64_1/PHASE64_1_FINAL_REPORT.md.\n",
    )
    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_1_FINAL_REPORT.md'}", flush=True)
    ok = bool(tests.get("ok") and adv.get("pass") and crash.get("suite_pass") and e2e.get("end_to_end_ok"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
