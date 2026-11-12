"""Phase 60 runner — execution reality & coverage; CLI only; no autostart."""

from __future__ import annotations

import json
import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase60.adapters import holdout_days, inventory, null_policy_ok
from phase60.audit_phase59 import run_independent_phase59_audit
from phase60.commission import CommissionModel, investigate_commission
from phase60.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    PHASE59_REPORTS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    canonical_json_sha256,
    file_sha256,
)
from phase60.coverage_matrix import build_market_coverage_matrix
from phase60.deep_audit import audit_remaining_days, build_integrity_summary, build_updated_coverage
from phase60.experience_audit import audit_experience
from phase60.gap_through import audit_phase56_behavior, build_sl_tp_cases
from phase60.paired_stats import paired_summaries
from phase60.progress import write_json, write_text
from phase60.reconstruct_events import reconstruct_paired
from phase60.slippage import (
    analyze_slippage_proxy,
    build_execution_price_semantics,
    build_slippage_methodology,
)
from phase60.verdict import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_phase60_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName("phase60.tests.test_phase60")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tests_run": 0, "failures": 1, "errors": 1}
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "command": "python -m unittest phase60.tests.test_phase60",
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("phase59_independent_audit", flush=True)
    p59_audit = run_independent_phase59_audit()
    write_json(REPORTS_DIR / "phase59_independent_audit.json", p59_audit)

    remaining_days = list(p59_audit.get("remaining_10_days") or [])
    print("deep_audit_remaining", len(remaining_days), flush=True)
    remaining = audit_remaining_days(remaining_days)
    write_json(REPORTS_DIR / "deep_audit_remaining_days.json", remaining)

    inv = inventory()
    cov59 = {}
    integ59 = {}
    cov59_path = PHASE59_REPORTS / "data_coverage_manifest.json"
    integ59_path = PHASE59_REPORTS / "dataset_integrity.json"
    if cov59_path.is_file():
        cov59 = json.loads(cov59_path.read_text(encoding="utf-8"))
    if integ59_path.is_file():
        integ59 = json.loads(integ59_path.read_text(encoding="utf-8"))

    coverage = build_updated_coverage(
        phase59_deep_days=list(cov59.get("deep_tick_audit_days") or []),
        remaining_audit=remaining,
        union_days=list(inv.get("union_days") or []),
    )
    write_json(REPORTS_DIR / "updated_data_coverage_manifest.json", coverage)

    integrity_summary = build_integrity_summary(
        phase59_integrity=integ59, remaining_audit=remaining, coverage=coverage
    )
    write_json(REPORTS_DIR / "data_integrity_summary.json", integrity_summary)

    print("commission_investigation", flush=True)
    commission = investigate_commission()
    write_json(REPORTS_DIR / "commission_evidence.json", commission)
    # Prove model refuses adjusted perf when UNKNOWN
    cm = CommissionModel(commission)
    assert cm.commission_adjusted_net_r(gross_r=1.0, risk_amount=10.0, lots=0.1, sides=2) is None

    semantics = build_execution_price_semantics()
    slip_method = build_slippage_methodology()
    write_json(REPORTS_DIR / "execution_price_semantics.json", semantics)
    write_json(REPORTS_DIR / "slippage_methodology.json", slip_method)

    print("gap_through_cases", flush=True)
    gap_audit = audit_phase56_behavior()
    sl_tp_cases = build_sl_tp_cases()
    write_json(REPORTS_DIR / "gap_through_execution_audit.json", gap_audit)
    write_json(REPORTS_DIR / "sl_tp_execution_cases.json", sl_tp_cases)

    # Reconstruct paired events on same stress window as Phase59 (non-holdout)
    stress_days = list(cov59.get("stress_days") or [])[:12]
    print("reconstruct_paired", len(stress_days), flush=True)
    events = reconstruct_paired(stress_days)
    paired = paired_summaries(
        [{"event_id": e["event_id"], "day": e["day"], "buy_net_r": e["buy_net_r"], "sell_net_r": e["sell_net_r"]} for e in events]
    )
    write_json(REPORTS_DIR / "paired_statistical_audit.json", paired)

    # Slippage proxy from reconstructed entries (intended=mid, fill=entry executable)
    proxy_obs = []
    for e in events:
        mid_buy = None
        try:
            mid_buy = (float(e["buy_entry_bid"]) + float(e["buy_entry_ask"])) / 2.0
        except Exception:
            pass
        proxy_obs.append(
            {
                "event_id": e["event_id"],
                "day": e["day"],
                "action": "BUY",
                "leg": "ENTRY",
                "intended": mid_buy,
                "fill": e.get("buy_entry_ask"),
            }
        )
        mid_sell = None
        try:
            mid_sell = (float(e["sell_entry_bid"]) + float(e["sell_entry_ask"])) / 2.0
        except Exception:
            pass
        proxy_obs.append(
            {
                "event_id": e["event_id"],
                "day": e["day"],
                "action": "SELL",
                "leg": "ENTRY",
                "intended": mid_sell,
                "fill": e.get("sell_entry_bid"),
            }
        )
    slip_proxy = analyze_slippage_proxy(proxy_obs)
    write_json(REPORTS_DIR / "slippage_proxy_analysis.json", slip_proxy)

    print("market_coverage_matrix", flush=True)
    # Prefer research days = union minus holdout; bound for runtime using preferred deep set
    research_days = [d for d in (cov59.get("deep_tick_audit_days") or []) if d not in set(holdout_days())]
    # Include newly audited remaining days that are not holdout
    research_days = sorted(set(research_days) | set(remaining_days))
    research_days = [d for d in research_days if d not in set(holdout_days())]
    # Bound matrix scan for practicality: first 40 research days + remaining
    matrix_days = sorted(set(research_days[:40]) | set(remaining_days))
    matrix_days = [d for d in matrix_days if d not in set(holdout_days())]
    market = build_market_coverage_matrix(matrix_days)
    write_json(REPORTS_DIR / "market_coverage_matrix.json", market)

    print("experience_integrity", flush=True)
    experience = audit_experience()
    write_json(REPORTS_DIR / "experience_integrity_audit.json", experience)

    print("tests", flush=True)
    test_result = _run_phase60_tests()
    write_json(REPORTS_DIR / "test_results.json", test_result)

    holdout_sealed = True
    # Ensure we did not list holdout in stress reconstruction
    if any(e.get("day") in set(holdout_days()) for e in events):
        holdout_sealed = False
    null_ok = null_policy_ok(EXPECTED_NULL_POLICY)

    verdict, reason = choose_verdict(
        phase59_audit=p59_audit,
        remaining=remaining,
        coverage=coverage,
        commission=commission,
        slippage_method=slip_method,
        experience=experience,
        holdout_sealed=holdout_sealed,
        null_ok=null_ok,
        tests_ok=bool(test_result.get("ok")),
    )

    runtime_s = time.perf_counter() - t0
    artifacts = {
        name: file_sha256(REPORTS_DIR / name)
        for name in sorted(p.name for p in REPORTS_DIR.glob("*.json"))
    }
    machine = {
        "recipe": RECIPE_ID,
        "verdict": verdict,
        "verdict_reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live_trading": LIVE_TRADING,
        "null_policy_ok": null_ok,
        "holdout_sealed": holdout_sealed,
        "phase58_holdout": holdout_days(),
        "remaining_10": remaining_days,
        "remaining_pass_n": remaining.get("n_pass_defined_audit"),
        "hundred_day_claim": coverage.get("hundred_day_coverage_claim_permitted"),
        "commission_status": commission.get("commission_status"),
        "actual_slippage_status": slip_method.get("actual_slippage_status"),
        "paired_n_events": paired.get("n_unique_events"),
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
            "Commission schedule UNKNOWN for target venue/account",
            "Actual broker slippage UNKNOWN (proxy only)",
        ],
        "medium": [
            "Major disruption events unlabeled",
            "100-day coverage claim depends on remaining-day audit outcomes",
            "Phase59 BOTH n=94 inflated independent-event interpretation (corrected here)",
        ],
        "low": [
            "Heuristic session/regime labels only",
            "Market coverage matrix bounded subset for runtime",
        ],
    }
    if remaining.get("n_fail"):
        defects["high"].append(f"Remaining-day audit failures: {remaining.get('failed_days')}")

    report = [
        "# Phase 60 — Final Report",
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
        "## 2. Phase 59 independent audit",
        f"- Critical checks pass: `{p59_audit.get('all_critical_checks_pass')}`",
        f"- Union days live: `{p59_audit.get('union_n_days_live')}`",
        f"- Deep audit n: `{p59_audit.get('deep_tick_audit_days_n')}`",
        f"- Remaining 10: `{remaining_days}`",
        f"- All remaining locatable: `{p59_audit.get('all_remaining_locatable')}`",
        f"- Coverage SHA reproducible: `{(p59_audit.get('checks') or {}).get('coverage_sha_reproducible')}`",
        f"- Artifact: `reports/phase60/phase59_independent_audit.json`",
        "",
        "## 3. Remaining 10-day deep audit",
        f"- Pass defined audit: `{remaining.get('n_pass_defined_audit')}` / `{remaining.get('n_days')}`",
        f"- Fail: `{remaining.get('failed_days')}`",
        f"- Added M5 bars: `{remaining.get('total_m5_bars')}`; ticks: `{remaining.get('total_ticks')}`",
        f"- Source silently repaired: `{remaining.get('source_silently_repaired')}`",
        "",
        "## 4. Final verified archive coverage",
        f"- Original Phase59 deep n: `{coverage.get('original_phase59_deep_audit_n')}`",
        f"- Final verified deep n: `{coverage.get('final_verified_deep_audit_n')}`",
        f"- 100-day claim permitted: `{coverage.get('hundred_day_coverage_claim_permitted')}`",
        f"- Still not verified: `{coverage.get('still_not_verified_deep')}`",
        "",
        "## 5. Commission evidence",
        f"- Status: **{commission.get('commission_status')}**",
        f"- Target venue established: `{commission.get('target_venue_established')}`",
        f"- Model refuses adjusted performance when UNKNOWN: `{cm.commission_adjusted_net_r(gross_r=1.0, risk_amount=1.0) is None}`",
        "",
        "## 6. Slippage: actual vs proxy",
        f"- Actual slippage: **{slip_method.get('actual_slippage_status')}**",
        f"- Proxy name: `{slip_method.get('proxy_name')}`",
        f"- Proxy n_computed: `{slip_proxy.get('n_computed')}`; mean_adverse_proxy: `{slip_proxy.get('mean_adverse_proxy')}`",
        f"- Live execution cost claim: `{slip_proxy.get('live_execution_cost_claim')}`",
        "",
        "## 7. Gap-through SL/TP",
        f"- Phase60 modifies prior phases: `{gap_audit.get('phase60_changes_to_prior_phases')}`",
        f"- Synthetic cases pass: `{sl_tp_cases.get('n_pass')}` / `{sl_tp_cases.get('n_cases')}`",
        f"- Broker fill behavior: `{gap_audit.get('broker_specific_fill_behavior')}`",
        "",
        "## 8. Market coverage matrix",
        f"- Research days scanned (bounded): `{market.get('research_days_n')}`",
        f"- Holdout excluded: `{market.get('holdout_excluded')}`",
        f"- Missing/weak: `{market.get('missing_or_weak')}`",
        f"- Major disruptions labeled: `{(market.get('major_disruption_labels') or {}).get('available')}`",
        "",
        "## 9. Paired BUY/SELL statistical corrections",
        f"- Unique events: `{paired.get('n_unique_events')}`",
        f"- Side observations: `{paired.get('n_side_observations')}`",
        f"- Correction: {paired.get('correction')}",
        f"- Within-event BUY−SELL mean: `{(paired.get('descriptive') or {}).get('within_event_buy_minus_sell_mean')}`",
        f"- Event bootstrap BUY−SELL CI95: `{(paired.get('inferential') or {}).get('buy_minus_sell_mean_ci95')}`",
        "",
        "## 10. Historical / shadow experience integrity",
        f"- Hist n: `{(experience.get('historical_hypothetical') or {}).get('n')}`",
        f"- Shadow n: `{(experience.get('agent_shadow') or {}).get('n')}`",
        f"- Merged: `{experience.get('stores_merged')}`",
        f"- Fabricated: `{experience.get('records_fabricated')}`",
        f"- Unknown commission/slippage preserved: `{experience.get('unknown_commission_preserved')}` / `{experience.get('unknown_slippage_preserved')}`",
        "",
        "## 11. Tests",
        f"- Command: `{test_result.get('command')}`",
        f"- OK: `{test_result.get('ok')}` run=`{test_result.get('tests_run')}` "
        f"fail=`{test_result.get('failures')}` err=`{test_result.get('errors')}`",
        "",
        "## 12. Artifact SHA-256",
        *[f"- `{k}`: `{v}`" for k, v in sorted(artifacts.items())],
        f"- validation_results: `{machine.get('sha256')}`",
        "",
        "## 13. Remaining defects",
        "### High",
        *[f"- {x}" for x in defects["high"]],
        "### Medium",
        *[f"- {x}" for x in defects["medium"]],
        "### Low",
        *[f"- {x}" for x in defects["low"]],
        "",
        "## 14. Production limitations",
        "- Production action remains WAIT; live trading NOT_AUTHORIZED.",
        "- Demo archives ≠ live broker matching, commission, or slippage.",
        "- Gap-through fills are historical-quote simulations, not broker-confirmed.",
        "- Heuristic regimes are not verified disruption labels.",
        "",
        "## 15. Next-phase prerequisites",
        "1. Verifiable commission schedule for the target venue/account/instrument (or explicit acceptance of UNKNOWN).",
        "2. Genuine fill records or measured slippage study vs intended price on target venue.",
        "3. Independently verifiable disruption/event labels if regime claims are required.",
        "4. Keep Phase58 holdout sealed until a preregistered survivor exists.",
        "5. Do not resume alpha search pretending cost unknowns are zero.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase60.run_phase60",
        ".\\.venv\\Scripts\\python.exe -m unittest phase60.tests.test_phase60",
        "```",
        "",
        f"Runtime s: `{runtime_s}`",
        "",
        "Phase0–59 unmodified. No live MT5. No broker orders. No autostart.",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE60_FINAL_REPORT.md", "\n".join(report))
    write_text(
        DOCS_DIR / "PHASE_60_EXECUTION_REALITY.md",
        "\n".join(
            [
                "# Phase 60 — Execution Reality & Market Coverage",
                "",
                f"**Verdict:** `{verdict}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                reason,
                "",
                "See `reports/phase60/PHASE60_FINAL_REPORT.md`.",
                "",
            ]
        ),
    )

    print(verdict, reason)
    print("report", REPORTS_DIR / "PHASE60_FINAL_REPORT.md")
    return 0 if test_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
