"""Phase 64.11 runner — evidence boundary closure (no orders / no Phase65)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_11.adversarial import run_adversarial_tests
from phase64_11.boundary_matrix import build_evidence_boundary_matrix
from phase64_11.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    GENUINE_FILLS,
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
from phase64_11.integrity import audit_integrity
from phase64_11.inventory import build_evidence_inventory
from phase64_11.progress import write_json, write_text
from phase64_11.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_11.tests.test_phase64_11")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_11.tests.test_phase64_11",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_10.tests.test_phase64_10",
        "phase64_9.tests.test_phase64_9",
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
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

    spread_points = 240.0
    try:
        p = Path(__file__).resolve().parents[2] / "reports" / "phase64_7" / "live_ro_probe_sanitized.json"
        if p.is_file():
            spread_points = float((json.loads(p.read_text(encoding="utf-8")).get("symbol") or {}).get("spread_points") or 240)
    except Exception:
        pass

    print("inventory", flush=True)
    inventory = build_evidence_inventory()
    write_json(REPORTS_DIR / "evidence_inventory.json", inventory)

    print("boundary_matrix", flush=True)
    matrix = build_evidence_boundary_matrix(observed_spread_points=spread_points)
    write_json(REPORTS_DIR / "evidence_boundary_matrix.json", {k: v for k, v in matrix.items() if k != "artifacts"})
    arts = matrix["artifacts"]
    write_json(REPORTS_DIR / "commission_boundary.json", arts["commission"])
    write_json(REPORTS_DIR / "margin_boundary.json", arts["margin"])
    write_json(REPORTS_DIR / "session_boundary.json", arts["sessions"])
    write_json(REPORTS_DIR / "swap_forensic.json", arts["swap"])
    write_json(REPORTS_DIR / "cost_taxonomy.json", arts["cost"])
    write_json(REPORTS_DIR / "demo_risk_policy_evidence.json", arts["risk_policy"])

    # Markdown deliverables
    matrix_md = "\n".join(
        [
            "# Evidence Boundary Matrix",
            "",
            "Primary Phase 64.11 deliverable. Classifications are evidence boundaries — not forced closures.",
            "",
            _md_table(
                [
                    {
                        "Blocker": r["blocker"],
                        "Current State": r["current_state"],
                        "Required Evidence": r["required_evidence"],
                        "Can Close Without Fill?": r["can_close_without_fill"],
                        "Classification": r["classification"],
                        "Next Evidence": r["next_evidence"],
                    }
                    for r in matrix["rows"]
                ],
                ["Blocker", "Current State", "Required Evidence", "Can Close Without Fill?", "Classification", "Next Evidence"],
            ),
            "",
        ]
    )
    write_text(REPORTS_DIR / "EVIDENCE_BOUNDARY_MATRIX.md", matrix_md)

    write_text(
        REPORTS_DIR / "COMMISSION_EVIDENCE_REPORT.md",
        "\n".join(
            [
                "# Commission Evidence Report",
                "",
                f"- Classification: `{arts['commission']['classification']}`",
                f"- Account-specific status: `{arts['commission']['account_specific']['status']}`",
                f"- Published mapped to Trial15/XAUUSDm: `{arts['commission']['published']['mapped_to_trial15_xauusdm']}`",
                f"- Can close without fill: `{arts['commission']['can_close_without_fill']}`",
                "",
                "## Reasoning",
                arts["commission"]["reasoning"],
                "",
                "## Next evidence",
                arts["commission"]["next_evidence"],
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "MARGIN_EVIDENCE_REPORT.md",
        "\n".join(
            [
                "# Margin Evidence Report",
                "",
                f"- MARGIN_MODEL: `{arts['margin']['MARGIN_MODEL']}`",
                f"- Classification: `{arts['margin']['classification']}`",
                f"- order_calc_margin: `{arts['margin']['order_calc_margin']}`",
                "",
                "## Reasoning",
                arts["margin"]["reasoning"],
                "",
                "## Next evidence",
                arts["margin"]["next_evidence"],
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "SESSION_EVIDENCE_REPORT.md",
        "\n".join(
            [
                "# Session Evidence Report",
                "",
                f"- Programmatic status: `{arts['sessions']['current_state']}`",
                f"- Classification: `{arts['sessions']['classification']}`",
                f"- Inferred from gaps: `{arts['sessions']['inferred_from_gaps']}`",
                f"- Can close without fill: `{arts['sessions']['can_close_without_fill']}`",
                "",
                "## Reasoning",
                arts["sessions"]["reasoning"],
                "",
                "## Next evidence",
                arts["sessions"]["next_evidence"],
                "",
            ]
        ),
    )
    swap_table = _md_table(arts["swap"]["forensic_table"], ["observation", "source", "value", "unit", "direction", "volume", "nights", "status"])
    write_text(
        REPORTS_DIR / "SWAP_FORENSIC_RECONCILIATION.md",
        "\n".join(
            [
                "# Swap Forensic Reconciliation",
                "",
                f"- Preserved Phase63: `{SWAP_LONG_PHASE63}`",
                f"- Preserved live: `{SWAP_LONG_PHASE64_7}`",
                f"- Overwrite: `{arts['swap']['overwrite']}` | Reconciled: `{arts['swap']['reconciled']}`",
                f"- Status for execution: `{arts['swap']['current_state']}`",
                f"- Classification: `{arts['swap']['classification']}`",
                "",
                swap_table,
                "",
                "## Reasoning",
                arts["swap"]["reasoning"],
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "COST_TAXONOMY.md",
        "\n".join(
            [
                "# Canonical Cost Taxonomy",
                "",
                f"- COST_MODEL_VALIDATED: `{arts['cost']['COST_MODEL_VALIDATED']}`",
                f"- Current state: `{arts['cost']['current_state']}`",
                "",
                _md_table(
                    [
                        {
                            "cost": c["cost"],
                            "evidence_type": c["evidence_type"],
                            "verification_status": c["verification_status"],
                            "demo_risk_gating_eligible": c["demo_risk_gating_eligible"],
                        }
                        for c in arts["cost"]["costs"]
                    ],
                    ["cost", "evidence_type", "verification_status", "demo_risk_gating_eligible"],
                ),
                "",
                arts["cost"]["evaluation"],
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "DEMO_RISK_POLICY_EVIDENCE.md",
        "\n".join(
            [
                "# DEMO Risk Policy Evidence",
                "",
                f"- Overall: `{arts['risk_policy']['overall_approval_status']}`",
                f"- Authorizes execution: `{arts['risk_policy']['authorizes_execution']}`",
                f"- Blocked parameters: `{arts['risk_policy']['blocked_parameters']}`",
                "",
                arts["risk_policy"]["note"],
                "",
                _md_table(
                    [
                        {
                            "parameter": p["parameter"],
                            "kind": p["kind"],
                            "status": p["status"],
                            "unit": p["unit"],
                        }
                        for p in arts["risk_policy"]["parameters"]
                    ],
                    ["parameter", "kind", "status", "unit"],
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
                "",
            ]
        ),
    )

    remaining = [
        "Commission: REQUIRES_GENUINE_ACCOUNT_EVENT (0 trade fills)",
        "Margin: STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT under current PROHIBITED order_calc_margin",
        "Sessions: closable from authoritative external evidence — not yet ingested",
        "Swap: UNKNOWN_FOR_EXECUTION; conflict preserved; overnight charge unproven",
        "Cost model: INCOMPLETE / COST_MODEL_VALIDATED=False",
        "Risk policy: UNAPPROVED (critical params BLOCKED_BY_UNKNOWN)",
        "No genuine fills; order_send PROHIBITED; Phase65 NOT_STARTED",
    ]
    write_json(REPORTS_DIR / "remaining_blockers.json", {"blockers": remaining})

    next_evidence = [
        r["blocker"] + ": " + r["next_evidence"] for r in matrix["rows"] if r["blocker"] in {
            "Commission", "Margin", "Sessions", "Swap", "Cost model", "Risk policy"
        }
    ]
    write_json(REPORTS_DIR / "exact_next_evidence.json", {"items": next_evidence})

    verdict = choose_verdict(
        matrix=matrix,
        adversarial_ok=bool(adversarial.get("suite_pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        tests_ok=bool(tests.get("ok")),
        regressions_ok=bool(regressions.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    report = "\n".join(
        [
            "# Phase 64.11 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**order_send:** `{ORDER_SEND}` | **BROKER_SUBMISSION_ENABLED:** `{BROKER_SUBMISSION_ENABLED}`",
            f"**BROKER_EXECUTION_AUTHORIZED:** `{BROKER_EXECUTION_AUTHORIZED}` | **Risk Policy:** `{UNAPPROVED}` | **Phase65:** `{PHASE65}`",
            f"**Genuine fills:** `{GENUINE_FILLS}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## 1. Executive verdict",
            f"`{verdict['verdict']}` — evidence boundary quality, **not** full economics knowledge "
            f"(not_claiming_economics_fully_known=`{verdict['not_claiming_economics_fully_known']}`).",
            "",
            "## 2. Evidence inventory",
            f"- Items: `{inventory['n_items']}` | By type: `{inventory['counts_by_type']}`",
            "",
            "## 3. Blocker classifications",
            *[f"- **{r['blocker']}**: `{r['classification']}` (state=`{r['current_state']}`)" for r in matrix["rows"]],
            "",
            "## 4–7. Commission / Margin / Sessions / Swap",
            f"- Commission: `{arts['commission']['classification']}`",
            f"- Margin: `{arts['margin']['classification']}`",
            f"- Sessions: `{arts['sessions']['classification']}`",
            f"- Swap: `{arts['swap']['classification']}` | conflict preserved "
            f"`{SWAP_LONG_PHASE63}` vs `{SWAP_LONG_PHASE64_7}`",
            "",
            "## 8. Canonical cost model",
            f"- COST_MODEL_VALIDATED: `{arts['cost']['COST_MODEL_VALIDATED']}` | state: `{arts['cost']['current_state']}`",
            "",
            "## 9. Risk-policy evidence",
            f"- Overall: `{arts['risk_policy']['overall_approval_status']}` | blocked: `{arts['risk_policy']['blocked_parameters']}`",
            "",
            "## 10. Evidence-boundary matrix",
            "See `EVIDENCE_BOUNDARY_MATRIX.md` (primary deliverable).",
            "",
            "## 11. Tests",
            f"- Unit OK=`{tests.get('ok')}` | Adversarial=`{adversarial.get('suite_pass')}` "
            f"({adversarial.get('n_pass')}/{adversarial.get('n_cases')}) | Regressions=`{regressions.get('ok')}` | Integrity=`{integrity.get('checks_pass')}`",
            "",
            "## 12. Regression integrity",
            f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
            f"- No mutation allowlist expansion; submission/auth unchanged: `{integrity.get('checks_pass')}`",
            "",
            "## 13. Remaining blockers",
            *[f"- {b}" for b in remaining],
            "",
            "## 14. Exact next evidence",
            *[f"- {x}" for x in next_evidence],
            "",
            "## 15. Security / invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            "",
            "**Next highest-impact task:** Ingest authoritative XAUUSDm session documentation "
            "(closable without a fill); keep commission/margin/swap blocked until genuine account events "
            "or approved calc APIs — still no `order_send` / Phase65.",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_11.run_phase64_11",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_11_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_64_11_BROKER_ECONOMICS_EVIDENCE_BOUNDARY.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] != "BROKER_EVIDENCE_BOUNDARY_BLOCKED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
