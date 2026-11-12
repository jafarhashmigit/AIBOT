"""Phase 65 runner — independent edge discovery (research-only; no orders)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase65.adversarial import run_adversarial_tests
from phase65.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    DOCS_DIR,
    EXECUTION_AUTHORIZATION,
    GENUINE_FILLS,
    HYPOTHESIS_BUDGET,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    UNAPPROVED,
    VERDICT_NONE,
)
from phase65.consumption import build_consumption_registry
from phase65.cost_stress import stress_hypothesis
from phase65.dual_experience import evaluate_dual_experience
from phase65.evaluate import evaluate_hypothesis
from phase65.events import build_events_for_days
from phase65.integrity import audit_integrity
from phase65.inventory import build_research_inventory
from phase65.leakage import audit_leakage
from phase65.progress import write_json, write_text
from phase65.regime import regime_robustness
from phase65.registry import build_and_freeze_registry
from phase65.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase65.tests.test_phase65")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_13.tests.test_phase64_13",
        "phase64_12.tests.test_phase64_12",
        "phase58.tests.test_phase58",
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
        details.append({"suite": name, "ok": suite_ok, "returncode": proc.returncode})
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

    print("inventory", flush=True)
    inventory = build_research_inventory()
    write_json(REPORTS_DIR / "research_inventory.json", inventory)

    print("consumption", flush=True)
    consumption = build_consumption_registry()
    write_json(REPORTS_DIR / "consumption_registry.json", consumption)

    print("preregister", flush=True)
    registry = build_and_freeze_registry(
        discovery_days=consumption["phase65_discovery"],
        validation_days=consumption["phase65_validation"],
    )
    write_json(REPORTS_DIR / "hypothesis_registry.json", registry)

    if not consumption["sufficient_unconsumed_for_discovery"]:
        verdict = choose_verdict(
            sufficient_data=False,
            leakage_ok=False,
            integrity_ok=True,
            tests_ok=True,
            survivors_discovery=[],
            survivors_validation=[],
            holdout_opened=False,
            holdout_confirmed=False,
            budget_exhausted=True,
        )
        write_json(REPORTS_DIR / "verdict.json", verdict)
        write_text(REPORTS_DIR / "PHASE65_FINAL_REPORT.md", f"# Phase 65\n\n**Verdict:** `{verdict['verdict']}`\n")
        print(verdict["verdict"], flush=True)
        return 1

    print("events_discovery", flush=True)
    disc_events = build_events_for_days(consumption["phase65_discovery"])
    print("events_validation", flush=True)
    val_events = build_events_for_days(consumption["phase65_validation"])
    write_json(
        REPORTS_DIR / "events_meta.json",
        {
            "n_discovery_events": len(disc_events),
            "n_validation_events": len(val_events),
            "discovery_days": consumption["phase65_discovery"],
            "validation_days": consumption["phase65_validation"],
        },
    )

    print("leakage", flush=True)
    leakage = audit_leakage(
        discovery_days=consumption["phase65_discovery"],
        validation_days=consumption["phase65_validation"],
        holdout=consumption["phase58_holdout_sealed"],
        events=disc_events + val_events,
    )
    write_json(REPORTS_DIR / "leakage_audit.json", leakage)

    print("evaluate", flush=True)
    results = []
    for h in registry["hypotheses"]:
        print(f"  {h['id']}", flush=True)
        results.append(evaluate_hypothesis(h["id"], disc_events, val_events))
    write_json(REPORTS_DIR / "hypothesis_results.json", results)

    survivors_d = [r["hypothesis_id"] for r in results if r["survives_discovery"]]
    survivors_v = [r["hypothesis_id"] for r in results if r["survives_validation"]]

    print("cost_stress", flush=True)
    costs = [stress_hypothesis(r["hypothesis_id"], disc_events, r["thresholds"]) for r in results]
    write_json(REPORTS_DIR / "execution_cost_stress.json", costs)

    print("dual_experience", flush=True)
    dual = evaluate_dual_experience(disc_events)
    write_json(REPORTS_DIR / "dual_experience.json", dual)

    print("regime", flush=True)
    regimes = [regime_robustness(r["hypothesis_id"], disc_events, r["thresholds"]) for r in results]
    write_json(REPORTS_DIR / "regime_robustness.json", regimes)

    # Holdout: DO NOT open unless validation survivors — and even then Phase65 keeps sealed
    # (single confirmatory reserved; this phase does not consume holdout)
    holdout_opened = False
    holdout_confirmed = False

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_results.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "integrity.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    rejected = [
        {
            "id": r["hypothesis_id"],
            "fail_reasons": r["fail_reasons"],
            "mean_all": r["discovery"]["expected_net_r_all_decisions"],
            "incr_WAIT": r["incremental_vs_WAIT"],
            "trades": r["discovery"]["n_trades"],
            "boot_bonf_excl0": r["bootstrap"].get("bonferroni_excludes_zero"),
        }
        for r in results
        if not r["survives_validation"]
    ]

    # Markdown deliverables
    write_text(
        REPORTS_DIR / "RESEARCH_INVENTORY.md",
        "\n".join(
            [
                "# Research Inventory",
                "",
                f"- Prior verdicts: `{inventory['prior_phase_verdicts']}`",
                f"- Retired families n: `{len(inventory['permanently_retired_families'])}`",
                f"- Phase58 holdout sealed: `{inventory['phase58_holdout_sealed']}`",
                f"- Costs: `{inventory['costs']}`",
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "HYPOTHESIS_REGISTRY.md",
        "\n".join(
            [
                "# Hypothesis Registry (preregistered)",
                "",
                f"- SHA: `{registry['registry_sha256']}`",
                f"- Budget: `{HYPOTHESIS_BUDGET}` | n=`{registry['n']}`",
                "",
                *[f"- `{h['id']}` v`{h['version']}`: {h['economic_rationale'][:160]}..." for h in registry["hypotheses"]],
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "DATA_LEAKAGE_AND_SPLIT_AUDIT.md",
        "\n".join(
            [
                "# Data Leakage and Split Audit",
                "",
                f"- Pass: `{leakage['pass']}`",
                f"- Holdout sealed OK: `{leakage['holdout_sealed_ok']}`",
                f"- Chronological: `{leakage['chronological_split_ok']}`",
                f"- Overlap violations: `{leakage['overlap_violations']}`",
                f"- Session states: `{leakage['session_states_observed']}`",
                f"- Discovery days: `{consumption['phase65_discovery']}`",
                f"- Validation days: `{consumption['phase65_validation']}`",
                f"- Unconsumed pool: `{consumption['unconsumed_eligible']}`",
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "BASELINE_COMPARISON.md",
        "\n".join(
            [
                "# Baseline Comparison (discovery)",
                "",
                *[
                    f"## {r['hypothesis_id']}\n"
                    f"- WAIT mean: `{r['baselines']['WAIT']['expected_net_r_all_decisions']}`\n"
                    f"- BUY mean: `{r['baselines']['BUY']['expected_net_r_all_decisions']}`\n"
                    f"- SELL mean: `{r['baselines']['SELL']['expected_net_r_all_decisions']}`\n"
                    f"- Policy mean: `{r['discovery']['expected_net_r_all_decisions']}`\n"
                    f"- Incremental vs WAIT: `{r['incremental_vs_WAIT']}`\n"
                    for r in results
                ],
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "STATISTICAL_VALIDATION.md",
        "\n".join(
            [
                "# Statistical Validation",
                "",
                _md_table(
                    [
                        {
                            "id": r["hypothesis_id"],
                            "disc_survive": r["survives_discovery"],
                            "val_survive": r["survives_validation"],
                            "mean_all": r["discovery"]["expected_net_r_all_decisions"],
                            "trades": r["discovery"]["n_trades"],
                            "bonf_excl0": r["bootstrap"].get("bonferroni_excludes_zero"),
                            "fail": ";".join(r["fail_reasons"]),
                        }
                        for r in results
                    ],
                    ["id", "disc_survive", "val_survive", "mean_all", "trades", "bonf_excl0", "fail"],
                ),
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "EXECUTION_COST_STRESS.md",
        "\n".join(
            [
                "# Execution Cost Stress",
                "",
                "- Unknown commission/swap never treated as zero.",
                "- Fully execution-robust claim: `False`.",
                "",
                *[
                    f"## {c['hypothesis_id']}\n"
                    f"- Break-even addl R/trade: `{c['break_even_additional_R_per_trade']}`\n"
                    f"- Scenarios: `{c['scenarios']}`\n"
                    for c in costs
                ],
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "DUAL_EXPERIENCE_EVALUATION.md",
        "\n".join(
            [
                "# Dual Experience Evaluation",
                "",
                f"- Stores merged: `{dual['stores_merged']}`",
                f"- Paper/shadow n: `{dual['paper_decision_experience']['n']}` evaluable=`{dual['paper_decision_experience']['evaluable']}`",
                f"- Learning improves OOS: `{dual['learning_improves_oos_decision_quality']}`",
                f"- Diagnostic discovery positive: `{dual['diagnostic_positive_on_discovery']}`",
                "",
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "REGIME_ROBUSTNESS.md",
        "\n".join(
            [
                "# Regime Robustness",
                "",
                *[f"- `{r.get('hypothesis_id')}`: high=`{r.get('high_vol')}` low=`{r.get('low_vol')}`\n" for r in regimes],
            ]
        ),
    )
    write_text(
        REPORTS_DIR / "REJECTED_HYPOTHESES.md",
        "\n".join(
            [
                "# Rejected Hypotheses",
                "",
                _md_table(rejected, ["id", "fail_reasons", "mean_all", "incr_WAIT", "trades", "boot_bonf_excl0"]),
                "",
                f"All tested hypotheses reported (n=`{len(results)}`). Hidden cherry-picking: `False`.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "TEST_RESULTS.md",
        "\n".join(
            [
                "# Test Results",
                "",
                f"- Unit OK: `{tests.get('ok')}` run=`{tests.get('tests_run')}`",
                f"- Adversarial: `{adversarial.get('suite_pass')}` ({adversarial.get('n_pass')}/{adversarial.get('n_cases')})",
                f"- Regressions OK: `{regressions.get('ok')}`",
                f"- Integrity: `{integrity.get('checks_pass')}`",
                f"- Leakage: `{leakage.get('pass')}`",
                "",
            ]
        ),
    )

    verdict = choose_verdict(
        sufficient_data=True,
        leakage_ok=bool(leakage["pass"]),
        integrity_ok=bool(integrity["checks_pass"]),
        tests_ok=bool(tests.get("ok")) and bool(adversarial.get("suite_pass")) and bool(regressions.get("ok")),
        survivors_discovery=survivors_d,
        survivors_validation=survivors_v,
        holdout_opened=holdout_opened,
        holdout_confirmed=holdout_confirmed,
        budget_exhausted=True,
    )
    # If no survivors at all, prefer NO_NEW_INFORMATION_FAMILY_FOUND over inconclusive
    if not survivors_d and verdict["verdict"] != VERDICT_NONE:
        if leakage["pass"] and integrity["checks_pass"] and tests.get("ok"):
            verdict["verdict"] = VERDICT_NONE
            verdict["reason"] = (
                "Hypothesis budget exhausted; no preregistered H65 family survived discovery "
                "gates vs WAIT under Bonferroni date-block controls"
            )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    limitations = [
        "Archive substrate MetaQuotes-Demo XAUUSD ≠ Exness live XAUUSDm execution",
        "Commission/slippage/swap UNKNOWN — not set to zero; not fully execution-robust",
        "Exness session schedule applied as research proxy on archive timestamps",
        "Phase58 holdout remains sealed (not opened)",
        "Small unconsumed day pool limits statistical power",
        "Shadow/paper experience empty or unaligned — no dual-learning OOS claim",
    ]
    next_phase = (
        "Keep Champion=NO_MODEL and Production=WAIT. Prefer collecting genuine DEMO "
        "broker economics evidence (commission/margin/swap) under READ_ONLY constraints "
        "before further strategy churn; if new unconsumed archives appear, preregister a "
        "new H65.x family with a fresh budget — do not reopen Phase58 holdout without a survivor."
    )

    report = "\n".join(
        [
            "# Phase 65 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
            f"**Live:** `{LIVE_TRADING}` | **Automated Orders:** `{AUTOMATED_ORDERS}` | **order_send:** `{ORDER_SEND}`",
            f"**Broker Collection:** `{BROKER_COLLECTION}` | **Execution:** `{EXECUTION_AUTHORIZATION}`",
            f"**Risk Policy:** `{UNAPPROVED}` | **Cost model:** `{COST_MODEL_INCOMPLETE}` | **Fills:** `{GENUINE_FILLS}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## 1. Executive verdict",
            f"`{verdict['verdict']}` — Champion remains `NO_MODEL`; Production remains `WAIT`.",
            "",
            "## 2. Research inventory",
            f"See `RESEARCH_INVENTORY.md`. Retired families enforced. Phase58 holdout sealed.",
            "",
            "## 3. Previously failed / retired",
            f"- Phase49/50/51/58 failures recorded; DO_NOT_REPEAT n=`{len(inventory['permanently_retired_families'])}`",
            "",
            "## 4. Eligible data and provenance",
            f"- Unconsumed days: `{consumption['unconsumed_eligible']}`",
            f"- Discovery: `{consumption['phase65_discovery']}` ({len(disc_events)} events)",
            f"- Validation: `{consumption['phase65_validation']}` ({len(val_events)} events)",
            "",
            "## 5. Sealed holdout protection",
            f"- Phase58 holdout: `{consumption['phase58_holdout_sealed']}` opened=`{holdout_opened}`",
            "",
            "## 6. Preregistered hypotheses",
            f"- Registry SHA: `{registry['registry_sha256']}`",
            *[f"- `{h['id']}`" for h in registry["hypotheses"]],
            "",
            "## 7. Leakage",
            f"- Pass: `{leakage['pass']}`",
            "",
            "## 8. WAIT / baselines",
            "See `BASELINE_COMPARISON.md`.",
            "",
            "## 9. Statistical results",
            f"- Discovery survivors: `{survivors_d}` | Validation survivors: `{survivors_v}`",
            "",
            "## 10. Execution-cost stress",
            "See `EXECUTION_COST_STRESS.md`. Unknown costs not zeroed.",
            "",
            "## 11. Dual-experience",
            f"- Learning OOS improve: `{dual['learning_improves_oos_decision_quality']}` | stores merged: `{dual['stores_merged']}`",
            "",
            "## 12. Regime robustness",
            "See `REGIME_ROBUSTNESS.md`.",
            "",
            "## 13. Rejected candidates",
            f"- n=`{len(rejected)}` — see `REJECTED_HYPOTHESES.md`",
            "",
            "## 14. Surviving research candidate",
            f"- `{survivors_v or 'NONE'}`",
            "",
            "## 15. Evidence limitations",
            *[f"- {x}" for x in limitations],
            "",
            "## 16. Reproducibility",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase65.run_phase65",
            "```",
            "",
            "## 17. Security invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            f"- Submission enabled: `{BROKER_SUBMISSION_ENABLED}` | Exec authorized: `{BROKER_EXECUTION_AUTHORIZED}`",
            "",
            "## 18. Next recommended phase",
            next_phase,
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE65_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_65_INDEPENDENT_EDGE_DISCOVERY.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if tests.get("ok") and integrity.get("checks_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
