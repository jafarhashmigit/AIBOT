"""Phase 64.12 runner — authoritative XAUUSDm session evidence (no orders / no Phase65)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_12.adversarial import run_adversarial_tests
from phase64_12.applicability import build_applicability_matrix
from phase64_12.constants import (
    ACTIVE_SYMBOL,
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    DEMO_COLLECTION,
    DOCS_DIR,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    RETRIEVAL_DATE,
    SCHEDULE_VERSION,
    UNAPPROVED,
    USER_TZ,
)
from phase64_12.freshness import freshness_policy
from phase64_12.integrity import audit_integrity
from phase64_12.journal_ingest import ingest_session_evidence
from phase64_12.progress import write_json, write_text
from phase64_12.schedule import build_verified_schedule_spec, pkt_view_of_segments
from phase64_12.session_model import build_session_model
from phase64_12.sources import official_source_inventory
from phase64_12.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_12.tests.test_phase64_12")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_12.tests.test_phase64_12",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_11.tests.test_phase64_11",
        "phase64_10.tests.test_phase64_10",
        "phase64_9.tests.test_phase64_9",
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
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
        details.append(
            {
                "suite": name,
                "returncode": proc.returncode,
                "ok": suite_ok,
                "stderr_tail": (proc.stderr or "")[-400:],
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

    print("sources", flush=True)
    inventory = official_source_inventory()
    write_json(REPORTS_DIR / "source_inventory.json", inventory)

    print("applicability", flush=True)
    appl = build_applicability_matrix()
    write_json(REPORTS_DIR / "applicability_matrix.json", appl)

    print("schedule", flush=True)
    schedule = build_verified_schedule_spec()
    write_json(REPORTS_DIR / "verified_schedule.json", schedule)

    print("freshness", flush=True)
    fresh = freshness_policy()
    write_json(REPORTS_DIR / "freshness.json", fresh)

    print("session_model", flush=True)
    model = build_session_model(freshness=fresh)
    write_json(REPORTS_DIR / "session_model.json", model)

    print("journal_ingest", flush=True)
    journal = ingest_session_evidence()
    write_json(REPORTS_DIR / "journal_ingest.json", journal)

    # --- Markdown deliverables ---
    write_text(
        REPORTS_DIR / "EXNESS_SESSION_SOURCE_AUDIT.md",
        "\n".join(
            [
                "# Exness Session Source Audit",
                "",
                f"- Retrieval date: `{RETRIEVAL_DATE}`",
                f"- Third-party sources used: `{inventory['third_party_used']}`",
                f"- Primary hour source: `{inventory['primary_hour_source']}`",
                f"- Primary applicability source: `{inventory['primary_applicability_source']}`",
                "",
                _md_table(
                    [
                        {
                            "source_id": s["source_id"],
                            "title": s["title"],
                            "url": s["url"],
                            "covers_xauusd": s["covers_xauusd"],
                            "explicitly_covers_xauusdm": s["explicitly_covers_xauusdm"],
                            "timezone": s["published_timezone"],
                        }
                        for s in inventory["sources"]
                    ],
                    ["source_id", "title", "url", "covers_xauusd", "explicitly_covers_xauusdm", "timezone"],
                ),
                "",
                "## Notes",
                "- Only official Exness Help Center / exness.com sources used.",
                "- Hour table lists `XAUUSD`; exact-symbol bridge is the official Standard `-m` suffix article.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "SESSION_EVIDENCE_MATRIX.md",
        "\n".join(
            [
                "# Session Evidence Matrix",
                "",
                appl["reasoning"],
                "",
                _md_table(
                    [
                        {
                            "Evidence": r["evidence"],
                            "Instrument": r["instrument"],
                            "Account type": r["account_type"],
                            "Platform": r["platform"],
                            "Exact applicability": r["exact_applicability"],
                            "Status": r["status"],
                        }
                        for r in appl["rows"]
                    ],
                    ["Evidence", "Instrument", "Account type", "Platform", "Exact applicability", "Status"],
                ),
                "",
                f"- Applicability justified: `{appl['applicability_justified']}`",
                f"- Status: `{appl['status']}`",
                "",
            ]
        ),
    )

    pkt_w = pkt_view_of_segments("WINTER")
    write_text(
        REPORTS_DIR / "XAUUSDm_SESSION_SPECIFICATION.md",
        "\n".join(
            [
                "# XAUUSDm Session Specification",
                "",
                f"- Symbol: `{ACTIVE_SYMBOL}` (published hours as `XAUUSD` via Standard `-m`)",
                f"- Schedule version: `{SCHEDULE_VERSION}`",
                f"- Evidence kind: `BROKER_PUBLISHED_SESSION`",
                f"- Source timezone: `UTC+0` (server does not observe DST; windows shift with US DST)",
                f"- Close Only mapped to: `BREAK` (reject new-order preflight)",
                f"- Model verified: `{model['verified']}`",
                "",
                "## Winter weekly (UTC) — effective from 2026-11-01",
                "",
                "```json",
                json.dumps(schedule["winter_weekly_utc"], indent=2),
                "```",
                "",
                "## Summer weekly (UTC)",
                "",
                "```json",
                json.dumps(schedule["summer_weekly_utc"], indent=2),
                "```",
                "",
                f"## Winter PKT ({USER_TZ}) view",
                "",
                "```json",
                json.dumps(pkt_w, indent=2),
                "```",
                "",
                "## Rollover",
                f"- Summer: `{schedule['rollover']['summer_utc']} UTC` | Winter: `{schedule['rollover']['winter_utc']} UTC`",
                "",
                "## Holidays",
                "- Calendar dates recorded; instrument-specific amended hours not published → UNKNOWN fail-closed on those dates.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "TIMEZONE_DST_VALIDATION.md",
        "\n".join(
            [
                "# Timezone / DST Validation",
                "",
                "- Published/server timezone: **UTC+0 / GMT+0** (Exness MetaTrader article).",
                "- Do **not** hardcode permanent UTC+2/+3 as Exness server time.",
                "- US DST shifts the **schedule windows** while server clock stays UTC.",
                "- Summer: 2nd Sunday March → day before 1st Sunday November.",
                "- Winter (current): from 2026-11-01 through day before 2027-03-14.",
                f"- User-facing TZ: `{USER_TZ}` (UTC+5, no DST).",
                "- Midnight-crossing segments handled via end=`24:00:00` exclusive bounds.",
                "- Naive datetimes rejected → `UNKNOWN`.",
                f"- Freshness usable: `{fresh['usable']}` | status=`{fresh['status']}`",
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
                f"- Journal idempotent: `{journal.get('all_duplicate_on_replay')}`",
                "",
            ]
        ),
    )

    remaining = [
        "Instrument-specific holiday hour amendments (email-only) → UNKNOWN on holiday dates",
        "No live MT5 symbol_info_session_* API in this environment (docs used instead)",
        "OPEN indicates published schedule open — not broker order acceptance proof",
        "Commission/margin/swap/cost/risk remain unchanged from Phase 64.11 (not this phase)",
        "Phase65 NOT_STARTED; order_send PROHIBITED",
    ]
    next_evidence = [
        "Optional: ingest future Exness holiday trading-hours notices that name XAUUSD/XAUUSDm",
        "Optional: if MetaTrader Python gains session-schedule APIs, cross-check without enabling mutation",
        "Do not treat session OPEN as execution authorization; commission/margin/swap still block DEMO approval",
    ]
    write_json(REPORTS_DIR / "remaining_uncertainties.json", {"items": remaining})
    write_json(REPORTS_DIR / "exact_next_evidence.json", {"items": next_evidence})

    verdict = choose_verdict(
        applicability_justified=bool(appl["applicability_justified"]),
        authoritative_hours=True,
        timezone_established=True,
        dst_handled=True,
        provenance_ok=bool(journal.get("all_duplicate_on_replay")) and bool(inventory["n_sources"]),
        tests_ok=bool(tests.get("ok")),
        adversarial_ok=bool(adversarial.get("suite_pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        regressions_ok=bool(regressions.get("ok")),
        third_party_used=bool(inventory["third_party_used"]),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    report = "\n".join(
        [
            "# Phase 64.12 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**order_send:** `{ORDER_SEND}` | **BROKER_SUBMISSION_ENABLED:** `{BROKER_SUBMISSION_ENABLED}`",
            f"**BROKER_EXECUTION_AUTHORIZED:** `{BROKER_EXECUTION_AUTHORIZED}` | **Risk Policy:** `{UNAPPROVED}` | **Cost model:** `{COST_MODEL_INCOMPLETE}`",
            f"**Genuine fills:** `{GENUINE_FILLS}` | **Phase65:** `{PHASE65}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## 1. Executive verdict",
            f"`{verdict['verdict']}` — authoritative session schedule for `{ACTIVE_SYMBOL}` via Exness Help Center "
            "+ official Standard `-m` applicability. Does **not** authorize execution.",
            "",
            "## 2. Official source inventory",
            f"- Sources: `{inventory['n_sources']}` | Third-party: `{inventory['third_party_used']}`",
            f"- See `EXNESS_SESSION_SOURCE_AUDIT.md`",
            "",
            "## 3. Exact-symbol applicability",
            f"- Status: `{appl['status']}` | Justified: `{appl['applicability_justified']}`",
            f"- See `SESSION_EVIDENCE_MATRIX.md`",
            "",
            "## 4. Verified trading schedule",
            f"- Version: `{SCHEDULE_VERSION}` | Model verified: `{model['verified']}`",
            f"- See `XAUUSDm_SESSION_SPECIFICATION.md`",
            "",
            "## 5. UTC and PKT schedule",
            f"- Server/published: UTC+0 | User-facing: `{USER_TZ}`",
            "",
            "## 6. Timezone/DST behavior",
            "- Server clock UTC (no DST); US DST shifts windows. See `TIMEZONE_DST_VALIDATION.md`",
            "",
            "## 7. Session-model implementation",
            f"- `phase64_12.session_model` / `schedule` | states OPEN/CLOSED/BREAK/UNKNOWN | fail-closed",
            f"- Authorizes execution: `{model['authorizes_execution']}`",
            "",
            "## 8. Broker evidence journal integration",
            f"- Idempotent replay: `{journal.get('all_duplicate_on_replay')}` | events=`{journal.get('n_events')}`",
            f"- Journal root: `{journal.get('journal_root')}`",
            "",
            "## 9. Freshness and conflicts",
            f"- Freshness: `{fresh['status']}` usable=`{fresh['usable']}`",
            "- Conflicts: preserve both; effective state UNKNOWN",
            "",
            "## 10. Tests",
            f"- Unit OK=`{tests.get('ok')}` | Adversarial=`{adversarial.get('suite_pass')}` "
            f"({adversarial.get('n_pass')}/{adversarial.get('n_cases')}) | Regressions=`{regressions.get('ok')}` | Integrity=`{integrity.get('checks_pass')}`",
            "",
            "## 11. Regression integrity",
            f"- Phase64.11 verdict preserved: `{integrity.get('phase64_11_verdict_preserved')}`",
            f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
            "",
            "## 12. Remaining session-related uncertainties",
            *[f"- {x}" for x in remaining],
            "",
            "## 13. Exact next evidence",
            *[f"- {x}" for x in next_evidence],
            "",
            "## 14. Security / invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_12.run_phase64_12",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_12_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_64_12_XAUUSDm_SESSION_EVIDENCE.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] == "XAUUSDm_SESSION_EVIDENCE_VALIDATED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
