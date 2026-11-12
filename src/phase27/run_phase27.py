"""Phase 27 runner — volatility-aware H13_C decision research (offline)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phase14.data import load_bundle
from phase14.strategy import generate_h13c_trades
from phase26.data import load_decision_times, load_h1_bars, load_m5_bars
from phase26.features import compute_orthogonal_features
from phase26.outcomes import build_rich_outcomes
from phase27.analysis import (
    decide_verdict,
    enrich_trades,
    hypothetical_policies,
    regime_analysis,
    statistical_validation,
)
from phase27.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_Q_HIGH,
    H13C_Q_LOW,
    H13C_STATUS,
    PHASE25_VERDICT,
    PHASE26_VERDICT,
    PHASE26_ACCEPTED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REGIME_METHOD,
    RESEARCH_CUTOFF_UTC,
)
from phase27.evaluate import (
    build_summary,
    join_mfe_mae,
    mfe_mae_by_regime,
    write_reports,
)
from phase27.integrity import safety_audit
from phase27.vol_model import build_oof_vol_predictions


def write_docs(preflight, vol_audit, regime, policies, stats, safety, verdict, answers) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    plan = f"""# PHASE 27 — Research Plan

Recipe: `{RECIPE_ID}`

## Objective

Test whether Phase 26's improved `fwd_vol_12` prediction provides **decision-time** value for frozen H13_C BUY/SELL outcomes.

Protected posture: champion `{CHAMPION_STATUS}`, H13_C `{H13C_STATUS}`, production `{PRODUCTION_FINAL_ACTION}`, Phase25 `{PHASE25_VERDICT}`, Phase26 `{PHASE26_VERDICT}`.

## Predeclared methods

- Volatility model: Ridge(alpha=1.0) on baseline + Phase 26 accepted features.
- Walk-forward: WF1–WF3 with purge cutoff = fold_start − 60m.
- Regime method: **`{REGIME_METHOD}`** (tertiles of train *predicted* vol; never realized future vol for decision regimes).
- H13_C cuts frozen: q_low={H13C_Q_LOW}, q_high={H13C_Q_HIGH}.
- Hypothetical policies: baseline, skip_high, skip_low, high/medium/low-only (no threshold search).
- Primary hypotheses: 6 (Bonferroni α=0.05/6).

## Preflight

```json
{json.dumps(preflight, indent=2)}
```
"""
    (DOCS_DIR / "PHASE_27_RESEARCH_PLAN.md").write_text(plan + "\n", encoding="utf-8")

    lines = [
        "# PHASE 27 — Results",
        "",
        f"Verdict: **{verdict['verdict']}**",
        f"Rationale: {verdict['rationale']}",
        "",
        f"Champion `{verdict['champion_status']}` | H13_C `{verdict['h13c_status']}` | Production `{verdict['production_final_action']}`",
        f"Phase25 `{verdict['phase25_verdict_preserved']}` | Phase26 `{verdict['phase26_verdict_preserved']}`",
        "",
        "## Volatility prediction audit (independent recompute)",
        "",
        f"- Folds improved: {vol_audit.get('n_folds_improved')} / 3; all: {vol_audit.get('all_folds_improved')}",
        "",
    ]
    for fid, b in vol_audit.get("fold_audit", {}).items():
        if b.get("skipped"):
            lines.append(f"- {fid}: skipped")
            continue
        lines.append(
            f"- {fid}: baseline MAE={b['baseline']['mae']:.6g} → ortho MAE={b['baseline_plus_ortho']['mae']:.6g} "
            f"(Δ={b['mae_improvement']:.6g}, improved={b['improved']}); "
            f"class_acc={b.get('vol_class_accuracy')}; regime_agree={b.get('regime_agreement_rate')}"
        )
    lines.extend(["", "## Hypothetical policies vs baseline", ""])
    for name, p in policies["policies"].items():
        lines.append(
            f"- `{name}`: n={p['n']} mean_r={p['mean_r']} Δ={p.get('delta_mean_r_vs_baseline')} "
            f"PF={p['profit_factor']} win={p['win_rate']} cost1.5x={p.get('cost_1_5x_mean_r')}"
        )
    lines.extend(
        [
            "",
            "## Decision-quality answers",
            "",
            "```json",
            json.dumps(answers, indent=2),
            "```",
            "",
            "## Statistical notes",
            "",
            f"- Primary passes: {stats.get('n_primary_passed')} / 6",
            f"- Contradictory folds: {stats.get('contradictory_folds')}",
            "",
            "## Safety",
            "",
            "```json",
            json.dumps(safety.get("checks"), indent=2),
            "```",
            "",
            "## Commands",
            "",
            "```powershell",
            "$env:PYTHONPATH='src'",
            "python -m unittest phase27.tests.test_phase27 -v",
            "python -m phase27.run_phase27",
            "```",
            "",
        ]
    )
    (DOCS_DIR / "PHASE_27_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def decision_quality_answers(vol_audit, regime, policies, stats) -> dict:
    buy = regime["by_side_regime"]["BUY"]
    sell = regime["by_side_regime"]["SELL"]
    base = policies["policies"]["baseline_h13c"]
    skip_h = policies["policies"]["skip_high_pred_vol"]
    skip_l = policies["policies"]["skip_low_pred_vol"]
    return {
        "1_pred_vol_identifies_favorable_BUY": {
            "answer": "partial/unconfirmed",
            "evidence": {
                "buy_high_mean_r": buy["high"]["mean_r"],
                "buy_low_mean_r": buy["low"]["mean_r"],
                "n_high": buy["high"]["n"],
                "n_low": buy["low"]["n"],
                "sufficient": buy["high"]["sufficient_n"] and buy["low"]["sufficient_n"],
            },
        },
        "2_pred_vol_identifies_favorable_SELL": {
            "answer": "partial/unconfirmed",
            "evidence": {
                "sell_high_mean_r": sell["high"]["mean_r"],
                "sell_low_mean_r": sell["low"]["mean_r"],
                "n_high": sell["high"]["n"],
                "n_low": sell["low"]["n"],
            },
        },
        "3_helps_fav_vs_adverse": {
            "answer": "see mfe_mae_by_regime in h13c_regime_analysis",
            "note": "Uses Phase 26 MFE/MAE research labels joined retrospectively.",
        },
        "4_improves_net_expectancy_after_costs": {
            "answer": bool(
                (skip_h["mean_r"] > base["mean_r"] and skip_h.get("cost_1_5x_positive"))
                or (skip_l["mean_r"] > base["mean_r"] and skip_l.get("cost_1_5x_positive"))
            ),
            "baseline_mean_r": base["mean_r"],
            "skip_high_mean_r": skip_h["mean_r"],
            "skip_low_mean_r": skip_l["mean_r"],
        },
        "5_consistent_across_WF1_3": {
            "vol_pred_all_folds": vol_audit.get("all_folds_improved"),
            "skip_high_active_folds_all_positive": skip_h.get("active_folds_all_positive"),
            "skip_low_active_folds_all_positive": skip_l.get("active_folds_all_positive"),
        },
        "6_adds_info_beyond_existing_features": {
            "answer": bool(vol_audit.get("n_folds_improved", 0) >= 2),
            "note": "Orthogonal features improve fwd_vol_12 MAE vs baseline features in walk-forward audit.",
        },
        "7_justify_future_shadow": {
            "answer": False,
            "note": "Requires CANDIDATE_FOR_FUTURE_SHADOW_TEST; default conservative unless CI/cost/fold gates clear.",
        },
    }


def main() -> int:
    print("PHASE27 preflight…")
    assert PRODUCTION_FINAL_ACTION == "WAIT"
    assert list(PHASE26_ACCEPTED)

    m5 = load_m5_bars()
    h1 = load_h1_bars()
    decision_times = load_decision_times()
    safety = safety_audit(m5, PROJECT_ROOT)
    preflight = {
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "n_m5": len(m5["times"]),
        "n_decision_times": len(decision_times),
        "holdout_opened": m5["holdout_opened"],
        "safety_all_pass": safety["checks"]["all_pass"],
        "h13c_q": {"low": H13C_Q_LOW, "high": H13C_Q_HIGH},
        "regime_method": REGIME_METHOD,
        "phase26_accepted_n": len(PHASE26_ACCEPTED),
    }
    print(json.dumps(preflight, indent=2))
    if not safety["checks"]["all_pass"]:
        print("SAFETY FAIL", json.dumps(safety["checks"], indent=2))
        return 2

    print("Features/outcomes (Phase 26 machinery, read-only reuse)…")
    feats = compute_orthogonal_features(m5, h1)
    outcomes26 = build_rich_outcomes(feats, len(m5["times"]))
    decision_indices = [m5["index"][t] for t in decision_times if t in m5["index"]]

    print("Independent fwd_vol_12 audit + OOF predictions…")
    vol = build_oof_vol_predictions(m5, feats, outcomes26, decision_indices)
    print("vol folds improved", vol["n_folds_improved"], "all", vol["all_folds_improved"])

    print("Frozen H13_C trades…")
    bundle = load_bundle()
    h13 = generate_h13c_trades(bundle)
    trades = enrich_trades(h13["trades"], vol["pred_vol_by_time"], vol["regime_by_time"])
    trades = join_mfe_mae(trades, m5, outcomes26)
    print("n_h13c_trades", len(trades))

    regime = regime_analysis(trades)
    regime["mfe_mae"] = mfe_mae_by_regime(trades)
    policies = hypothetical_policies(trades)
    stats = statistical_validation(policies, vol, regime)
    verdict = decide_verdict(vol, policies, stats)
    answers = decision_quality_answers(vol, regime, policies, stats)
    # update answer 7 from verdict
    answers["7_justify_future_shadow"]["answer"] = verdict["verdict"] == "CANDIDATE_FOR_FUTURE_SHADOW_TEST"

    summary = build_summary(
        preflight=preflight,
        verdict=verdict,
        vol_audit=vol,
        policies=policies,
        answers=answers,
    )
    # store fold_audit without huge pred maps in summary path files
    vol_report = {
        "fold_audit": vol["fold_audit"],
        "n_folds_improved": vol["n_folds_improved"],
        "all_folds_improved": vol["all_folds_improved"],
        "independent_verify_note": vol["independent_verify_note"],
        "n_oof_predictions": len(vol["pred_vol_by_time"]),
    }
    paths = write_reports(
        summary=summary,
        vol_audit=vol_report,
        regime=regime,
        policies=policies,
        stats=stats,
        safety=safety,
    )
    write_docs(preflight, vol_report, regime, policies, stats, safety, verdict, answers)
    print("VERDICT", verdict["verdict"])
    print("reports", paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
