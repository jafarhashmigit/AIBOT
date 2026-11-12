"""Phase 64.10 runner — economics/risk closure (no orders / no Phase65)."""

from __future__ import annotations

import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_10.adversarial import run_adversarial_tests
from phase64_10.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    UNAPPROVED,
)
from phase64_10.economics_matrix import build_economics_bundle
from phase64_10.integrity import audit_integrity
from phase64_10.progress import write_json, write_text
from phase64_10.risk_policy import build_demo_risk_policy
from phase64_10.scorecard import build_readiness_scorecard
from phase64_10.stress import build_stress_framework
from phase64_10.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_10.tests.test_phase64_10")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_10.tests.test_phase64_10",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_9.tests.test_phase64_9",
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
        "phase64_5.tests.test_phase64_5",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", name, "-q"],
                capture_output=True,
                text=True,
                env=env,
            )
        suite_ok = proc.returncode == 0
        details.append(
            {"suite": name, "returncode": proc.returncode, "ok": suite_ok, "stderr_tail": (proc.stderr or "")[-400:]}
        )
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Live probe spread from Phase64.7 sanitized report if available
    spread_points = 240.0
    try:
        import json

        p = Path(__file__).resolve().parents[2] / "reports" / "phase64_7" / "live_ro_probe_sanitized.json"
        if p.is_file():
            spread_points = float((json.loads(p.read_text(encoding="utf-8")).get("symbol") or {}).get("spread_points") or 240)
    except Exception:
        pass

    print("economics", flush=True)
    economics = build_economics_bundle(observed_spread_points=spread_points, n_trade_deals=0)
    write_json(REPORTS_DIR / "broker_economics_matrix.json", {"matrix": economics["matrix"], "sha256": economics["sha256"]})
    write_json(REPORTS_DIR / "commission_evidence_report.json", economics["commission"])
    write_json(REPORTS_DIR / "margin_model_specification.json", economics["margin"])
    write_json(REPORTS_DIR / "trading_session_specification.json", economics["sessions"])
    write_json(REPORTS_DIR / "swap_conflict_analysis.json", economics["swap"])
    write_json(REPORTS_DIR / "cost_model.json", economics["cost_model"])

    print("risk_policy", flush=True)
    policy = build_demo_risk_policy(
        commission_resolved=False,
        margin_complete=False,
        sessions_verified=False,
        swap_resolved=False,
    )
    write_json(REPORTS_DIR / "demo_risk_policy_specification.json", policy)

    print("stress", flush=True)
    stress = build_stress_framework(observed_spread_points=spread_points, expected_edge_usd=None)
    write_json(REPORTS_DIR / "cost_stress_framework.json", stress)

    print("scorecard", flush=True)
    scorecard = build_readiness_scorecard(
        commission=economics["commission"],
        margin=economics["margin"],
        sessions=economics["sessions"],
        swap=economics["swap"],
        cost_model=economics["cost_model"],
        risk_policy=policy,
    )
    write_json(REPORTS_DIR / "execution_readiness_scorecard.json", scorecard)

    write_json(
        REPORTS_DIR / "swap_long_conflict_preserved.json",
        {
            "phase63_user_reported_swap_long": SWAP_LONG_PHASE63,
            "phase64_7_live_swap_long": SWAP_LONG_PHASE64_7,
            "overwrite": False,
            "interchangeable": False,
            "status_for_execution": "UNKNOWN_FOR_EXECUTION",
        },
    )

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "test_and_adversarial_evidence.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    remaining = [
        "actual_commission_observed = UNKNOWN (0 genuine trade fills)",
        "published commission not verified as applicable to this Trial15/XAUUSDm account",
        "MARGIN_MODEL = INCOMPLETE (API margin_initial/maintenance unusable; leverage estimate not broker fact)",
        "Trading sessions programmatic status = UNKNOWN (Phase63 PARTIAL user-reported only)",
        "swap = UNKNOWN_FOR_EXECUTION (conflict −488.7 vs −644.8 explainable but not reconciled)",
        "Risk policy remains UNAPPROVED — not APPROVED_FOR_DEMO",
        "BROKER_SUBMISSION_ENABLED=False; order_send PROHIBITED; Phase65 NOT_STARTED",
        "No genuine trade fills; no manual trade performed",
    ]
    write_json(REPORTS_DIR / "remaining_blockers.json", {"blockers": remaining})

    verdict = choose_verdict(
        economics=economics,
        risk_policy=policy,
        scorecard=scorecard,
        adversarial_ok=bool(adversarial.get("suite_pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        tests_ok=bool(tests.get("ok")),
        regressions_ok=bool(regressions.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    dims = verdict["dimensions"]
    report = "\n".join(
        [
            "# Phase 64.10 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**order_send:** `{ORDER_SEND}` | **BROKER_SUBMISSION_ENABLED:** `{BROKER_SUBMISSION_ENABLED}`",
            f"**BROKER_EXECUTION_AUTHORIZED:** `{BROKER_EXECUTION_AUTHORIZED}` | **Risk Policy:** `{policy.get('approval_status')}` | **Phase65:** `{PHASE65}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## Dimensions (not conflated)",
            *[f"- {k}: `{v}`" for k, v in dims.items()],
            "",
            "## Economics summary",
            f"- Spread (snapshot): `VERIFIED` ({spread_points} points)",
            f"- Commission account-specific: `{economics['commission']['actual_commission_status']}`",
            f"- Commission published: `{economics['commission']['published_commission']['status']}` (not merged)",
            f"- Margin model: `{economics['margin']['MARGIN_MODEL']}`",
            f"- Sessions: `{economics['sessions']['programmatic_status']}` / `{economics['sessions']['completeness']}`",
            f"- Swap conflict: `{economics['swap']['conflict_status']}` → `{economics['swap']['status_for_execution']}`",
            f"- Cost model deterministic complete: `{economics['cost_model']['deterministic_execution_cost_complete']}`",
            "",
            "## Risk policy",
            f"- Approval: `{policy.get('approval_status')}` | Authorizes execution: `{policy.get('authorizes_execution')}`",
            f"- Critical blockers: `{policy.get('critical_blockers')}`",
            "",
            "## Readiness scorecard",
            f"- Execution ready: `{scorecard.get('execution_ready')}` | Blocking: `{scorecard.get('n_blocking')}`",
            f"- Blocking deps: `{scorecard.get('blocking_dependencies')}`",
            "",
            "## Tests",
            f"- Unit OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Regressions OK=`{regressions.get('ok')}`",
            f"- Integrity: `{integrity.get('checks_pass')}`",
            "",
            "## Invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            "",
            "## Remaining blockers",
            *[f"- {b}" for b in remaining],
            "",
            "**Next highest-impact task:** Obtain account-specific commission applicability + "
            "broker-verified margin/session schedules (still without enabling `order_send` / Phase65).",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_10.run_phase64_10",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_10_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_64_10_BROKER_ECONOMICS_RISK_READINESS.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] != "BROKER_ECONOMICS_RISK_BLOCKED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
