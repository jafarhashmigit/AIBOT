"""Phase 63 runner — register metadata, import genuine exports if present; CLI only."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase54.decision import NullPolicy
from phase62.store import ExecutionStore
from phase63.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    EXPORTS_DIR,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STORE_ROOT,
    VERIFICATION_STATUS,
    canonical_json_sha256,
    file_sha256,
)
from phase63.economics import build_economics_ledger
from phase63.import_pipeline import discover_csv_headers, import_genuine_exports, list_genuine_exports
from phase63.importers_adversarial import run_adversarial_import_tests
from phase63.integrity import audit_integrity
from phase63.metadata import (
    ACTIVE_SYMBOL,
    SUPERSEDED_SYMBOL,
    assert_no_xauusd_leakage,
    get_active_symbol,
    register_metadata,
)
from phase63.progress import write_json, write_text
from phase63.sufficiency import assess_sufficiency
from phase63.verdict import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName("phase63.tests.test_phase63")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tests_run": 0, "failures": 1, "errors": 1}
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "command": "python -m unittest phase63.tests.test_phase63",
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("register_metadata_xauusdm_active", flush=True)
    metadata = register_metadata(observation_timestamp_utc=_utc())
    write_json(REPORTS_DIR / "exness_account_metadata_registered.json", metadata)
    leakage = assert_no_xauusd_leakage(metadata)
    correction = {
        "previous_active_symbol": SUPERSEDED_SYMBOL,
        "new_active_symbol": ACTIVE_SYMBOL,
        "get_active_symbol": get_active_symbol(),
        "leakage_failures": leakage,
        "leakage_pass": len(leakage) == 0,
        "profile_status": metadata.get("profile_status"),
        "supersession_reason": metadata.get("supersession_reason"),
        "missing_specifications": metadata.get("missing_specifications"),
        "tick_value_active": (metadata.get("values") or {}).get("tick_value"),
        "calculation_mode_active": (metadata.get("values") or {}).get("calculation_mode"),
        "margin_currency_active": (metadata.get("values") or {}).get("margin_currency"),
        "profit_currency_active": (metadata.get("values") or {}).get("profit_currency"),
    }
    write_json(REPORTS_DIR / "broker_metadata_correction.json", correction)

    print("import_genuine_exports", flush=True)
    store = ExecutionStore(root=STORE_ROOT)
    import_result = import_genuine_exports(
        store,
        expected_symbol=ACTIVE_SYMBOL,
        expected_environment="DEMO",
        platform="MT5",
        pseudonymous_account_ref="exness-mt5-demo-xauusdm",
    )
    write_json(REPORTS_DIR / "genuine_import_result.json", import_result)

    # Document discovered schemas (or awaiting)
    schema_report = {
        "exports_found": [str(p) for p in list_genuine_exports()],
        "n_exports": len(list_genuine_exports()),
        "per_file_headers": [],
        "status": import_result.get("status"),
    }
    for p in list_genuine_exports():
        schema_report["per_file_headers"].append(discover_csv_headers(p))
    write_json(REPORTS_DIR / "csv_schema_discovered.json", schema_report)

    print("economics_sufficiency", flush=True)
    economics = build_economics_ledger(store, metadata)
    write_json(REPORTS_DIR / "execution_economics_ledger.json", economics)
    sufficiency = assess_sufficiency(store)
    write_json(REPORTS_DIR / "evidence_sufficiency.json", sufficiency)

    integrity = audit_integrity(store)
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("adversarial_import_tests", flush=True)
    adv = run_adversarial_import_tests()
    write_json(REPORTS_DIR / "adversarial_import_audit.json", adv)

    print("unit_tests", flush=True)
    test_result = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", test_result)

    null_ok = NullPolicy().version == EXPECTED_NULL_POLICY
    verdict, reason = choose_verdict(
        metadata=metadata,
        import_result=import_result,
        sufficiency=sufficiency,
        integrity=integrity,
        tests_ok=bool(test_result.get("ok")) and bool(adv.get("pass")),
        null_ok=null_ok,
    )

    genuine = [r for r in store.all_normalized() if not r.get("synthetic")]
    n_deals = sum(1 for r in genuine if r.get("record_kind") == "DEAL")
    n_orders = sum(1 for r in genuine if r.get("record_kind") == "ORDER")
    n_fills = sum(1 for r in genuine if r.get("actual_fill_price") is not None)
    qn = len(store.quarantine_rows())

    runtime_s = time.perf_counter() - t0
    artifacts = {p.name: file_sha256(p) for p in sorted(REPORTS_DIR.glob("*.json"))}
    machine = {
        "recipe": RECIPE_ID,
        "verdict": verdict,
        "verdict_reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live_trading": LIVE_TRADING,
        "automated_orders": "DISABLED",
        "demo_evidence_collection": "READ_ONLY",
        "verification_status": VERIFICATION_STATUS,
        "active_symbol": get_active_symbol(),
        "tick_value": (metadata.get("values") or {}).get("tick_value"),
        "calculation_mode": (metadata.get("values") or {}).get("calculation_mode"),
        "import_status": import_result.get("status"),
        "metadata_leakage_pass": len(leakage) == 0,
        "genuine_orders": n_orders,
        "genuine_deals": n_deals,
        "genuine_fills": n_fills,
        "quarantine_n": qn,
        "sufficiency": sufficiency.get("sufficient"),
        "test_result": test_result,
        "adversarial_pass": adv.get("pass"),
        "artifact_sha256": artifacts,
        "broker_orders": 0,
        "mt5_live": 0,
        "auto_start": False,
        "runtime_s": runtime_s,
        "generated_utc": _utc(),
    }
    machine["sha256"] = canonical_json_sha256({k: machine[k] for k in machine if k != "sha256"})
    write_json(REPORTS_DIR / "validation_results.json", machine)

    vals = metadata.get("values") or {}
    defects = {
        "high": [
            "No genuine Exness demo CSV export imported" if import_result.get("status") == "AWAITING_GENUINE_DEMO_EXPORT" else None,
            "Evidence sufficiency gates unmet",
            "Decision-linked independent decision count unavailable without decision IDs",
        ],
        "medium": [
            "Metadata is USER_REPORTED_FROM_CONNECTED_MT5_SPECIFICATION — not API-verified",
            "Tick size/value and account currency/leverage remain UNKNOWN for XAUUSDm",
            "Partial trading sessions (Monday–Thursday segment_2 end truncated)",
            "Slippage/spread/latency UNKNOWN without reference quotes",
        ],
        "low": [
            "CSV header map awaits first genuine XAUUSDm export inspection results",
            "Market sell USD/lot margin reported null/truncated",
        ],
    }
    defects["high"] = [x for x in defects["high"] if x]

    report = [
        "# Phase 63 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Automated Orders:** `DISABLED` | **Demo Collection:** `READ_ONLY`",
        f"**Reason:** {reason}",
        f"**Generated:** {_utc()}",
        "",
        "## Files created",
        "- `src/phase63/**` (new)",
        "- `tests/phase63/**` (new)",
        "- `reports/phase63/**` (new)",
        "- `src/data/phase63/account_metadata/**` (new)",
        "- `src/data/phase63/account_metadata/**` and `exness_demo_execution/**` (Phase63-owned; Phase62 intake untouched)",
        "",
        "## Phase 0–62 immutability",
        f"- Source modified: `{integrity.get('phase0_62_source_modified')}`",
        f"- Phase62 report present: `{integrity.get('phase62_report_present')}`",
        f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
        "- Phase62 intake path not written by Phase63 (test isolation preserved)",
        "",
        "## Broker metadata correction (XAUUSD → XAUUSDm)",
        f"- Previous symbol: **{SUPERSEDED_SYMBOL}** → status `SUPERSEDED`",
        f"- Reason: `{metadata.get('supersession_reason')}`",
        f"- New active symbol: **{get_active_symbol()}**",
        f"- Leakage guards pass: `{len(leakage) == 0}` failures=`{leakage}`",
        f"- Artifact: `reports/phase63/broker_metadata_correction.json`",
        "",
        "## Active account metadata (provenance)",
        f"- Status: **{metadata.get('verification_status')}** | Profile: `{metadata.get('profile_status')}`",
        f"- Independently API-verified: `{metadata.get('independently_verified_via_api')}`",
        f"- Symbol: `{vals.get('symbol')}` | Platform: `{vals.get('platform')}` | Category: `{vals.get('category')}`",
        f"- Digits: `{vals.get('digits')}` | Contract size: `{vals.get('contract_size')}` `{vals.get('contract_size_unit')}`",
        f"- Margin currency: `{vals.get('margin_currency')}` | Profit currency: `{vals.get('profit_currency')}`",
        f"- Calculation mode: `{vals.get('calculation_mode')}` | Execution mode: `{vals.get('execution_mode')}`",
        f"- Tick size/value: `{vals.get('tick_size')}` / `{vals.get('tick_value')}` (UNKNOWN — not inherited)",
        f"- Account currency/leverage: `{vals.get('account_currency')}` / `{vals.get('account_leverage')}`",
        f"- Sessions completeness: `{(vals.get('trading_sessions') or {}).get('completeness')}`",
        f"- Credentials stored: `{metadata.get('credentials_stored')}`",
        f"- Missing specs: `{metadata.get('missing_specifications')}`",
        "",
        "## Actual CSV schema discovered",
        f"- Exports found: `{schema_report.get('n_exports')}`",
        f"- Status: `{schema_report.get('status')}`",
        f"- Per-file headers: `{schema_report.get('per_file_headers')}`",
        "",
        "## Genuine imported records",
        f"- Orders: `{n_orders}` | Deals: `{n_deals}` | Fills: `{n_fills}`",
        f"- Quarantine rows: `{qn}`",
        f"- Import totals: `{import_result.get('totals')}`",
        "",
        "## Missing execution-cost fields",
        f"- Missing commission n: `{economics.get('missing_commission_n')}`",
        f"- Missing treated as zero: `{economics.get('missing_treated_as_zero')}`",
        f"- Quote estimates called actual slippage: `{economics.get('quote_estimates_called_actual_slippage')}`",
        "",
        "## Evidence sufficiency",
        f"- Sufficient: `{sufficiency.get('sufficient')}`",
        f"- Observed: `{sufficiency.get('observed')}`",
        f"- Missing requirements: `{sufficiency.get('missing_sample_requirements')}`",
        f"- Thresholds lowered: `{sufficiency.get('thresholds_lowered')}`",
        "",
        "## Tests",
        f"- Unit: `{test_result.get('command')}` OK=`{test_result.get('ok')}` run=`{test_result.get('tests_run')}`",
        f"- Adversarial import audit pass: `{adv.get('pass')}`",
        "",
        "## Historical / shadow / demo separation",
        f"- Domains: `{integrity.get('domains')}`",
        f"- Merged: `{integrity.get('stores_merged')}`",
        "",
        "## Phase 58 holdout",
        f"- Sealed: `{integrity.get('phase58_holdout_sealed')}`",
        "",
        "## Artifact SHA-256",
        *[f"- `{k}`: `{v}`" for k, v in sorted(artifacts.items())],
        f"- validation: `{machine.get('sha256')}`",
        "",
        "## Remaining defects",
        "### High",
        *[f"- {x}" for x in defects["high"]],
        "### Medium",
        *[f"- {x}" for x in defects["medium"]],
        "### Low",
        *[f"- {x}" for x in defects["low"]],
        "",
        "## Next recommended action",
        f"1. Export **History → Deals** CSV from Exness MT5 demo for symbol **{ACTIVE_SYMBOL}** only.",
        f"2. Place file in `{EXPORTS_DIR}` (reject/quarantine non-{ACTIVE_SYMBOL} rows).",
        "3. Supply missing UNKNOWN fields (tick size/value, account currency/leverage, complete sessions) from MT5 Spec when available.",
        "4. Re-run `python -m phase63.run_phase63`. Do not start Phase 64 until this correction is confirmed.",
        "5. Keep Champion NO_MODEL / WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase63.run_phase63",
        ".\\.venv\\Scripts\\python.exe -m unittest phase63.tests.test_phase63",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE63_FINAL_REPORT.md", "\n".join(report))
    write_text(
        DOCS_DIR / "PHASE_63_EXNESS_DEMO_EVIDENCE.md",
        f"# Phase 63\n\n**Verdict:** `{verdict}`\n\n{reason}\n\nSee `reports/phase63/PHASE63_FINAL_REPORT.md`.\n",
    )
    print(verdict, reason)
    print("report", REPORTS_DIR / "PHASE63_FINAL_REPORT.md")
    return 0 if test_result.get("ok") and adv.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
