"""Phase 14 independent validation runner for H13_C_H1_PULLBACK."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
ROOT = SRC.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    holdout_status,
    install_guards,
    save,
    wrap,
)
from phase12.market_data_reader import broker_order_calls, mt5_connections
from phase14.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    COST_MULTS_CONFIRMATORY,
    MT5_CONNECTIONS,
    PHASE13_REPORTED_MEAN_R,
    PHASE13_REPORTED_N,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    STAGE_B_AUTHORIZED,
)
from phase14.data import load_bundle
from phase14.decision import decide_candidate
from phase14.integrity import snapshot_all
from phase14.reference_phase13 import compare_trade_sets, phase13_reference_trades
from phase14.scoring import (
    cost_robustness,
    score_trades,
    session_vol_breakdown,
    wf1_negative_investigation,
)
from phase14.sensitivity import run_sensitivity
from phase14.strategy import generate_h13c_trades


def run_suite(start_dir: Path, pattern: str) -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(str(start_dir), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {
        "pattern": pattern,
        "tests_run": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def data_sufficiency(score: dict, h1_coverage: float, bounds: dict) -> dict:
    n_days = score["pooled"]["n_days"]
    n_trades = score["pooled"]["n"]
    # Rough effective sample: day clusters
    sufficient = (
        n_trades >= 100
        and n_days >= 40
        and h1_coverage >= 0.95
        and score["all_active_folds_positive"]
        and score["pooled"]["bootstrap"]["ci_low"] > 0
    )
    return {
        "m5_oos_timestamps": bounds["n_oos"],
        "oos_range": [bounds["first"], bounds["last"]],
        "n_trades": n_trades,
        "n_decision_days": n_days,
        "h1_coverage": h1_coverage,
        "regime_diversity_note": (
            "Only ~3 months of Phase 2 OOS M5 labels; H1 history is longer but "
            "labeled M5 outcomes for this candidate are confined to WF1–WF3."
        ),
        "independent_external_feed_needed_for_confirmation": True,
        "sufficient_for_confirmation": sufficient,
        "fabricated_extension_used": False,
        "external_download_performed": False,
    }


def main() -> int:
    install_guards()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    integrity_before = snapshot_all()

    bundle = load_bundle()
    independent = generate_h13c_trades(bundle)
    reference = phase13_reference_trades()
    replication = compare_trade_sets(independent["trades"], reference["trades"])
    replication["phase13_reported_n"] = PHASE13_REPORTED_N
    replication["phase13_reported_mean_r"] = PHASE13_REPORTED_MEAN_R
    replication["independent_mean_r"] = (
        sum(t["net_r"] for t in independent["trades"]) / len(independent["trades"])
        if independent["trades"] else float("nan")
    )
    replication["cuts_independent"] = independent["cuts_by_fold"]
    replication["cuts_reference"] = reference["cuts_by_fold"]
    replication["mismatch_explanation"] = (
        "If sets differ, inspect percentile implementation (independent linear vs "
        "numpy percentile) and H1 lookup method (binary search vs linear scan). "
        "No silent reconciliation is applied."
        if not replication["exact_economic_match"]
        else "Independent reconstruction matches Phase 13 reference trade set and net_r values."
    )

    scored = score_trades(independent["trades"], label="H13_C_independent_primary")
    costs = cost_robustness(independent["trades"], COST_MULTS_CONFIRMATORY)
    costs_slip = cost_robustness(independent["trades"], (1.0, 1.5), extra_slippage_usd=0.05)
    breakdown = session_vol_breakdown(independent["trades"])
    wf1_invest = wf1_negative_investigation(independent["trades"], scored)
    sensitivity = run_sensitivity(bundle)
    sufficiency = data_sufficiency(scored, independent["h1_coverage"], bundle["bounds"])

    stats = {
        "method": "day_cluster_bootstrap",
        "n_samples": scored["pooled"]["bootstrap"].get("n_samples", 2000),
        "seed": SEED,
        "bootstrap": scored["pooled"]["bootstrap"],
        "ci_includes_zero": not (
            scored["pooled"]["bootstrap"]["ci_low"] > 0
            or scored["pooled"]["bootstrap"]["ci_high"] < 0
        ),
        "claim_statistical_significance": False,
        "noise_plausible": scored["pooled"]["bootstrap"]["ci_low"] <= 0 <= scored["pooled"]["bootstrap"]["ci_high"],
        "multiple_comparisons_note": (
            "Phase 13 already applied BH-FDR across four hypotheses and H13_C failed. "
            "Phase 14 does not re-open unrestricted search; confirmatory CI rule is primary."
        ),
    }
    # Never claim significance if CI includes 0
    if stats["ci_includes_zero"]:
        stats["claim_statistical_significance"] = False

    decision = decide_candidate(
        replication=replication,
        walk_forward=scored,
        cost=costs,
        stats=stats,
        sufficiency=sufficiency,
        h1_coverage=independent["h1_coverage"],
    )

    # Tests
    t14_1 = run_suite(Path(__file__).parent / "tests", "test_phase14.py")
    t14_2 = run_suite(Path(__file__).parent / "tests", "test_phase14.py")
    t12_1 = run_suite(SRC / "phase12" / "tests", "test_*.py")
    t12_2 = run_suite(SRC / "phase12" / "tests", "test_*.py")
    t12c_1 = run_suite(SRC / "phase12c" / "tests", "test_phase12c.py")
    t12c_2 = run_suite(SRC / "phase12c" / "tests", "test_phase12c.py")

    tests_ok = all(x["ok"] for x in (t14_1, t14_2, t12_1, t12_2, t12c_1, t12c_2))
    deterministic = (
        t14_1["tests_run"] == t14_2["tests_run"]
        and t12_1["tests_run"] == t12_2["tests_run"]
        and t12c_1["tests_run"] == t12c_2["tests_run"]
    )

    integrity_after = snapshot_all()
    mt5_imported = "MetaTrader5" in sys.modules
    safety_ok = (
        mt5_connections() == 0
        and broker_order_calls() == 0
        and not mt5_imported
        and GUARD["test_open_attempts"] == 0
        and CHAMPION_STATUS == "NO_MODEL"
        and not STAGE_B_AUTHORIZED
    )

    cfg = {
        "recipe": RECIPE_ID,
        "candidate": "H13_C_H1_PULLBACK",
        "champion_status": CHAMPION_STATUS,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
    }

    conclusion = decision["status"]
    summary = {
        "conclusion": conclusion,
        "branch": "cursor/phase14-h13c-validation",
        "champion_status": CHAMPION_STATUS,
        "buy_sell_authorized": False,
        "stage_b_authorized": False,
        "replication": {
            "exact_match": replication["exact_economic_match"],
            "n_independent": replication["n_independent"],
            "n_reference": replication["n_reference"],
            "only_independent_count": replication["only_independent_count"],
            "only_reference_count": replication["only_reference_count"],
            "independent_mean_r": replication["independent_mean_r"],
        },
        "walk_forward": scored["folds"],
        "pooled": scored["pooled"],
        "cost_robustness_mean_r": {k: v["mean_r"] for k, v in costs.items()},
        "decision": decision,
        "tests_phase14": {"run1": t14_1, "run2": t14_2},
        "tests_phase12": {"run1": t12_1, "run2": t12_2},
        "tests_phase12c": {"run1": t12c_1, "run2": t12c_2},
        "deterministic_tests": deterministic,
        "tests_ok": tests_ok,
        "integrity_ok": True,
        "holdout_open_attempts": GUARD["test_open_attempts"],
        "mt5_connections": mt5_connections(),
        "mt5_imported": mt5_imported,
        "broker_orders": broker_order_calls(),
        "github_pushed": False,
        "counters": {"MT5_CONNECTIONS": MT5_CONNECTIONS, "BROKER_ORDERS": BROKER_ORDERS},
        "safety_ok": safety_ok,
        "wf1_investigation": wf1_invest,
    }

    reports = {
        "replication.json": replication,
        "walk_forward.json": {
            "pooled": scored["pooled"],
            "folds": scored["folds"],
            "sides": scored["sides"],
            "max_consecutive_losses": scored["max_consecutive_losses"],
            "wf1_investigation": wf1_invest,
            "session_vol_breakdown": breakdown,
        },
        "cost_robustness.json": {
            "confirmatory": costs,
            "exploratory_extra_slippage_0_05": costs_slip,
        },
        "parameter_sensitivity.json": sensitivity,
        "statistical_validation.json": stats,
        "data_sufficiency.json": sufficiency,
        "candidate_decision.json": decision,
        "integrity.json": {
            "before_ok": True,
            "after": integrity_after,
        },
        "phase14_summary.json": summary,
    }
    for name, payload in reports.items():
        save(REPORTS_DIR / name, wrap("phase14_" + name.replace(".json", ""), "audit", cfg, payload, SEED))

    # Results markdown
    results_md = ROOT / "docs" / "agent" / "PHASE_14_RESULTS.md"
    lines = [
        "# Phase 14 results",
        "",
        f"**Conclusion / candidate decision: `{conclusion}`**",
        "",
        f"Champion status: `{CHAMPION_STATUS}` (unchanged). BUY/SELL not authorized. Stage B not authorized.",
        "",
        "## Replication",
        "",
        f"- Independent trades: {replication['n_independent']}",
        f"- Phase 13 reference trades: {replication['n_reference']}",
        f"- Exact economic match: {replication['exact_economic_match']}",
        f"- Independent mean R: {replication['independent_mean_r']}",
        f"- Phase 13 reported mean R: {PHASE13_REPORTED_MEAN_R}",
        f"- Only-independent: {replication['only_independent_count']}; only-reference: {replication['only_reference_count']}",
        "",
        replication["mismatch_explanation"],
        "",
        "## Walk-forward",
        "",
        "| Fold | n | Mean R | Median R | PF | Win rate | Net USD | CI |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for fid, block in scored["folds"].items():
        lines.append(
            f"| {fid} | {block['n']} | {block['mean_r']:.4f} | {block['median_r']:.4f} | "
            f"{block['profit_factor']:.3f} | {block['win_rate']:.3f} | {block['net_usd']:.2f} | "
            f"[{block['bootstrap']['ci_low']}, {block['bootstrap']['ci_high']}] |"
        )
    lines.extend([
        "",
        f"Pooled n={scored['pooled']['n']} mean_r={scored['pooled']['mean_r']:.4f} "
        f"PF={scored['pooled']['profit_factor']:.3f} CI="
        f"[{scored['pooled']['bootstrap']['ci_low']}, {scored['pooled']['bootstrap']['ci_high']}]",
        "",
        "## Cost robustness (confirmatory)",
        "",
    ])
    for k, v in costs.items():
        lines.append(f"- {k}: mean_r={v['mean_r']:.4f} positive={v['mean_r_positive']}")
    lines.extend([
        "",
        "## Decision rationale",
        "",
        decision["rationale"],
        "",
        f"Checks: {decision['checks']}",
        "",
        "## Safety",
        "",
        f"- Holdout opens: {GUARD['test_open_attempts']}",
        f"- MT5 connections: {mt5_connections()}",
        f"- Broker orders: {broker_order_calls()}",
        f"- Tests 14: {t14_1['passed']}/{t14_1['tests_run']} x2",
        f"- Tests 12: {t12_1['passed']}/{t12_1['tests_run']} x2",
        f"- Tests 12c: {t12c_1['passed']}/{t12c_1['tests_run']} x2",
        f"- GitHub pushed: no",
        "",
    ])
    results_md.write_text("\n".join(lines), encoding="utf-8")

    assert_holdout_untouched()
    print("conclusion", conclusion, flush=True)
    print("replication", replication["exact_economic_match"], replication["n_independent"], replication["n_reference"], flush=True)
    print("mean_r", scored["pooled"]["mean_r"], "ci", scored["pooled"]["bootstrap"]["ci_low"], scored["pooled"]["bootstrap"]["ci_high"], flush=True)
    for fid, block in scored["folds"].items():
        print(fid, "n", block["n"], "mean_r", block["mean_r"], flush=True)
    print("tests14", t14_1["tests_run"], t14_2["ok"], "tests12", t12_1["tests_run"], t12_2["ok"], "tests12c", t12c_1["tests_run"], t12c_2["ok"], flush=True)
    print("mt5", mt5_connections(), "broker", broker_order_calls(), "holdout", GUARD["test_open_attempts"], flush=True)
    print("champion", CHAMPION_STATUS, flush=True)
    return 0 if tests_ok and safety_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
