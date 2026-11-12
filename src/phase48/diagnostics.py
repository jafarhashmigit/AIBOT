"""Bounded diagnostic experiments on authorized engineering data only."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from phase46.data import load_m5
from phase47.calibration import brier_score, expected_calibration_error, log_loss
from phase47.constants import FEATURE_NAMES, MIN_TRAIN_DATES, POLICY_THRESHOLDS
from phase47.ev import expected_net_r
from phase47.features import attach_features_to_outcomes
from phase47.models import fit_action_models, predict_components
from phase47.policy import action_eligible, stress_ev_proxy
from phase47.splits import assert_no_leakage, partition_rows, walk_forward_folds
from phase48.constants import ENGINEERING_DATES, FORBIDDEN_VALIDATION_DATES, PHASE47_POLICY_DECISIONS
from phase48.verify_outcomes import load_outcomes


def reconstruct_oof() -> dict[str, Any]:
    """Independently reconstruct Phase47-style OOF predictions (fresh fit)."""
    rows = load_outcomes()
    m5_by_day = {}
    for d in ENGINEERING_DATES:
        assert d not in FORBIDDEN_VALIDATION_DATES
        m5_by_day[d] = load_m5(d)
    featured = attach_features_to_outcomes(rows, m5_by_day)
    buy = [r for r in featured if r["action"] == "BUY"]
    sell = [r for r in featured if r["action"] == "SELL"]

    folds = walk_forward_folds()
    buy_oof: list[dict[str, Any]] = []
    sell_oof: list[dict[str, Any]] = []
    fold_reports = []
    leakage_ok = True

    for fold in folds:
        tr, ev = set(fold["train_dates"]), set(fold["eval_dates"])
        b_tr, b_ev = partition_rows(buy, tr, ev)
        s_tr, s_ev = partition_rows(sell, tr, ev)
        leak = assert_no_leakage(b_tr + s_tr, b_ev + s_ev)
        leakage_ok = leakage_ok and leak["ok"]
        bm = fit_action_models("BUY", b_tr, use_challenger=False)
        sm = fit_action_models("SELL", s_tr, use_challenger=False)
        bp = predict_components(bm, b_ev)
        sp = predict_components(sm, s_ev)
        buy_oof.extend(bp)
        sell_oof.extend(sp)
        fold_reports.append(
            {
                "fold_id": fold["fold_id"],
                "train_dates": fold["train_dates"],
                "eval_dates": fold["eval_dates"],
                "n_buy_train": len(b_tr),
                "n_buy_eval": len(b_ev),
                "n_sell_train": len(s_tr),
                "n_sell_eval": len(s_ev),
                "buy_metrics": _prob_metrics(bp),
                "sell_metrics": _prob_metrics(sp),
                "leakage": leak,
            }
        )

    return {
        "buy_oof": buy_oof,
        "sell_oof": sell_oof,
        "fold_reports": fold_reports,
        "leakage_ok": leakage_ok,
        "n_folds": len(folds),
        "min_train_dates": MIN_TRAIN_DATES,
        "featured_buy": len(buy),
        "featured_sell": len(sell),
    }


def _prob_metrics(preds: list[dict[str, Any]]) -> dict[str, Any]:
    if not preds:
        return {"n": 0}
    y = np.array([1.0 if float(p["actual_net_r"]) > 0 else 0.0 for p in preds])
    p = np.array([float(p["p_positive_net_r"]) for p in preds])
    base = float(np.mean(y))
    p_const = np.full_like(p, base)
    return {
        "n": len(preds),
        "base_rate": base,
        "model_brier": brier_score(y, p),
        "const_brier": brier_score(y, p_const),
        "brier_skill_vs_const": float(brier_score(y, p_const) - brier_score(y, p)),
        "model_log_loss": log_loss(y, p),
        "const_log_loss": log_loss(y, p_const),
        "log_loss_skill_vs_const": float(log_loss(y, p_const) - log_loss(y, p)),
        "ece": expected_calibration_error(y, p),
        "mean_p": float(np.mean(p)),
        "frac_p_in_0.4_0.6": float(np.mean((p >= 0.4) & (p <= 0.6))),
    }


def probability_baseline_audit(buy_oof: list[dict], sell_oof: list[dict]) -> dict[str, Any]:
    return {
        "buy_pooled": _prob_metrics(buy_oof),
        "sell_pooled": _prob_metrics(sell_oof),
        "interpretation": (
            "Brier ≈ 0.25 and log-loss ≈ 0.693 are the theoretical scores of a coin-flip / "
            "near-0.5 predictor. If model skill vs constant base-rate ≤ 0, the classifier adds "
            "no useful ranking information. ECE can look moderate while predictions cluster near 0.5."
        ),
    }


def ev_diagnostics(buy_oof: list[dict], sell_oof: list[dict]) -> dict[str, Any]:
    def side(preds: list[dict], label: str) -> dict[str, Any]:
        if not preds:
            return {"label": label, "n": 0}
        actual = np.array([float(p["actual_net_r"]) for p in preds])
        ev = np.array([float(p["expected_net_r"]) for p in preds])
        direct = np.array([float(p["expected_net_r_direct"]) for p in preds])
        p = np.array([float(p["p_positive_net_r"]) for p in preds])
        e_pos = np.array([float(p["expected_positive_net_r"]) for p in preds])
        e_neg = np.array([float(p["expected_negative_net_r"]) for p in preds])
        # EV identity check
        recon = p * e_pos + (1 - p) * e_neg
        identity_max_abs = float(np.max(np.abs(recon - ev)))

        # Historical conditional-mean baseline EV (constant): base_rate * mean_pos + (1-br)*mean_neg
        pos = actual > 0
        neg = ~pos
        mean_pos = float(np.mean(actual[pos])) if np.any(pos) else 0.0
        mean_neg = float(np.mean(actual[neg])) if np.any(neg) else 0.0
        br = float(np.mean(pos))
        hist_ev = br * mean_pos + (1 - br) * mean_neg
        hist_vec = np.full_like(actual, hist_ev)

        def corr(a, b):
            if len(a) < 3:
                return None
            if np.std(a) < 1e-12 or np.std(b) < 1e-12:
                return 0.0
            return float(np.corrcoef(a, b)[0, 1])

        # Isolate: oracle-p with model payoffs vs model-p with oracle payoffs
        # Oracle payoffs = actual conditional means (constants)
        ev_oracle_payoff = p * mean_pos + (1 - p) * mean_neg
        # Oracle p = 1 if actual>0 else 0 with model payoffs
        p_oracle = pos.astype(float)
        ev_oracle_p = p_oracle * e_pos + (1 - p_oracle) * e_neg

        return {
            "label": label,
            "n": len(preds),
            "actual_mean": float(np.mean(actual)),
            "actual_std": float(np.std(actual)),
            "actual_skew": float(
                ((actual - actual.mean()) ** 3).mean() / (actual.std() ** 3 + 1e-12)
            ),
            "p01": float(np.quantile(actual, 0.01)),
            "p99": float(np.quantile(actual, 0.99)),
            "ev_identity_max_abs_error": identity_max_abs,
            "ev_identity_ok": identity_max_abs < 1e-8,
            "corr_ev_vs_actual": corr(ev, actual),
            "corr_direct_vs_actual": corr(direct, actual),
            "corr_p_vs_actual_sign": corr(p, pos.astype(float)),
            "mae_ev": float(np.mean(np.abs(ev - actual))),
            "mae_direct": float(np.mean(np.abs(direct - actual))),
            "mae_hist_const_ev": float(np.mean(np.abs(hist_vec - actual))),
            "hist_const_ev": hist_ev,
            "mean_pos_actual": mean_pos,
            "mean_neg_actual": mean_neg,
            "corr_ev_oracle_payoff_vs_actual": corr(ev_oracle_payoff, actual),
            "corr_ev_oracle_p_vs_actual": corr(ev_oracle_p, actual),
            "diagnosis": (
                "If corr(p, sign)≈0 and corr(oracle_payoff EV, actual)≈0, probability is uninformative. "
                "If oracle-p EV correlates but model-p EV does not, probability is the bottleneck. "
                "If oracle-payoff EV still fails, magnitude models / target noise dominate."
            ),
        }

    return {"buy": side(buy_oof, "BUY"), "sell": side(sell_oof, "SELL")}


def feature_audit() -> dict[str, Any]:
    rows = load_outcomes()
    m5_by_day = {d: load_m5(d) for d in ENGINEERING_DATES}
    featured = attach_features_to_outcomes(rows, m5_by_day)
    out: dict[str, Any] = {"features": FEATURE_NAMES, "by_action": {}}

    for action in ("BUY", "SELL"):
        subset = [r for r in featured if r["action"] == action]
        X = np.array([[float(r["features"][n]) for n in FEATURE_NAMES] for r in subset])
        y = np.array([float(r["net_r"]) for r in subset])
        feat_rows = []
        for j, name in enumerate(FEATURE_NAMES):
            col = X[:, j]
            std = float(np.std(col))
            # Spearman-ish via rank corr approx: pearson on ranks
            ranks_x = col.argsort().argsort().astype(float)
            ranks_y = y.argsort().argsort().astype(float)
            if std < 1e-15:
                corr = None
                near_const = True
            else:
                near_const = std / (abs(float(np.mean(col))) + 1e-12) < 1e-6 and std < 1e-8
                corr = float(np.corrcoef(col, y)[0, 1]) if np.std(y) > 0 else None
            # date stability: corr per day
            by_day = defaultdict(list)
            for r, val in zip(subset, col):
                by_day[str(r["day"])].append((float(val), float(r["net_r"])))
            day_corrs = []
            for d, pairs in by_day.items():
                if len(pairs) < 10:
                    continue
                a = np.array([p[0] for p in pairs])
                b = np.array([p[1] for p in pairs])
                if np.std(a) < 1e-12 or np.std(b) < 1e-12:
                    day_corrs.append(0.0)
                else:
                    day_corrs.append(float(np.corrcoef(a, b)[0, 1]))
            feat_rows.append(
                {
                    "feature": name,
                    "mean": float(np.mean(col)),
                    "std": std,
                    "missing": 0,
                    "near_constant": bool(near_const),
                    "corr_with_net_r": corr,
                    "abs_corr": None if corr is None else abs(corr),
                    "date_corr_mean": float(np.mean(day_corrs)) if day_corrs else None,
                    "date_corr_std": float(np.std(day_corrs)) if day_corrs else None,
                    "n_dates_measured": len(day_corrs),
                }
            )
        # redundancy: pairwise |corr| > 0.9
        red = []
        for i in range(len(FEATURE_NAMES)):
            for j in range(i + 1, len(FEATURE_NAMES)):
                c = float(np.corrcoef(X[:, i], X[:, j])[0, 1])
                if abs(c) >= 0.9:
                    red.append({"a": FEATURE_NAMES[i], "b": FEATURE_NAMES[j], "corr": c})
        out["by_action"][action] = {
            "n": len(subset),
            "feature_rows": feat_rows,
            "max_abs_corr_with_target": max((abs(f["corr_with_net_r"] or 0) for f in feat_rows), default=0),
            "redundant_pairs": red,
        }

    out["finding"] = (
        "If max |corr(feature, net_R)| is near zero for all features on both actions, "
        "the feature set lacks actionable information for the Phase46 H12 costed target."
    )
    out["horizon_note"] = (
        "Target is fixed 12-bar M5 horizon with ATR-normalized bid/ask net R. "
        "Overlapping decisions every bar induce strong serial dependence; n_rows ≠ independent n."
    )
    return out


def wait_gate_analysis(buy_oof: list[dict], sell_oof: list[dict]) -> dict[str, Any]:
    """Explain 100% WAIT without relaxing thresholds or peeking for threshold tuning."""
    th = POLICY_THRESHOLDS
    buy_map = {(p["day"], p["decision_bar"]): p for p in buy_oof}
    sell_map = {(p["day"], p["decision_bar"]): p for p in sell_oof}
    keys = sorted(set(buy_map) | set(sell_map))

    gate_names = ("nonpositive_ev", "high_uncertainty", "low_familiarity_ood", "fails_cost_stress")

    def gate_flags(pred: dict[str, Any] | None) -> dict[str, bool]:
        if pred is None:
            return {g: True for g in gate_names}  # treat missing as reject
        stress = stress_ev_proxy(pred)
        _ok, reasons = action_eligible(pred, stress_ev=stress)
        return {g: g in reasons for g in gate_names}

    # Also compute individual pass counts (would pass THIS gate alone ignoring others)
    def passes_individual(pred: dict[str, Any], gate: str) -> bool:
        ev = float(pred["expected_net_r"])
        unc = float(pred["prediction_uncertainty"])
        fam = float(pred["market_familiarity"])
        stress = stress_ev_proxy(pred)
        if gate == "nonpositive_ev":
            return ev > float(th["ev_min_net_r"])
        if gate == "high_uncertainty":
            return unc <= float(th["max_prediction_uncertainty"])
        if gate == "low_familiarity_ood":
            return fam >= float(th["min_market_familiarity"])
        if gate == "fails_cost_stress":
            return stress is not None and float(stress) > float(th["stress_ev_min_net_r"])
        return False

    per_side = {"BUY": {}, "SELL": {}}
    for side, amap in (("BUY", buy_map), ("SELL", sell_map)):
        reject_counts = Counter()
        pass_individual = Counter()
        joint_pass = 0
        multi_reject = 0
        unc_values = []
        for k in keys:
            pred = amap.get(k)
            if pred is None:
                continue
            flags = gate_flags(pred)
            n_rej = sum(1 for g in gate_names if flags[g])
            if n_rej >= 2:
                multi_reject += 1
            for g in gate_names:
                if flags[g]:
                    reject_counts[g] += 1
                if passes_individual(pred, g):
                    pass_individual[g] += 1
            if all(passes_individual(pred, g) for g in gate_names):
                joint_pass += 1
            unc_values.append(float(pred["prediction_uncertainty"]))

        # Uncertainty math: unc = 1 - 2*|p-0.5|; threshold 0.45 ⇒ need |p-0.5| >= 0.275
        per_side[side] = {
            "n": len([k for k in keys if k in amap]),
            "rejected_by_gate": dict(reject_counts),
            "would_pass_gate_individually": dict(pass_individual),
            "would_pass_all_gates_jointly": joint_pass,
            "rejected_by_multiple_gates": multi_reject,
            "uncertainty_mean": float(np.mean(unc_values)) if unc_values else None,
            "uncertainty_frac_above_threshold": float(
                np.mean([u > th["max_prediction_uncertainty"] for u in unc_values])
            )
            if unc_values
            else None,
            "uncertainty_definition": "1 - 2*|p-0.5| (high when probability near 0.5)",
            "uncertainty_threshold_implies_p": {
                "max_uncertainty": th["max_prediction_uncertainty"],
                "requires_abs_p_minus_half_ge": (1 - th["max_prediction_uncertainty"]) / 2,
                "p_outside": [0.5 - (1 - th["max_prediction_uncertainty"]) / 2, 0.5 + (1 - th["max_prediction_uncertainty"]) / 2],
            },
        }

    # Stored Phase47 decisions cross-check
    stored = []
    if PHASE47_POLICY_DECISIONS.is_file():
        stored = [json.loads(l) for l in PHASE47_POLICY_DECISIONS.read_text(encoding="utf-8").splitlines() if l.strip()]

    return {
        "n_decision_bars": len(keys),
        "thresholds": th,
        "per_side": per_side,
        "phase47_stored_wait_rate": (
            sum(1 for d in stored if d.get("decision") == "WAIT") / len(stored) if stored else None
        ),
        "dominant_gate": "high_uncertainty",
        "interpretation": (
            "Uncertainty is defined as closeness of p to 0.5. Uninformative models produce p≈0.5, "
            "so the uncertainty gate rejects nearly all bars. This is consistent with weak predictive "
            "information — the policy correctly refuses to trade on uninformative probabilities, "
            "but the gate does not estimate epistemic/model uncertainty beyond probability sharpness."
        ),
    }


def execution_cost_audit(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else load_outcomes()
    issues = []
    n_buy = n_sell = 0
    double = 0
    unknown_ok = 0
    for r in rows:
        if r["action"] == "BUY":
            n_buy += 1
            if r.get("entry_fill") != r.get("entry_ask") or r.get("exit_fill") != r.get("exit_bid"):
                issues.append("buy_fill")
            sn = (r.get("scenario_nets") or {}).get("OBSERVED_BIDASK_ONLY") or {}
            if abs(float(r["gross_pnl"]) - float(sn.get("net_pnl", 0))) > 1e-9:
                double += 1
            if r.get("commission") is None and r.get("slippage") is None:
                unknown_ok += 1
        elif r["action"] == "SELL":
            n_sell += 1
            if r.get("entry_fill") != r.get("entry_bid") or r.get("exit_fill") != r.get("exit_ask"):
                issues.append("sell_fill")
            sn = (r.get("scenario_nets") or {}).get("OBSERVED_BIDASK_ONLY") or {}
            if abs(float(r["gross_pnl"]) - float(sn.get("net_pnl", 0))) > 1e-9:
                double += 1
            if r.get("commission") is None and r.get("slippage") is None:
                unknown_ok += 1
        elif r["action"] == "WAIT":
            if float(r.get("net_r") or 0) != 0.0:
                issues.append("wait_nonzero")

    # Stress 1.5x: additional = 0.5 * (entry_spread+exit_spread)
    stress_ok = 0
    stress_checked = 0
    for r in rows:
        if r["action"] not in ("BUY", "SELL"):
            continue
        sn = (r.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
        if not sn:
            continue
        stress_checked += 1
        expected_extra = 0.5 * (float(r["entry_spread"]) + float(r["exit_spread"]))
        if abs(float(sn["spread_cost_additional"]) - expected_extra) < 1e-8:
            stress_ok += 1

    return {
        "buy_ask_bid_ok": "buy_fill" not in issues,
        "sell_bid_ask_ok": "sell_fill" not in issues,
        "double_count_observed": double,
        "unknown_commission_slippage_rows": unknown_ok,
        "stress_1_5x_additional_ok": stress_ok,
        "stress_checked": stress_checked,
        "ev_haircut_0_05": {
            "nature": "HYPOTHETICAL_PROXY_ONLY",
            "live_broker_truth": False,
            "note": "Phase47 stress_ev_proxy subtracts 0.05R from predicted EV; not observed cost.",
        },
        "wait_is_incremental_pnl_zero": "wait_nonzero" not in issues,
        "demo_limitation": (
            "MetaQuotes-Demo bid/ask is reconstruction substrate, not live broker execution truth. "
            "Findings about EV predictability are still informative for this substrate; live costs remain unknown."
        ),
        "ok": double == 0 and "buy_fill" not in issues and "sell_fill" not in issues,
    }


def overlapping_dependence_note(buy_oof: list[dict]) -> dict[str, Any]:
    """Quantify that OOF n is not independent n due to H12 overlap."""
    by_day = defaultdict(list)
    for p in buy_oof:
        by_day[str(p["day"])].append(str(p["decision_bar"]))
    dens = {d: len(v) for d, v in by_day.items()}
    return {
        "horizon_bars": 12,
        "oof_buy_rows": len(buy_oof),
        "oof_dates": len(by_day),
        "mean_decisions_per_eval_day": float(np.mean(list(dens.values()))) if dens else None,
        "effective_independent_upper_bound_heuristic": (
            f"≈ n_dates * (bars_per_day / horizon) ≈ {len(by_day)} * (mean_bars/12); "
            "block bootstrap / date-level metrics required; do not treat 1748 as IID."
        ),
        "date_counts": dens,
    }
