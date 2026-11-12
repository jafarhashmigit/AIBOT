"""Phase 62 runner — metadata intake + read-only demo collector; CLI only."""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase62.adapters import null_policy_ok, phase58_holdout
from phase62.capability import build_capability_matrix, discover_integrations, platform_integration_decision
from phase62.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
    file_sha256,
)
from phase62.cost_evidence import demo_cost_evidence_status
from phase62.domains import audit_domains
from phase62.importers import import_csv, import_json_records, write_synthetic_fixtures
from phase62.intake import build_identity_status, intake_schema
from phase62.integrity import phase_integrity_audit
from phase62.progress import write_json, write_text
from phase62.schema import execution_record_schema
from phase62.store import ExecutionStore, recovery_audit
from phase62.sufficiency import accumulate
from phase62.verdict import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName("phase62.tests.test_phase62")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tests_run": 0, "failures": 1, "errors": 1}
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "command": "python -m unittest phase62.tests.test_phase62",
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("intake_schema", flush=True)
    schema_intake = intake_schema()
    write_json(REPORTS_DIR / "account_metadata_intake_schema.json", schema_intake)
    identity = build_identity_status()
    write_json(REPORTS_DIR / "account_identity_status.json", identity)

    print("capability", flush=True)
    discovery = discover_integrations()
    matrix = build_capability_matrix(identity, discovery)
    decision = platform_integration_decision(identity, matrix)
    write_json(REPORTS_DIR / "collector_capability_matrix.json", matrix)
    write_json(REPORTS_DIR / "platform_integration_decision.json", decision)

    exec_schema = execution_record_schema()
    write_json(REPORTS_DIR / "execution_record_schema.json", exec_schema)

    store = ExecutionStore()
    print("fixtures_and_import_validation", flush=True)
    fixtures = write_synthetic_fixtures()
    # Validate import against TEMP store so synthetic never pollutes genuine store
    import_stats: dict[str, Any] = {"genuine_store_imports": 0, "validation_temp_only": True}
    quarantine_summary: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as td:
        tmp_store = ExecutionStore(root=Path(td) / "validation_store")
        csv_stats = import_csv(
            tmp_store,
            Path(fixtures["csv"]),
            platform=str(identity.get("platform")),
            pseudonymous_account_ref=identity.get("pseudonymous_account_ref"),
        )
        # Re-import for idempotency
        csv_stats2 = import_csv(
            tmp_store,
            Path(fixtures["csv"]),
            platform=str(identity.get("platform")),
            pseudonymous_account_ref=identity.get("pseudonymous_account_ref"),
        )
        json_stats = import_json_records(
            tmp_store,
            Path(fixtures["json"]),
            platform=str(identity.get("platform")),
            allow_synthetic=False,  # must quarantine
        )
        import_stats = {
            "validation_temp_only": True,
            "synthetic_fixtures": fixtures,
            "csv_first_import": csv_stats,
            "csv_reimport": csv_stats2,
            "json_synthetic_blocked": json_stats,
            "idempotent_reimport": csv_stats2.get("duplicates", 0) >= csv_stats.get("ingested", 0),
            "genuine_production_store_untouched_by_fixtures": True,
        }
        quarantine_summary = {
            "temp_validation_quarantine_n": len(tmp_store.quarantine_rows()),
            "reasons_sample": [r.get("quarantine_reason") for r in tmp_store.quarantine_rows()[:10]],
            "genuine_store_quarantine_n": len(store.quarantine_rows()),
        }

    write_json(REPORTS_DIR / "import_validation_report.json", import_stats)
    write_json(REPORTS_DIR / "quarantine_summary.json", quarantine_summary)

    print("store_recovery", flush=True)
    recovery = recovery_audit(store)
    write_json(REPORTS_DIR / "execution_store_recovery_audit.json", recovery)
    integrity_store = store.integrity_report()
    write_json(REPORTS_DIR / "collector_integrity_report.json", integrity_store)

    cost = demo_cost_evidence_status(store, identity)
    write_json(REPORTS_DIR / "demo_cost_evidence_status.json", cost)

    sufficiency = accumulate(store, identity)
    write_json(REPORTS_DIR / "evidence_accumulation_status.json", sufficiency)

    domains = audit_domains(store)
    write_json(REPORTS_DIR / "evidence_domain_integrity_audit.json", domains)

    phase_int = phase_integrity_audit()
    write_json(REPORTS_DIR / "phase_integrity_security.json", phase_int)

    print("tests", flush=True)
    test_result = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", test_result)

    holdout = phase58_holdout()
    holdout_sealed = len(holdout) == 10
    null_ok = null_policy_ok()
    verdict, reason = choose_verdict(
        identity=identity,
        decision=decision,
        integrity=phase_int,
        domains=domains,
        recovery=recovery,
        holdout_sealed=holdout_sealed,
        null_ok=null_ok,
        tests_ok=bool(test_result.get("ok")),
        credentials_persisted=bool(identity.get("credentials_persisted")),
        live_access=bool(decision.get("live_account_access")),
    )

    genuine = [r for r in store.all_normalized() if not r.get("synthetic")]
    n_orders = len({r.get("order_id") for r in genuine if r.get("order_id")})
    n_deals = len([r for r in genuine if r.get("record_kind") == "DEAL"])
    n_fills = len([r for r in genuine if r.get("actual_fill_price") is not None])

    runtime_s = time.perf_counter() - t0
    artifacts = {p.name: file_sha256(p) for p in sorted(REPORTS_DIR.glob("*.json"))}
    machine = {
        "recipe": RECIPE_ID,
        "verdict": verdict,
        "verdict_reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live_trading": LIVE_TRADING,
        "null_policy_ok": null_ok,
        "holdout_sealed": holdout_sealed,
        "account_type": identity.get("account_type"),
        "platform": identity.get("platform"),
        "exact_broker_symbol": identity.get("exact_broker_symbol"),
        "integration_decision": decision.get("decision"),
        "genuine_orders": n_orders,
        "genuine_deals": n_deals,
        "genuine_fills": n_fills,
        "test_result": test_result,
        "artifact_sha256": artifacts,
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
    }
    machine["sha256"] = canonical_json_sha256({k: machine[k] for k in machine if k != "sha256"})
    write_json(REPORTS_DIR / "validation_results.json", machine)

    defects = {
        "high": [
            "Account metadata intake file absent — identity incomplete",
            "No genuine Exness demo fills imported into production store",
            "Native MT5 history API blocked by Phase12 allowlist; terminal not connected",
        ],
        "medium": [
            "Platform UNKNOWN",
            "Exact XAUUSD broker symbol UNKNOWN",
            "Evidence accumulation below Phase61 thresholds",
        ],
        "low": [
            "CSV column map is explicit template — actual broker export headers must be confirmed per file",
        ],
    }

    report = [
        "# Phase 62 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Reason:** {reason}",
        f"**Generated:** {_utc()}",
        "",
        "## 1. Verdict",
        f"`{verdict}` — {reason}",
        "",
        "## 2. Account identity status",
        f"- Account type: **{identity.get('account_type')}**",
        f"- Intake file present: `{identity.get('intake_file_present')}`",
        f"- Core identity verified: `{identity.get('core_identity_verified')}`",
        f"- Credentials persisted: `{identity.get('credentials_persisted')}`",
        f"- Suffix inference used: `{identity.get('suffix_inference_used')}`",
        "",
        "## 3. Platform identification",
        f"- Platform: **{identity.get('platform')}**",
        f"- Integration decision: `{decision.get('decision')}`",
        f"- Native terminal connected: `{decision.get('native_terminal_connected')}`",
        "",
        "## 4. Exact XAUUSD symbol verification",
        f"- Exact broker symbol: **{identity.get('exact_broker_symbol')}**",
        "",
        "## 5. Collector capability",
        f"- Safest viable path: `{(matrix.get('safest_viable_path'))}`",
        f"- history_deals_get permitted: `{(discovery.get('mt5_allowlist') or {}).get('history_deals_get_permitted')}`",
        f"- order_send prohibited: `{(discovery.get('mt5_allowlist') or {}).get('order_send_prohibited')}`",
        "",
        "## 6. Actual demo integration status",
        f"- Activated adapters: `{decision.get('activated_adapters')}`",
        f"- Live account access: `{decision.get('live_account_access')}`",
        f"- Orders submitted: `{decision.get('orders_submitted')}`",
        "",
        "## 7. CSV/JSON ingestion results",
        f"- Validation on temp store only: `{import_stats.get('validation_temp_only')}`",
        f"- CSV first ingest: `{(import_stats.get('csv_first_import') or {}).get('ingested')}` "
        f"dup_reimport=`{(import_stats.get('csv_reimport') or {}).get('duplicates')}` "
        f"quarantine=`{(import_stats.get('csv_first_import') or {}).get('quarantined')}`",
        f"- Synthetic JSON blocked from genuine semantics: quarantined=`{(import_stats.get('json_synthetic_blocked') or {}).get('quarantined')}`",
        "",
        "## 8. Genuine production-store counts",
        f"- Orders: `{n_orders}` | Deals: `{n_deals}` | Fills: `{n_fills}`",
        "",
        "## 9. Duplicate / quarantine",
        f"- Temp validation quarantine n: `{quarantine_summary.get('temp_validation_quarantine_n')}`",
        f"- Genuine store quarantine n: `{quarantine_summary.get('genuine_store_quarantine_n')}`",
        "",
        "## 10. Commission / cost evidence",
        f"- Fully adjusted performance allowed: `{cost.get('fully_adjusted_performance_allowed')}`",
        f"- Actual demo commission status: `{(cost.get('actual_demo_deal_commission') or {}).get('status')}`",
        f"- Published schedule activated: `{(cost.get('published_broker_commission_schedule') or {}).get('activated')}`",
        "",
        "## 11. Evidence sufficiency",
        f"- Operational gate: `{sufficiency.get('sufficient_operational_gate')}`",
        f"- Observed fills: `{(sufficiency.get('observed') or {}).get('n_deals_fills')}`",
        f"- Thresholds lowered: `{sufficiency.get('thresholds_lowered_after_outcomes')}`",
        "",
        "## 12. Storage / recovery",
        f"- Recovery audit pass: `{recovery.get('pass')}`",
        f"- Production store normalized n: `{(recovery.get('production_store_integrity') or {}).get('n_normalized')}`",
        "",
        "## 13. Security / read-only",
        f"- Read-only enforced: `{phase_int.get('read_only_enforced')}`",
        f"- Live orders: `{phase_int.get('live_orders')}`",
        f"- Credentials in reports: `{phase_int.get('credentials_in_reports')}`",
        "",
        "## 14. Historical / shadow / demo separation",
        f"- Merged: `{domains.get('stores_merged')}`",
        f"- Demo overwrote others: `{domains.get('demo_overwrote_historical_or_paper')}`",
        f"- Checks pass: `{domains.get('checks_pass')}`",
        "",
        "## 15. Phase 58 holdout",
        f"- Sealed: `{holdout_sealed}` days=`{holdout}`",
        "",
        "## 16. Phase 0–61 immutability",
        f"- Source modified: `{phase_int.get('phase0_61_source_modified')}`",
        f"- Phase61 artifacts modified: `{phase_int.get('phase61_artifacts_modified')}`",
        "",
        "## 17. Artifact SHA-256",
        *[f"- `{k}`: `{v}`" for k, v in sorted(artifacts.items())],
        f"- validation: `{machine.get('sha256')}`",
        "",
        "## 18. Remaining defects",
        "### High",
        *[f"- {x}" for x in defects["high"]],
        "### Medium",
        *[f"- {x}" for x in defects["medium"]],
        "### Low",
        *[f"- {x}" for x in defects["low"]],
        "",
        "## 19. Next-phase recommendation",
        "1. Supply non-secret `src/data/phase62/intake/account_metadata.json` with VERIFIED Personal Area fields.",
        "2. Export Exness **demo** deal history (CSV) and import via the Phase62 CSV adapter with confirmed headers.",
        "3. Do not expand MT5 allowlist or connect terminals until security review + verified demo metadata.",
        "4. Accumulate toward Phase61 thresholds before cost-calibration claims.",
        "5. Keep Champion NO_MODEL / Production WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase62.run_phase62",
        ".\\.venv\\Scripts\\python.exe -m unittest phase62.tests.test_phase62",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "No live MT5. No broker orders. No credentials stored. No autostart.",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE62_FINAL_REPORT.md", "\n".join(report))
    write_text(
        DOCS_DIR / "PHASE_62_EXNESS_DEMO_COLLECTOR.md",
        "\n".join(
            [
                "# Phase 62 — Exness Demo Execution Collector",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `reports/phase62/PHASE62_FINAL_REPORT.md`.",
                "",
            ]
        ),
    )
    print(verdict, reason)
    print("report", REPORTS_DIR / "PHASE62_FINAL_REPORT.md")
    return 0 if test_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
