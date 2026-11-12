"""Phase 61 runner — Exness evidence calibration; CLI only; no live trading."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase61.adapters import null_policy_ok, phase58_holdout
from phase61.commission import ExnessCommissionModel, calibrate_commission
from phase61.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
    file_sha256,
)
from phase61.cost_ledger import audit_ledger_examples
from phase61.evidence_registry import build_official_evidence_registry
from phase61.execution_evidence import ExnessEvidenceAdapter, evidence_schema
from phase61.identity import build_account_identity
from phase61.integrity import audit_integrity
from phase61.latency import analyze_latency
from phase61.progress import write_json, write_text
from phase61.slippage import build_slippage_study
from phase61.sufficiency import assess_sufficiency
from phase61.verdict import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName("phase61.tests.test_phase61")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tests_run": 0, "failures": 1, "errors": 1}
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "command": "python -m unittest phase61.tests.test_phase61",
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("identity", flush=True)
    identity = build_account_identity()
    write_json(REPORTS_DIR / "exness_account_identity.json", identity)

    print("official_evidence", flush=True)
    registry = build_official_evidence_registry()
    write_json(REPORTS_DIR / "exness_official_evidence_registry.json", registry)

    print("commission_calibration", flush=True)
    commission = calibrate_commission(identity, registry)
    write_json(REPORTS_DIR / "exness_commission_calibration.json", commission)
    model = ExnessCommissionModel(commission)
    assert model.commission_adjusted_net_r(gross_r=1.0, risk_amount=10.0, lots=0.1, sides=2) is None

    print("execution_evidence_interfaces", flush=True)
    schema = evidence_schema()
    adapter = ExnessEvidenceAdapter()
    capability = adapter.capability()
    write_json(REPORTS_DIR / "execution_evidence_schema.json", schema)
    write_json(REPORTS_DIR / "execution_evidence_capability.json", capability)

    # Optional: record a labeled simulated paper example (not Exness proof)
    try:
        adapter.record_simulated_paper(
            decision_id="phase61_schema_smoke",
            strategy_or_policy_id="NullPolicy",
            instrument="XAUUSD",
            symbol="UNKNOWN",
            side="BUY",
            intended_entry_price=None,
            decision_timestamp_utc="2026-01-01 12:00:00",
            quote_timestamp_utc="2026-01-01 12:00:00",
            bid_at_decision=2000.0,
            ask_at_decision=2000.2,
            intended_volume_lots=0.01,
            simulated_submission_timestamp_utc="2026-01-01 12:00:00",
            first_executable_quote_after_decision=2000.2,
            simulated_fill_price=2000.2,
            data_quality="SMOKE_ONLY",
            source_provenance="phase61_schema_smoke_not_broker_evidence",
        )
    except Exception:
        pass

    records = adapter.collector.all()
    print("slippage_latency_ledger", flush=True)
    slippage = build_slippage_study(records)
    write_json(REPORTS_DIR / "exness_slippage_study.json", slippage)
    latency = analyze_latency(records)
    write_json(REPORTS_DIR / "execution_latency_report.json", latency)
    ledger = audit_ledger_examples()
    write_json(REPORTS_DIR / "trade_cost_ledger_audit.json", ledger)

    sufficiency = assess_sufficiency(
        n_independent_decisions=0,
        n_actual_fills=int(slippage.get("actual_fill_n") or 0),
        n_trading_days=0,
        sessions_represented=0,
        missing_record_rate=slippage.get("missing_record_rate"),
        account_consistent=identity.get("account_type") != "UNKNOWN",
        volume_consistent=False,
    )
    write_json(REPORTS_DIR / "evidence_sufficiency_assessment.json", sufficiency)

    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("tests", flush=True)
    test_result = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", test_result)

    holdout = phase58_holdout()
    holdout_sealed = len(holdout) == 10 and not integrity.get("phase58_holdout_used_for_calibration")
    null_ok = null_policy_ok()
    verdict, reason = choose_verdict(
        identity=identity,
        commission=commission,
        slippage=slippage,
        sufficiency=sufficiency,
        integrity=integrity,
        capability=capability,
        holdout_sealed=holdout_sealed,
        null_ok=null_ok,
        tests_ok=bool(test_result.get("ok")),
    )

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
        "broker_symbol": identity.get("broker_symbol"),
        "commission_status": commission.get("commission_status"),
        "actual_slippage_status": slippage.get("actual_slippage_status"),
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
            "Exness account_type UNKNOWN — no Personal Area / account metadata in repo",
            "broker_symbol UNKNOWN — XAUUSD suffix ambiguous across Pro/Raw/Zero",
            "commission_status UNKNOWN — published figures not activated",
            "actual_slippage_status UNKNOWN — no genuine Exness fill records",
        ],
        "medium": [
            "Demo deal-history collector not integrated",
            "Evidence sample insufficient for cost-model claims",
            "Historical MetaQuotes-Demo archives ≠ Exness economics",
        ],
        "low": [
            "Latency UNKNOWN without broker timestamps",
            "Swap conditions unverified for overnight holds",
        ],
    }

    report = [
        "# Phase 61 — Final Report",
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
        "## 2. Exness account identification",
        f"- Account type: **{identity.get('account_type')}**",
        f"- Account currency: `{identity.get('account_currency')}`",
        f"- Platform: `{identity.get('trading_platform')}`",
        f"- Verification: `{identity.get('verification_status')}`",
        f"- Historical archive server label: MetaQuotes-Demo (not Exness confirmation)",
        f"- Credentials stored: `{identity.get('account_login_stored')}`",
        "",
        "## 3. Instrument / symbol verification",
        f"- Intended: `{identity.get('instrument_intended')}`",
        f"- Broker symbol: **{identity.get('broker_symbol')}**",
        f"- Suffix: `{identity.get('symbol_suffix')}`",
        f"- Ambiguity: {identity.get('suffix_ambiguity_note')}",
        "",
        "## 4. Official broker evidence",
        f"- Facts registered: `{registry.get('n_facts')}`",
        f"- Active account configuration from docs alone: `{registry.get('active_account_configuration')}`",
        f"- Key XAUUSD published commission reference: Raw Spread 3.5 / Zero 5.5 USD per lot per side (investigation only)",
        f"- Artifact: `reports/phase61/exness_official_evidence_registry.json`",
        "",
        "## 5. Account-specific commission status",
        f"- Status: **{commission.get('commission_status')}**",
        f"- Published reference active in model: `{commission.get('published_reference_active_in_model')}`",
        f"- Refuses adjusted performance when UNKNOWN: `{model.commission_adjusted_net_r(gross_r=1.0, risk_amount=1.0, lots=1.0, sides=2) is None}`",
        "",
        "## 6. Actual versus proxy slippage",
        f"- Actual: **{slippage.get('actual_slippage_status')}** (n={slippage.get('actual_fill_n')})",
        f"- Proxy label: `{slippage.get('proxy_label')}`",
        f"- Live cost calibration from proxy alone: `{slippage.get('live_cost_calibration_from_proxy_alone')}`",
        "",
        "## 7. Execution latency",
        f"- Broker latency status: `{latency.get('broker_latency_status')}`",
        f"- Measured observations: `{latency.get('measured_latency_observations')}`",
        f"- Never estimate from candle-only timestamps: `{latency.get('never_estimate_from_candle_only')}`",
        "",
        "## 8. Cost ledger completeness",
        f"- Unknown case refuses total: `{ledger.get('pass_unknown_refuses_total')}`",
        f"- Complete case has total: `{ledger.get('pass_complete_has_total')}`",
        "",
        "## 9. Sample sufficiency",
        f"- Sufficient for account-specific cost model: `{sufficiency.get('sufficient_for_account_specific_cost_model')}`",
        f"- Small demo establishes live economics: `{sufficiency.get('small_demo_sample_establishes_live_economics')}`",
        f"- Preregistered thresholds: `{sufficiency.get('preregistered_thresholds')}`",
        "",
        "## 10. Tests",
        f"- `{test_result.get('command')}` OK=`{test_result.get('ok')}` "
        f"run=`{test_result.get('tests_run')}` fail=`{test_result.get('failures')}` err=`{test_result.get('errors')}`",
        "",
        "## 11. Phase 58 holdout isolation",
        f"- Sealed: `{holdout_sealed}` days=`{holdout}`",
        f"- Used for calibration: `{integrity.get('phase58_holdout_used_for_calibration')}`",
        "",
        "## 12. Phase 0–60 immutability",
        f"- Phase60 artifacts modified by Phase61: `{integrity.get('phase60_artifacts_modified_by_phase61')}`",
        f"- Phase0–60 source modified: `{integrity.get('phase0_60_source_modified')}`",
        f"- New model / alpha optimization: `{integrity.get('new_trading_model_introduced')}` / `{integrity.get('alpha_optimization_performed')}`",
        "",
        "## 13. Artifact SHA-256",
        *[f"- `{k}`: `{v}`" for k, v in sorted(artifacts.items())],
        f"- validation: `{machine.get('sha256')}`",
        "",
        "## 14. Remaining defects / evidence requirements",
        "### High",
        *[f"- {x}" for x in defects["high"]],
        "### Medium",
        *[f"- {x}" for x in defects["medium"]],
        "### Low",
        *[f"- {x}" for x in defects["low"]],
        "",
        "## 15. Next-phase recommendation",
        "1. Obtain non-secret Exness account metadata from Personal Area (account type, currency, platform, exact symbol).",
        "2. Confirm XAUUSD contract specs for that account; only then activate commission schedule.",
        "3. Wire read-only Exness **demo** deal-history collector (no live orders) and accumulate fills under sufficiency thresholds.",
        "4. Keep Phase58 holdout sealed; do not resume alpha search pretending costs are known.",
        "5. Treat demo execution ≠ live execution equivalence even after demo validation.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase61.run_phase61",
        ".\\.venv\\Scripts\\python.exe -m unittest phase61.tests.test_phase61",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "No live MT5. No broker orders. No autostart. Champion NO_MODEL. Production WAIT.",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE61_FINAL_REPORT.md", "\n".join(report))
    write_text(
        DOCS_DIR / "PHASE_61_EXNESS_EXECUTION_EVIDENCE.md",
        "\n".join(
            [
                "# Phase 61 — Exness Execution Evidence & Cost Calibration",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `reports/phase61/PHASE61_FINAL_REPORT.md`.",
                "",
            ]
        ),
    )
    print(verdict, reason)
    print("report", REPORTS_DIR / "PHASE61_FINAL_REPORT.md")
    return 0 if test_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
