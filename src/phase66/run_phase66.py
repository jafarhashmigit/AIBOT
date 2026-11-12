"""Phase 66 runner — independent market evidence & continuous read-only collection."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_13.schedule import state_at_utc
from phase66.adversarial import run_adversarial_tests
from phase66.architecture import build_architecture_inventory
from phase66.collector import collect_fixture_cycle, try_live_collect
from phase66.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    DOCS_DIR,
    EXECUTION_AUTHORIZATION,
    FIXTURE_JOURNAL_ROOT,
    GENUINE_FILLS,
    JOURNAL_ROOT,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SYNTHETIC_TEST_FIXTURE,
    UNAPPROVED,
)
from phase66.dual_experience import evaluate_dual_experience_isolation
from phase66.eligibility import build_eligibility_registry
from phase66.health import build_health_report
from phase66.integrity import audit_integrity
from phase66.manifest import build_dataset_manifest
from phase66.progress import write_json, write_text
from phase66.security import security_audit
from phase66.spread_stats import compute_spread_stats
from phase66.sufficiency import propose_sufficiency_gates
from phase66.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase66.tests.test_phase66")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase66.tests.test_phase66",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_13.tests.test_phase64_13",
        "phase64_12.tests.test_phase64_12",
        "phase64_11.tests.test_phase64_11",
        "phase64_10.tests.test_phase64_10",
        "phase64_9.tests.test_phase64_9",
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
        "phase58.tests.test_phase58",
        "phase57_1.tests.test_phase57_1",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        print(f"regression {name}", flush=True)
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        suite_ok = proc.returncode == 0
        details.append(
            {
                "suite": name,
                "returncode": proc.returncode,
                "ok": suite_ok,
                "stderr_tail": (proc.stderr or "")[-500:],
            }
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
    session_now = state_at_utc(datetime.now(timezone.utc))["state"]

    print("architecture", flush=True)
    arch = build_architecture_inventory()
    write_json(REPORTS_DIR / "architecture_inventory.json", arch)
    write_text(
        REPORTS_DIR / "ARCHITECTURE_INVENTORY.md",
        "\n".join(
            [
                "# Phase 66 — Architecture Inventory",
                "",
                f"- Generated: `{now}`",
                f"- Recipe: `{RECIPE_ID}`",
                f"- Second collector built: `{arch['second_collector_built']}`",
                "",
                "## Existing collection components",
                _md_table(arch["existing_collection_components"], ["component", "role", "reuse"]),
                "",
                "## Market APIs used (permitted)",
                ", ".join(f"`{a}`" for a in arch["market_collection_apis_used"]),
                "",
                "## APIs not used (unapproved for Phase66)",
                ", ".join(f"`{a}`" for a in arch["apis_not_used_unapproved"]),
                "",
                "## Persistence / recovery",
                f"- Persistence: {arch['persistence']}",
                f"- Recovery: {arch['recovery']}",
                "",
                "## Missing before Phase 66",
                *[f"- {m}" for m in arch["missing_capabilities_before_phase66"]],
                "",
                "## Reuse decisions",
                *[f"- {m}" for m in arch["reuse_decisions"]],
                "",
                "## Security boundaries",
                *[f"- {m}" for m in arch["security_boundaries"]],
                "",
                arch["note"],
                "",
            ]
        ),
    )

    print("fixture_collection", flush=True)
    fixture = collect_fixture_cycle(journal_root=FIXTURE_JOURNAL_ROOT, rounds=2)
    write_json(REPORTS_DIR / "fixture_collection.json", fixture)
    fixture_ok = fixture["rounds"][0]["status"] == "OK" and fixture["n_events"] >= 1

    print("live_attempt", flush=True)
    live = try_live_collect(journal_root=JOURNAL_ROOT)
    write_json(REPORTS_DIR / "live_collection_attempt.json", live)
    live_n = int(live.get("genuine_observations") or 0)

    fixture_journal = BrokerEvidenceJournal(FIXTURE_JOURNAL_ROOT, allow_synthetic=True, store_label="FIXTURE")
    fixture_events = fixture_journal.all_events()
    quotes = [e for e in fixture_events if e.get("kind") == "QUOTE_SNAPSHOT"]
    spread = compute_spread_stats(quotes)
    write_json(REPORTS_DIR / "spread_stats.json", spread)

    quality_summary = {
        "fixture_rejected": sum(r.get("stats", {}).get("REJECTED", 0) for r in fixture["rounds"]),
        "fixture_duplicates": sum(r.get("stats", {}).get("DUPLICATE_SUPPRESSED", 0) for r in fixture["rounds"]),
        "missingness": None,
        "silent_repair": False,
        "forward_fill_as_broker_observed": False,
    }
    manifest = build_dataset_manifest(
        events=fixture_events,
        evidence_class=SYNTHETIC_TEST_FIXTURE,
        research_use_status="EXCLUDED",
        quality_summary=quality_summary,
    )
    write_json(REPORTS_DIR / "dataset_manifest.json", manifest)

    print("eligibility", flush=True)
    live_days: list[str] = []
    if live.get("status") == "OK" and live_n > 0:
        # One calendar day of broker-observed snapshots — not an independent research sample.
        day = str(live.get("retrieved_at_utc") or now)[:10]
        live_days = [day]
    elig = build_eligibility_registry(new_live_days=live_days)
    write_json(REPORTS_DIR / "research_eligibility.json", elig)

    print("sufficiency", flush=True)
    suff = propose_sufficiency_gates(
        live_genuine_n=live_n,
        new_independent_date_blocks=len(live_days),
        fixture_ok=fixture_ok,
    )
    write_json(REPORTS_DIR / "sufficiency_gates.json", suff)

    print("health", flush=True)
    health = build_health_report(last_collect=fixture["rounds"][-1], session_state=session_now, connected=True)
    write_json(REPORTS_DIR / "collection_health.json", health)

    print("dual_experience", flush=True)
    dual = evaluate_dual_experience_isolation()
    write_json(REPORTS_DIR / "dual_experience.json", dual)

    print("security", flush=True)
    sec = security_audit()
    write_json(REPORTS_DIR / "security_audit.json", sec)

    print("integrity", flush=True)
    integ = audit_integrity()
    write_json(REPORTS_DIR / "integrity.json", integ)

    print("adversarial", flush=True)
    adv = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial.json", adv)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "unit_tests.json", tests)

    print("regressions", flush=True)
    regs = _run_regressions()
    write_json(REPORTS_DIR / "regressions.json", regs)

    engineering_ok = fixture_ok and arch["second_collector_built"] is False and dual["isolation_ok"]
    quality_blocked = False
    ops_blocked = live.get("status") == "LIVE_UNAVAILABLE" and not fixture_ok
    verdict = choose_verdict(
        engineering_ok=engineering_ok,
        security_ok=bool(sec.get("pass")) and bool(integ.get("checks_pass")),
        fixture_collection_ok=fixture_ok,
        quality_blocked=quality_blocked,
        ops_blocked=ops_blocked,
        independent_evidence_sufficient=bool(suff["independent_research_evidence_sufficient"]),
        live_genuine_n=live_n,
        tests_ok=bool(tests.get("ok")) and bool(adv.get("suite_pass")),
        regressions_ok=bool(regs.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    # --- Markdown reports ---
    write_text(
        REPORTS_DIR / "COLLECTION_DESIGN.md",
        "\n".join(
            [
                "# Collection Design",
                "",
                "- Read-only market evidence via `symbol_info` (bid/ask/time) + `copy_rates_from_pos` (M5).",
                "- Tick-stream APIs (`copy_ticks_*`) are **not** Phase-12 permitted — not used.",
                "- Persistence: reuse `BrokerEvidenceJournal` (WAL, dedup, quarantine).",
                "- Session labeling from Phase 64.13 schedule; collection ≠ trading permission.",
                "- Fixture store and genuine store are separated (`allow_synthetic`).",
                f"- Fixture cycle status: `{fixture['rounds'][0]['status']}`",
                f"- Live attempt status: `{live.get('status')}` genuine_ingested=`{live_n}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "EVIDENCE_SCHEMA_AND_PROVENANCE.md",
        "\n".join(
            [
                "# Evidence Schema and Provenance",
                "",
                "## Evidence classes",
                "BROKER_OBSERVED, HISTORICAL_ARCHIVE, DERIVED_OBSERVATION, HYPOTHETICAL_OUTCOME,",
                "PAPER_DECISION, PAPER_OUTCOME, EXTERNAL_REFERENCE, SYNTHETIC_TEST_FIXTURE",
                "",
                "- Deterministic `evidence_id` from kind|symbol|server_ts|payload|schema.",
                "- Canonical timestamps UTC; Asia/Karachi only for user-facing presentation.",
                "- Content hash + stable_key + event_id for journal identity.",
                "- Schema / collector / dataset versions persisted on every record.",
                "- No silent normalization of bid/ask; rejected rows quarantine with reason.",
                "",
                f"- Fixture manifest observations: `{manifest['observation_count']}`",
                f"- Research use of fixture dataset: `{manifest['research_use_status']}` (EXCLUDED)",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "DATA_QUALITY_AUDIT.md",
        "\n".join(
            [
                "# Data Quality Audit",
                "",
                "- Validators: invalid/future/stale timestamps, missing bid/ask, bid>ask, non-positive,",
                "  abnormal spread, incomplete/inconsistent OHLC, unexpected symbol.",
                "- No silent repair / forward-fill as BROKER_OBSERVED.",
                "- M5 candles never inferred into ticks.",
                "- Unavailability classes distinguish connection failure vs market closed/break.",
                "",
                f"- Fixture rejected: `{quality_summary['fixture_rejected']}`",
                f"- Fixture duplicates suppressed: `{quality_summary['fixture_duplicates']}`",
                f"- Silent repair: `{quality_summary['silent_repair']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "SESSION_AWARE_COLLECTION.md",
        "\n".join(
            [
                "# Session-Aware Collection",
                "",
                "- States: OPEN, CLOSE_ONLY, BREAK, CLOSED, UNKNOWN (Phase 64.13).",
                f"- Current session at run: `{session_now}`",
                "- Market observation may continue when quotes are technically available.",
                "- Independent permissions: collect market info ≠ research event ≠ paper decision ≠ broker execution.",
                "- Fail closed on unexpected symbol/server; do not infer session when authoritative schedule conflicted.",
                "- Collection status does **not** authorize trading.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "RECOVERY_AND_DURABILITY.md",
        "\n".join(
            [
                "# Recovery and Durability",
                "",
                "- Reuses Phase 64.5 BrokerEvidenceJournal: append-only events, WAL, dedup index, quarantine.",
                "- Idempotent ingest: duplicate stable_key+body_hash → DUPLICATE_SUPPRESSED.",
                "- Watermark persisted separately for collection lag / last quote & M5 timestamps.",
                "- Synthetic fixtures cannot enter genuine store.",
                "- Corrections append new records; originals not overwritten.",
                f"- Fixture journal integrity: `{fixture.get('journal_integrity')}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "COLLECTION_HEALTH.md",
        "\n".join(
            [
                "# Collection Health",
                "",
                f"- Collector status: `{health['collector_status']}`",
                f"- MT5 connection (fixture path): `{health['mt5_connection']}`",
                f"- Last successful observation: `{health.get('last_successful_observation')}`",
                f"- Session: `{health['current_session_state']}`",
                f"- Unavailability class: `{health['unavailability_class']}`",
                "- Process running alone is not treated as healthy.",
                f"- Live genuine observations this run: `{live_n}`",
                "",
                "## Spread stats (fixture quotes only — not execution cost)",
                f"- n={spread['n_observations']} mean={spread['mean']} median={spread['median']} "
                f"p90={spread['p90']} p95={spread['p95']} p99={spread['p99']} max={spread['maximum']}",
                f"- Establishes commission/swap/slippage: False",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "DATASET_MANIFEST.md",
        "\n".join(
            [
                "# Dataset Manifest",
                "",
                f"- Manifest ID: `{manifest['manifest_id']}`",
                f"- Symbol: `{manifest['symbol']}`",
                f"- Timeframes: {manifest['timeframes']}",
                f"- Observation count: `{manifest['observation_count']}`",
                f"- Source classification: `{manifest['source_classification']}`",
                f"- Research-use status: `{manifest['research_use_status']}`",
                f"- Note: {manifest['note']}",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "RESEARCH_ELIGIBILITY.md",
        "\n".join(
            [
                "# Research Eligibility",
                "",
                f"- Phase58 holdout accessed: `{elig['phase58_holdout_accessed']}`",
                f"- Holdout days sealed: `{len(elig['phase58_holdout_sealed'])}`",
                f"- Phase65 history preserved: `{elig['phase65_history_preserved']}`",
                f"- New live collection days: `{elig['new_live_collection_days']}`",
                f"- Independent research evidence sufficient: `{elig['independent_research_evidence_sufficient']}`",
                f"- Evidence generation ID: `{elig['evidence_generation_id']}`",
                "",
                "## Proposed sufficiency thresholds",
                str(suff["proposed_thresholds"]),
                "",
                "- Auto-start strategy experiments: False",
                "- Requires new preregistered protocol: True",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "SECURITY_AUDIT.md",
        "\n".join(
            [
                "# Security Audit",
                "",
                f"- Pass: `{sec['pass']}`",
                f"- order_send call sites: `{sec['order_send_call_sites']}`",
                f"- Unapproved API hits: `{sec['unapproved_api_hits']}`",
                f"- Submission enabled: `{sec['submission_enabled']}`",
                f"- Execution authorized: `{sec['execution_authorized']}`",
                f"- Wrong symbol/server fail-closed: True",
                f"- Recovery cannot authorize execution: True",
                f"- Integrity checks pass: `{integ['checks_pass']}`",
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
                f"- Unit tests ok: `{tests['ok']}` run=`{tests['tests_run']}` "
                f"failures=`{tests['failures']}` errors=`{tests['errors']}`",
                f"- Adversarial suite pass: `{adv['suite_pass']}` ({adv['n_pass']}/{adv['n_cases']})",
                f"- Regressions ok: `{regs['ok']}`",
                "",
                "## Regression details",
                _md_table(regs["details"], ["suite", "ok", "returncode"]),
                "",
                "## Adversarial cases",
                _md_table(adv["cases"], ["name", "pass"]),
                "",
            ]
        ),
    )

    elapsed = time.perf_counter() - t0
    write_text(
        REPORTS_DIR / "PHASE66_FINAL_REPORT.md",
        "\n".join(
            [
                "# Phase 66 — Final Report",
                "",
                f"- Generated: `{now}`",
                f"- Recipe: `{RECIPE_ID}`",
                f"- Elapsed sec: `{elapsed:.1f}`",
                f"- **Verdict: `{verdict['verdict']}`**",
                f"- Reason: {verdict['reason']}",
                "",
                "## 1. Already present",
                "- BrokerEvidenceJournal, Fake/Live Mt5Backend, Phase12 allowlist, Phase64.13 session schedule,",
                "  Phase64.8 trade-history RO collector, Phase58/65 research artifacts and sealed holdout.",
                "",
                "## 2. Implemented",
                "- Phase66 market snapshot + M5 collector (read-only), evidence schema/provenance,",
                "  quality gates, watermark, health, eligibility registry, spread stats, sufficiency gates,",
                "  dual-experience isolation check, security/integrity/adversarial suites.",
                "",
                "## 3. Tested",
                f"- Unit `{tests['ok']}`, adversarial `{adv['suite_pass']}`, regressions `{regs['ok']}`.",
                "",
                "## 4. Actually collected",
                f"- Fixture (SYNTHETIC_TEST_FIXTURE) events: `{len(fixture_events)}` (engineering only).",
                f"- Live genuine BROKER_OBSERVED ingested this run: `{live_n}` status=`{live.get('status')}`.",
                "",
                "## 5. Remains unavailable",
                "- Continuous long-running uptime not claimed.",
                "- `copy_ticks_*` not permitted — no genuine tick stream under current allowlist.",
                "- Commission / swap-for-execution / complete cost model still UNKNOWN/INCOMPLETE.",
                "",
                "## 6. Independently evidenced",
                "- Engineering path: fixture persistence, dedup, quarantine, fail-closed wrong symbol/server.",
                f"- Independent research date blocks newly collected: `{len(elig.get('new_live_collection_days') or [])}`.",
                "",
                "## 7. Proxy / estimate only",
                "- Fixture spreads are not current broker execution cost.",
                "- Historical archive remains HISTORICAL_ARCHIVE (MetaQuotes-era), not Exness live.",
                "",
                "## 8. Operationally ready?",
                f"- Engineering ready: `{verdict['engineering_ready']}`",
                f"- Continuous collection uptime claimed: `{verdict['continuous_collection_uptime_claimed']}`",
                "",
                "## 9. Sufficient independent research evidence?",
                f"- `{verdict['independent_research_evidence_sufficient']}`",
                "",
                "## 10. Next recommended phase",
                "- Operate the read-only collector against live MT5 to accumulate genuine BROKER_OBSERVED",
                "  date blocks under eligibility UNREVIEWED; then propose a new preregistered research protocol",
                "  only after sufficiency gates and cost-uncertainty handling — no automatic strategy promotion.",
                "",
                "## Invariants",
                _md_table(
                    [{"k": k, "v": v} for k, v in verdict["invariants"].items()],
                    ["k", "v"],
                ),
                "",
                f"- Champion: `{CHAMPION_STATUS}` Production: `{PRODUCTION_FINAL_ACTION}` "
                f"Live: `{LIVE_TRADING}` AutomatedOrders: `{AUTOMATED_ORDERS}`",
                f"- BrokerCollection: `{BROKER_COLLECTION}` order_send: `{ORDER_SEND}` "
                f"ExecutionAuthorization: `{EXECUTION_AUTHORIZATION}`",
                f"- Submission/Execution flags: `{BROKER_SUBMISSION_ENABLED}` / `{BROKER_EXECUTION_AUTHORIZED}`",
                f"- Risk: `{UNAPPROVED}` Cost: `{COST_MODEL_INCOMPLETE}` GenuineFills: `{GENUINE_FILLS}`",
                "",
                "## Dual experience",
                f"- Isolation ok: `{dual['isolation_ok']}` — raw hypothetical and paper stores not merged.",
                "",
            ]
        ),
    )

    write_text(
        DOCS_DIR / "PHASE66_STATUS.md",
        "\n".join(
            [
                "# Phase 66 Status",
                "",
                f"- Verdict: `{verdict['verdict']}`",
                f"- Engineering ready: `{verdict['engineering_ready']}`",
                f"- Independent evidence sufficient: `{verdict['independent_research_evidence_sufficient']}`",
                f"- Live genuine observations: `{live_n}`",
                f"- Champion remains `NO_MODEL`; Production `WAIT`; order_send PROHIBITED.",
                "",
            ]
        ),
    )

    print(f"VERDICT {verdict['verdict']}", flush=True)
    print(f"elapsed {elapsed:.1f}s", flush=True)
    return 0 if verdict["verdict"] == "COLLECTION_ENGINEERING_READY" and tests["ok"] and regs["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
