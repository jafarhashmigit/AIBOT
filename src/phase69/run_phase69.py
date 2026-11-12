"""Phase 69 runner."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase69.accounting import build_live_evidence_accounting
from phase69.adversarial import run_adversarial_tests
from phase69.audit import initial_audit
from phase69.boundaries import research_boundaries
from phase69.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    CHAMPION_STATUS,
    DOCS_DIR,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STATUS_INSUFFICIENT,
    STATUS_THRESHOLD,
)
from phase69.integrity import audit_integrity
from phase69.progress import md_table, write_json, write_text
from phase69.registry import build_and_freeze_registry
from phase69.security import security_audit
from phase69.sufficiency import build_sufficiency_report


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase69.tests.test_phase69")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase68.tests.test_phase68",
        "phase67.tests.test_phase67",
        "phase66.tests.test_phase66",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        print(f"regression {name}", flush=True)
        proc = subprocess.run([sys.executable, "-m", "unittest", name, "-q"], capture_output=True, text=True, env=env)
        suite_ok = proc.returncode == 0
        details.append({"suite": name, "ok": suite_ok, "returncode": proc.returncode, "stderr_tail": (proc.stderr or "")[-300:]})
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("audit", flush=True)
    audit = initial_audit()
    write_json(REPORTS_DIR / "initial_audit.json", audit)

    print("accounting", flush=True)
    acc = build_live_evidence_accounting()
    write_json(REPORTS_DIR / "live_evidence_accounting.json", acc)

    print("sufficiency", flush=True)
    suf = build_sufficiency_report(acc)
    write_json(REPORTS_DIR / "evidence_sufficiency.json", suf)

    print("registry", flush=True)
    reg = build_and_freeze_registry()
    write_json(REPORTS_DIR / "hypothesis_registry.json", reg)

    print("boundaries", flush=True)
    bounds = research_boundaries()
    write_json(REPORTS_DIR / "research_boundaries.json", bounds)

    print("security/integrity/adversarial/tests", flush=True)
    sec = security_audit()
    integ = audit_integrity()
    adv = run_adversarial_tests()
    tests = _run_tests()
    regs = _run_regressions()
    write_json(REPORTS_DIR / "security_audit.json", sec)
    write_json(REPORTS_DIR / "integrity.json", integ)
    write_json(REPORTS_DIR / "adversarial.json", adv)
    write_json(REPORTS_DIR / "unit_tests.json", tests)
    write_json(REPORTS_DIR / "regressions.json", regs)

    engineering_complete = (
        bool(tests.get("ok"))
        and bool(adv.get("suite_pass"))
        and bool(regs.get("ok"))
        and bool(sec.get("pass"))
        and bool(integ.get("checks_pass"))
        and reg.get("frozen_before_evaluation") is True
        and suf.get("trading_edge_validated") is False
    )

    write_text(
        REPORTS_DIR / "PHASE69_INITIAL_AUDIT.md",
        "\n".join(
            [
                "# Phase 69 — Initial Audit",
                "",
                f"- Generated: `{now}`",
                f"- Collector reused: `{audit['collector_reused']}`",
                f"- Journal reused: `{audit['journal_reused']}`",
                f"- Second collector/journal: `{audit['second_collector_created']}` / `{audit['second_journal_created']}`",
                f"- Tick APIs permitted: `{audit['tick_apis_permitted']}`",
                "",
                "## Defects documented before fix",
                *[f"- **{d['id']}**: {d['severity']} → Fix: {d['fix']}" for d in audit["defects_documented_before_fix"]],
                "",
                f"- Phase58 holdout: `{audit['phase58_holdout_policy']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "LIVE_EVIDENCE_ACCUMULATION.md",
        "\n".join(
            [
                "# Live Evidence Accumulation",
                "",
                f"- Journal: `{acc['journal_root']}`",
                f"- Runtime sec measured: `{acc['runtime_sec_measured']}`",
                f"- Continuous uptime claimed: `{acc['continuous_uptime_claimed']}`",
                f"- Provenance counts: `{acc['provenance_counts']}`",
                f"- Unique HISTORICAL_BACKFILL M5: `{acc['unique_historical_backfill_m5_bars']}`",
                f"- Unique BROKER_OBSERVED_LIVE_BAR M5: `{acc['unique_newly_closed_live_m5_bars']}`",
                f"- BROKER_OBSERVED_QUOTE: `{acc['live_quote_observations']}`",
                f"- Independent live dates: `{acc['independent_live_collection_dates']}` (n=`{acc['n_independent_live_dates']}`)",
                f"- Backfill never counted as live: `{acc['backfill_never_counted_as_live']}`",
                f"- Contamination: `{acc['contamination_detected']}`",
                f"- Reconnects (BLOCKED cycles): `{acc['reconnects_observed']}`",
                f"- Duplicates suppressed (verify): `{acc['duplicate_suppressed_verify']}`",
                f"- Quarantine: `{acc['quarantine_n']}`",
                f"- Journal integrity: `{acc['journal_integrity']}`",
                "",
                "## Ingest hardening",
                "Phase66 `collect_once` now stamps `evidence_provenance` + `collector_cycle` using process start time.",
                "Phase67 service passes `collector_started_utc` each cycle.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "EVIDENCE_SUFFICIENCY.md",
        "\n".join(
            [
                "# Evidence Sufficiency",
                "",
                f"- **Status: `{suf['status']}`**",
                f"- Reason: {suf['reason']}",
                f"- Provisional date target: `{suf['provisional_independent_date_target']}`",
                f"- Independent live dates: `{suf['n_independent_live_dates']}`",
                f"- Unique newly closed live M5: `{suf['unique_newly_closed_live_m5_bars']}`",
                f"- Quotes: `{suf['live_quote_observations']}`",
                f"- Runtime measured: `{suf['runtime_sec_measured']}`",
                f"- Trading edge validated: `{suf['trading_edge_validated']}`",
                f"- Twenty dates equals edge: `{suf['twenty_dates_equals_edge']}`",
                "",
                suf["note"],
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "HYPOTHESIS_REGISTRY.md",
        "\n".join(
            [
                "# Hypothesis Registry (preregistered, unvalidated)",
                "",
                f"- Version: `{reg['registry_version']}`",
                f"- SHA: `{reg['registry_sha256']}`",
                f"- Frozen before evaluation: `{reg['frozen_before_evaluation']}`",
                f"- Confirmatory tests run: `{reg['confirmatory_tests_run']}`",
                f"- Strategy promotion: `{reg['strategy_promotion']}`",
                "",
                *[
                    "\n".join(
                        [
                            f"## `{h['id']}`",
                            f"- Status: `{h['status']}`",
                            f"- Question: {h['research_question']}",
                            f"- Rules: `{h['rule_definitions']}`",
                            f"- Unresolved: `{h.get('unresolved_definitions')}`",
                            f"- Primary outcome: {h['primary_outcome']}",
                            f"- Costs: `{h['cost_assumptions']}`",
                            f"- Rejection: `{h['rejection_criteria']}`",
                            "",
                        ]
                    )
                    for h in reg["hypotheses"]
                ],
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "RESEARCH_BOUNDARIES.md",
        "\n".join(
            [
                "# Research Boundaries",
                "",
                md_table(bounds["stores"], ["name", "symbol", "use"]),
                "",
                f"- Combine XAUUSD with XAUUSDm: `{not bounds['do_not_combine_xauusd_with_xauusdm']}` (must be False → do_not=`{bounds['do_not_combine_xauusd_with_xauusdm']}`)",
                f"- Phase58 holdout opened: `{bounds['phase58_holdout_opened']}`",
                f"- Consumed archive as confirmation: `{bounds['consumed_archive_as_confirmation']}`",
                f"- Strategy promotion in Phase69: `{bounds['strategy_promotion_in_phase69']}`",
                "",
                "## Future methodology",
                *[f"- {m}" for m in bounds["methodology_for_future_tests"]],
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
                f"- Unit ok=`{tests['ok']}` run=`{tests['tests_run']}` fail=`{tests['failures']}` err=`{tests['errors']}`",
                f"- Adversarial ok=`{adv['suite_pass']}` ({adv['n_pass']}/{adv['n_cases']})",
                f"- Regressions ok=`{regs['ok']}`",
                f"- Security=`{sec['pass']}` Integrity=`{integ['checks_pass']}`",
                "",
                md_table(regs["details"], ["suite", "ok", "returncode"]),
                "",
                md_table(adv["cases"], ["name", "pass"]),
                "",
            ]
        ),
    )

    elapsed = time.perf_counter() - t0
    write_text(
        REPORTS_DIR / "PHASE69_FINAL_REPORT.md",
        "\n".join(
            [
                "# Phase 69 — Final Report",
                "",
                f"- Generated: `{now}`",
                f"- Recipe: `{RECIPE_ID}`",
                f"- Elapsed sec: `{elapsed:.1f}`",
                "",
                "## Distinctions (required)",
                f"- Implementation completed: `{engineering_complete}`",
                f"- Tests actually passed: unit=`{tests['ok']}` adv=`{adv['suite_pass']}` regs=`{regs['ok']}`",
                f"- Genuine broker observations in journal: quotes=`{acc['live_quote_observations']}` "
                f"backfill_m5_unique=`{acc['unique_historical_backfill_m5_bars']}` "
                f"live_closed_m5_unique=`{acc['unique_newly_closed_live_m5_bars']}`",
                f"- Runtime actually measured: `{acc['runtime_sec_measured']}` (Phase67 verify; not long-term uptime)",
                f"- Evidence sufficiency status: `{suf['status']}`",
                f"- Unresolved blockers: live independent dates=`{acc['n_independent_live_dates']}` "
                f"(need `{suf['provisional_independent_date_target']}`); tick stream APIs still unapproved",
                f"- Hypotheses registered but not tested: `{[h['id'] for h in reg['hypotheses']]}`",
                f"- Trading edge status: **NOT VALIDATED** (`{suf['trading_edge_validated']}`)",
                "",
                f"## Engineering-complete: `{engineering_complete}`",
                f"## Trading-edge-validated: `False`",
                "",
                "## Final state",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- Live trading: `{LIVE_TRADING}`",
                f"- Automated orders: `{AUTOMATED_ORDERS}`",
                f"- order_send: `{ORDER_SEND}`",
                f"- Broker collection: `{BROKER_COLLECTION}`",
                "",
            ]
        ),
    )

    write_text(
        DOCS_DIR / "PHASE69_STATUS.md",
        f"# Phase 69 Status\n\n- Engineering complete: `{engineering_complete}`\n- Sufficiency: `{suf['status']}`\n- Edge validated: `False`\n",
    )

    print(f"SUFFICIENCY {suf['status']}", flush=True)
    print(f"ENGINEERING_COMPLETE {engineering_complete}", flush=True)
    print(f"elapsed {elapsed:.1f}s", flush=True)
    return 0 if engineering_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
