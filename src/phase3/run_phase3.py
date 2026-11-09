"""Phase 3 orchestrator: audit, nested OOS decisions, evaluation.

Does not open the holdout, does not write over Phase 1/2 files, does not send orders.
Pandas is not imported: Windows Application Control blocks pandas DLLs in this session.
numpy and sklearn from the approved venv are used instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from phase3.baselines import (
    apply_c,
    apply_d,
    baseline_a_wait,
    baseline_b_direction,
    baseline_e1,
    fit_c_threshold,
    fit_d_threshold,
)
from phase3.constants import (
    ACTIONS_PATH,
    CONS_MIN_GAP,
    CONS_TAU_CANDIDATES,
    EV_TAU_CANDIDATES,
    FEATURE_VERSION,
    FROZEN_POLICY,
    FROZEN_POLICY_ID,
    JOURNAL_PATH,
    META_RF_REASON,
    META_RF_USED,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
    UNCERTAINTY_K,
)
from phase3.dataset import load_oos, to_wide
from phase3.decision_feature_audit import run_audit
from phase3.decision_journal import build_journal, write_journal
from phase3.decision_policy import decide_batch, select_threshold
from phase3.evaluate import (
    compare_policies,
    phase3_economic_gate,
    stress_spread,
    stress_threshold,
)
from phase3.expected_value import attach_conservative, class_conditional_mean_r, inner_mae
from phase3.meta_model import apply_meta, fit_meta
from phase3.nplib import (
    assert_holdout_untouched,
    col,
    fmt_time,
    holdout_status,
    install_guards,
    save,
    wrap,
    write_csv_dicts,
    GUARD,
)
from phase3.walk_forward import fold_public, nested_folds


def _public_selection(sel: dict) -> dict:
    return dict(sel)


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    long_rows = load_oos()
    wide = to_wide(long_rows)
    audit = run_audit(long_rows, wide)
    save(REPORTS_DIR / "feature_audit.json",
         wrap("phase3_feature_audit", "confirmatory", {"recipe": RECIPE_ID}, audit, SEED))
    if not audit["passed"]:
        print("FEATURE AUDIT FAILED", [c["name"] for c in audit["checks"] if not c["passed"]])
        return 1

    folds = nested_folds(wide)
    fold_pub = [fold_public(f) for f in folds]
    save(REPORTS_DIR / "walk_forward_design.json",
         wrap("phase3_walk_forward_design", "confirmatory",
              {"recipe": RECIPE_ID, "frozen_policy": FROZEN_POLICY},
              {"folds": fold_pub, "n_oos_timestamps": int(len(wide)),
               "limitation": "Only two outer folds. WF1 has no earlier OOS to calibrate on."},
              SEED))
    for row in fold_pub:
        print(row["nested_id"], "inner_ts", row["inner_timestamps"], "outer_ts", row["outer_timestamps"],
              "inner_end", row["inner_end"], "outer", row["outer_first"], "->", row["outer_last"])

    outer_parts = []
    journal_parts = []
    fold_fits = []
    policy_names = [
        "A_WAIT", "B_DIRECTION", "E1_PHASE2", "C_EV_THRESHOLD",
        "D_PROB_ADVANTAGE", "EV_ENGINE", FROZEN_POLICY_ID, "META_RIDGE",
    ]
    outer_actions = {name: [] for name in policy_names}

    for fold in folds:
        inner = fold["inner"]
        outer = fold["outer"]
        mapping = class_conditional_mean_r(inner)
        mae = inner_mae(inner, mapping)
        inner_c = attach_conservative(inner, mapping, mae, UNCERTAINTY_K)
        outer_c = attach_conservative(outer, mapping, mae, UNCERTAINTY_K)

        c_fit = fit_c_threshold(inner_c)
        d_fit = fit_d_threshold(inner_c)
        ev_fit = select_threshold(
            inner_c, col(inner_c, "ev_BUY"), col(inner_c, "ev_SELL"), EV_TAU_CANDIDATES)
        cons_fit = select_threshold(
            inner_c, col(inner_c, "cons_ev_BUY"), col(inner_c, "cons_ev_SELL"),
            CONS_TAU_CANDIDATES, min_gap=CONS_MIN_GAP)
        meta_models = fit_meta(inner_c, fold["nested_id"])

        a_wait = baseline_a_wait(len(outer_c))
        b_dir = baseline_b_direction(outer_c)
        e1 = baseline_e1(outer_c)
        c_act = apply_c(outer_c, c_fit)
        d_act = apply_d(outer_c, d_fit)
        if ev_fit["fallback_wait"]:
            ev_act = baseline_a_wait(len(outer_c))
        else:
            ev_act = decide_batch(col(outer_c, "ev_BUY"), col(outer_c, "ev_SELL"), ev_fit["tau"], 0.0)
        if cons_fit["fallback_wait"]:
            cons_act = baseline_a_wait(len(outer_c))
        else:
            cons_act = decide_batch(col(outer_c, "cons_ev_BUY"), col(outer_c, "cons_ev_SELL"),
                                    cons_fit["tau"], CONS_MIN_GAP)
        meta_act, meta_extra = apply_meta(outer_c, meta_models)
        for i, rec in enumerate(outer_c):
            rec["nested_id"] = fold["nested_id"]
            rec["meta_r_BUY"] = float(meta_extra["meta_r_BUY"][i])
            rec["meta_r_SELL"] = float(meta_extra["meta_r_SELL"][i])
            rec["meta_ppos_BUY"] = float(meta_extra["meta_ppos_BUY"][i])
            rec["meta_ppos_SELL"] = float(meta_extra["meta_ppos_SELL"][i])
            rec["action_A_WAIT"] = str(a_wait[i])
            rec["action_B_DIRECTION"] = str(b_dir[i])
            rec["action_E1_PHASE2"] = str(e1[i])
            rec["action_C_EV_THRESHOLD"] = str(c_act[i])
            rec["action_D_PROB_ADVANTAGE"] = str(d_act[i])
            rec["action_EV_ENGINE"] = str(ev_act[i])
            rec["action_P3_CONSERVATIVE_EV"] = str(cons_act[i])
            rec["action_META_RIDGE"] = str(meta_act[i])

        fold_fits.append({
            "nested_id": fold["nested_id"],
            "inner_end": fmt_time(fold["inner_end"]),
            "class_conditional_mean_r": mapping,
            "inner_ev_mae": mae,
            "uncertainty_k": UNCERTAINTY_K,
            "C_EV_THRESHOLD": _public_selection(c_fit),
            "D_PROB_ADVANTAGE": _public_selection(d_fit),
            "EV_ENGINE": _public_selection(ev_fit),
            "P3_CONSERVATIVE_EV": _public_selection(cons_fit),
            "META_RIDGE": _public_selection(meta_models["selection"]),
            "meta_ok": meta_models.get("ok"),
            "meta_notes": meta_models.get("notes"),
            "meta_paths": {k: meta_models[k] for k in meta_models if k.endswith("_path")},
        })
        journal_parts.append(build_journal(
            outer_c, cons_act,
            nested_id=fold["nested_id"],
            inner_end=fold["inner_end"],
            tau=cons_fit["tau"],
            min_gap=CONS_MIN_GAP,
            k=UNCERTAINTY_K,
            mapping_mae=mae,
        ))
        outer_parts.extend(outer_c)
        outer_actions["A_WAIT"].append(a_wait)
        outer_actions["B_DIRECTION"].append(b_dir)
        outer_actions["E1_PHASE2"].append(e1)
        outer_actions["C_EV_THRESHOLD"].append(c_act)
        outer_actions["D_PROB_ADVANTAGE"].append(d_act)
        outer_actions["EV_ENGINE"].append(ev_act)
        outer_actions[FROZEN_POLICY_ID].append(cons_act)
        outer_actions["META_RIDGE"].append(meta_act)

    policy_actions = {name: np.concatenate(parts) for name, parts in outer_actions.items()}
    comparison = compare_policies(outer_parts, policy_actions)

    frozen_act = policy_actions[FROZEN_POLICY_ID]
    spread_stress = stress_spread(outer_parts, frozen_act)
    pert = {}
    offset = 0
    for fold, fit in zip(folds, fold_fits):
        n = len(fold["outer"])
        part = outer_parts[offset:offset + n]
        tau = fit["P3_CONSERVATIVE_EV"]["tau"]
        pert[fold["nested_id"]] = stress_threshold(
            part, col(part, "cons_ev_BUY"), col(part, "cons_ev_SELL"), tau, CONS_MIN_GAP)
        offset += n

    flat_pert = {k: v for nest in pert.values() if isinstance(nest, dict)
                 for k, v in nest.items() if isinstance(v, dict)}
    stress = {"spread": spread_stress, "threshold": pert}
    frozen_pooled = comparison[FROZEN_POLICY_ID]["pooled"]
    frozen_by_fold = comparison[FROZEN_POLICY_ID]["by_outer_fold"]
    gate = phase3_economic_gate(frozen_pooled, frozen_by_fold,
                                {"spread": spread_stress, "threshold": flat_pert},
                                audit["passed"])

    journal = write_journal(journal_parts, JOURNAL_PATH)
    action_rows = []
    for rec in outer_parts:
        action_rows.append({
            "decision_time": fmt_time(rec["decision_time"]),
            "nested_id": rec["nested_id"],
            "fold_id": rec["fold_id"],
            "action_A_WAIT": rec["action_A_WAIT"],
            "action_B_DIRECTION": rec["action_B_DIRECTION"],
            "action_E1_PHASE2": rec["action_E1_PHASE2"],
            "action_C_EV_THRESHOLD": rec["action_C_EV_THRESHOLD"],
            "action_D_PROB_ADVANTAGE": rec["action_D_PROB_ADVANTAGE"],
            "action_EV_ENGINE": rec["action_EV_ENGINE"],
            "action_P3_CONSERVATIVE_EV": rec["action_P3_CONSERVATIVE_EV"],
            "action_META_RIDGE": rec["action_META_RIDGE"],
        })
    write_csv_dicts(ACTIONS_PATH, action_rows)

    conclusion = "CREDIBLE EDGE ESTABLISHED" if gate["passed"] else "NO CREDIBLE ECONOMIC EDGE"
    results = {
        "n_outer_timestamps": int(len(outer_parts)),
        "n_journal_rows": int(len(journal)),
        "folds": fold_pub,
        "fold_fits": fold_fits,
        "frozen_policy": FROZEN_POLICY,
        "meta_rf_used": META_RF_USED,
        "meta_rf_reason": META_RF_REASON,
        "comparison": comparison,
        "stress": stress,
        "phase3_economic_gate": gate,
        "conclusion": conclusion,
        "pandas_unavailable": (
            "pandas DLLs are blocked by Windows Application Control in this session. "
            "Phase 3 used numpy + sklearn from the approved venv. No packages were installed."
        ),
        "permutation_a_phase1": {
            "status": "not_run",
            "note": "The Phase 1 200-retrain label-block permutation remains incomplete. "
                    "This phase does not mark it passed and did not run a substitute as if it were A.",
        },
        "journal_path": str(JOURNAL_PATH),
        "actions_path": str(ACTIONS_PATH),
        "feature_version": FEATURE_VERSION,
        "finding_class": "exploratory",
        "production_ready": False,
        "live_ready": False,
    }
    save(REPORTS_DIR / "decision_results.json",
         wrap("phase3_decision_results", "exploratory",
              {"recipe": RECIPE_ID, "frozen_policy": FROZEN_POLICY}, results, SEED))

    registry = []
    for fit in fold_fits:
        registry.append({
            "model_id": f"ev_map_{fit['nested_id']}",
            "model_type": "class_conditional_ev_plus_mae_penalty",
            "model_version": RECIPE_ID,
            "role": "decision_layer",
            "nested_id": fit["nested_id"],
            "training_period_end": fit["inner_end"],
            "parameters": {
                "class_conditional_mean_r": fit["class_conditional_mean_r"],
                "inner_ev_mae": fit["inner_ev_mae"],
                "k": UNCERTAINTY_K,
                "tau": fit["P3_CONSERVATIVE_EV"]["tau"],
                "min_gap": CONS_MIN_GAP,
                "selection": fit["P3_CONSERVATIVE_EV"],
            },
            "random_seed": SEED,
            "python": "3.12.10",
            "artifact_path": fit["meta_paths"],
            "evaluation_report_path": str(REPORTS_DIR / "decision_results.json"),
            "journal_path": str(JOURNAL_PATH),
            "status": "experimental",
            "production_ready": False,
            "live_ready": False,
            "known_limitations": [
                "Only two outer folds.",
                "Inner mapping and threshold share the same inner window.",
                "Phase 1 permutation A remains not_run.",
            ],
        })
    save(REPORTS_DIR / "model_registry.json",
         wrap("phase3_model_registry", "exploratory", {"recipe": RECIPE_ID},
              {"n_models": len(registry), "models": registry}, SEED))

    assert_holdout_untouched()
    print("holdout attempts", GUARD["test_open_attempts"], holdout_status())
    print("journal", JOURNAL_PATH, "rows", len(journal))
    fr = frozen_pooled
    print("FROZEN", FROZEN_POLICY_ID, "trades", fr.get("n_trades"),
          "mean_trade_r", fr.get("mean_r_per_trade"),
          "mean_decision_r", fr.get("mean_r_per_decision"),
          "pf", fr.get("profit_factor"))
    print("WAIT", comparison["A_WAIT"]["pooled"].get("n_trades"),
          "E1", comparison["E1_PHASE2"]["pooled"].get("n_trades"),
          comparison["E1_PHASE2"]["pooled"].get("mean_r_per_trade"))
    print("GATE", gate["passed"], "CONCLUSION", conclusion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
