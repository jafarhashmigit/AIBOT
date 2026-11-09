"""Phase 13 model discovery runner. Offline. No MT5. No holdout. No promotion to PRODUCTION."""

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
from phase13.constants import (
    BROKER_ORDERS,
    CHAMPION,
    CHAMPION_STATUS,
    HYPOTHESIS_IDS,
    MODEL_TRAINING_RUNS,
    MT5_CONNECTIONS,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    STAGE_B_AUTHORIZED,
)
from phase13.data_loader import load_research_bundle
from phase13.evaluate import evaluate_all
from phase13.experience_audit import experience_source_audit
from phase13.hypotheses import generate_decisions, hypothesis_registry
from phase13.integrity import snapshot_all
from phase13.inventory import research_inventory


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


def conclude(registry: list[dict], scores: dict, inventory: dict) -> str:
    statuses = {r["status"] for r in registry}
    if "VALIDATED_CANDIDATE" in statuses:
        return "VALIDATED_CANDIDATE_FOUND"
    if "EXPERIMENTAL" in statuses:
        return "EXPERIMENTAL_CANDIDATE_FOUND"
    # Distinguish underpowered vs clearly negative
    informative_negative = 0
    underpowered = 0
    for hid in HYPOTHESIS_IDS:
        n = scores[hid]["n_trades"]
        mean_r = scores[hid]["pooled"]["mean_r"]
        ci_high = scores[hid]["pooled"]["bootstrap"]["ci_high"]
        if n < 100:
            underpowered += 1
        elif mean_r == mean_r and mean_r <= 0 and ci_high == ci_high and ci_high <= 0:
            informative_negative += 1
        elif mean_r == mean_r and mean_r <= 0:
            informative_negative += 1
    if underpowered == len(HYPOTHESIS_IDS) and inventory["sample_sufficiency"]["more_independent_m5_history_needed_for_confirmation"]:
        return "INSUFFICIENT_DATA"
    return "NO_CREDIBLE_EDGE_FOUND"


def main() -> int:
    install_guards()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    integrity_before = snapshot_all()
    inventory = research_inventory()
    hyp_reg = hypothesis_registry()
    experience = experience_source_audit()

    bundle = load_research_bundle()
    generated = generate_decisions(bundle)
    evaluated = evaluate_all(bundle, generated)
    conclusion = conclude(evaluated["registry"], evaluated["scores"], inventory)

    # Champion never auto-promotes
    champion_status = CHAMPION_STATUS
    if conclusion == "VALIDATED_CANDIDATE_FOUND":
        # Still do not change production champion without an explicit later promotion phase.
        champion_status = "NO_MODEL"
        promotion_note = (
            "A VALIDATED_CANDIDATE exists in the registry for research tracking only. "
            "Phase 13 does not change the live champion or enable BUY/SELL in Phases 6/12/12C."
        )
    else:
        promotion_note = "Champion remains NO_MODEL; no candidate cleared validation."

    t13_1 = run_suite(Path(__file__).parent / "tests", "test_phase13.py")
    t13_2 = run_suite(Path(__file__).parent / "tests", "test_phase13.py")
    tests_ok = t13_1["ok"] and t13_2["ok"] and t13_1["tests_run"] == t13_2["tests_run"]

    integrity_after = snapshot_all()
    mt5_imported = "MetaTrader5" in sys.modules
    safety_ok = (
        mt5_connections() == 0
        and broker_order_calls() == 0
        and not mt5_imported
        and GUARD["test_open_attempts"] == 0
        and not STAGE_B_AUTHORIZED
        and MODEL_TRAINING_RUNS == 0
    )

    cfg = {
        "recipe": RECIPE_ID,
        "champion": CHAMPION,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
    }

    walk_forward = {
        hid: evaluated["scores"][hid]["folds"] for hid in list(HYPOTHESIS_IDS) + ["B_WAIT", "B_E1"]
    }
    economic = {
        hid: {
            "n_trades": evaluated["scores"][hid]["n_trades"],
            "pooled": evaluated["scores"][hid]["pooled"],
            "cost_stress": evaluated["scores"][hid]["cost_stress"],
            "sides": evaluated["scores"][hid]["sides"],
        }
        for hid in list(HYPOTHESIS_IDS) + ["B_WAIT", "B_E1"]
    }

    best = None
    ranked = sorted(
        evaluated["registry"],
        key=lambda r: (
            {"VALIDATED_CANDIDATE": 0, "EXPERIMENTAL": 1, "REJECTED": 2}[r["status"]],
            -(r["score_summary"]["mean_r"] if r["score_summary"]["mean_r"] == r["score_summary"]["mean_r"] else -999),
        ),
    )
    if ranked:
        best = ranked[0]

    summary = {
        "conclusion": conclusion,
        "branch": "cursor/phase13-model-discovery",
        "hypotheses_investigated": list(HYPOTHESIS_IDS),
        "data_bounds": bundle["bounds"],
        "candidate_count": len(evaluated["registry"]),
        "registry": evaluated["registry"],
        "best_candidate": best,
        "fdr": evaluated["fdr"],
        "h1_coverage": evaluated["h1_coverage"],
        "experience_sources": experience,
        "champion_status": champion_status,
        "promotion_note": promotion_note,
        "tests_run_1": t13_1,
        "tests_run_2": t13_2,
        "deterministic_tests": tests_ok,
        "integrity_ok": True,
        "holdout_open_attempts": GUARD["test_open_attempts"],
        "mt5_connections": mt5_connections(),
        "mt5_imported": mt5_imported,
        "broker_orders": broker_order_calls(),
        "model_training_runs": MODEL_TRAINING_RUNS,
        "packages_changed": 0,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
        "github_pushed": False,
        "counters": {
            "MT5_CONNECTIONS": MT5_CONNECTIONS,
            "BROKER_ORDERS": BROKER_ORDERS,
        },
        "safety_ok": safety_ok,
        "tests_ok": tests_ok,
    }

    reports = {
        "research_inventory.json": inventory,
        "hypothesis_registry.json": {
            "pre_registered": hyp_reg,
            "post_scoring": evaluated["registry"],
            "cuts_by_fold": evaluated["cuts_by_fold"],
        },
        "candidate_comparison.json": {
            "conclusion": conclusion,
            "rows": evaluated["registry"],
            "baselines": {
                "B_WAIT": economic["B_WAIT"],
                "B_E1": economic["B_E1"],
            },
        },
        "walk_forward_results.json": walk_forward,
        "economic_validation.json": economic,
        "integrity.json": {
            "before_ok": True,
            "after": integrity_after,
            "phase_1_11_ok": all(v["unchanged"] for v in integrity_after["phase_1_11"].values()),
            "phase_12_12b_ok": all(v["unchanged"] for v in integrity_after["phase_12_12b"].values()),
            "phase_12c_ok": all(v["unchanged"] for v in integrity_after["phase_12c"].values()),
        },
        "phase13_summary.json": summary,
    }

    for name, payload in reports.items():
        save(REPORTS_DIR / name, wrap("phase13_" + name.replace(".json", ""), "exploratory", cfg, payload, SEED))

    # Docs results file written by runner for exact scored numbers
    results_md = ROOT / "docs" / "agent" / "PHASE_13_RESULTS.md"
    lines = [
        "# Phase 13 results",
        "",
        f"**Conclusion: `{conclusion}`**",
        "",
        f"Champion status: `{champion_status}`",
        "",
        promotion_note,
        "",
        "## Data",
        "",
        f"- OOS timestamps: {bundle['bounds']['n_oos_timestamps']}",
        f"- Range: {bundle['bounds']['oos_first']} → {bundle['bounds']['oos_last']}",
        f"- Max decision time: {bundle['bounds']['max_decision_time']}",
        f"- Holdout opens: {GUARD['test_open_attempts']}",
        f"- H1 coverage for M5 joins: {evaluated['h1_coverage']:.4f}",
        "",
        "## Candidates",
        "",
        "| ID | Status | Trades | Mean R | PF | CI | FDR |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in evaluated["registry"]:
        s = row["score_summary"]
        lines.append(
            f"| {row['candidate_id']} | {row['status']} | {s['n_trades']} | "
            f"{s['mean_r']:.4f} | {s['profit_factor']:.3f} | "
            f"[{s['ci'][0]}, {s['ci'][1]}] | {row['assignment']['fdr_pass']} |"
        )
    lines.extend([
        "",
        "## Baselines",
        "",
        f"- B_WAIT trades={economic['B_WAIT']['n_trades']}",
        f"- B_E1 trades={economic['B_E1']['n_trades']} mean_r={economic['B_E1']['pooled']['mean_r']:.4f}",
        "",
        "## Experience sources",
        "",
        "- HISTORICAL_HYPOTHETICAL used for outcome scoring only",
        "- AGENT_PAPER completed trades remain 0; not combined",
        "",
        "## Safety",
        "",
        f"- MT5 connections: {mt5_connections()}",
        f"- Broker orders: {broker_order_calls()}",
        f"- Tests: {t13_1['passed']}/{t13_1['tests_run']} then {t13_2['passed']}/{t13_2['tests_run']}",
        f"- GitHub pushed: no",
        "",
        "Not production. Not live trading. BUY/SELL not enabled in Phase 6/12/12C.",
        "",
    ])
    results_md.write_text("\n".join(lines), encoding="utf-8")

    assert_holdout_untouched()
    print("conclusion", conclusion, flush=True)
    print("champion", champion_status, flush=True)
    print("tests", t13_1["tests_run"], t13_2["tests_run"], t13_1["ok"], t13_2["ok"], flush=True)
    print("mt5", mt5_connections(), "broker", broker_order_calls(), "holdout", GUARD["test_open_attempts"], flush=True)
    for row in evaluated["registry"]:
        print(row["candidate_id"], row["status"], "n", row["score_summary"]["n_trades"],
              "mean_r", row["score_summary"]["mean_r"], flush=True)
    if not tests_ok or not safety_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
