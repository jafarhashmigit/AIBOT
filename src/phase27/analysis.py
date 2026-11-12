"""H13_C outcome analysis by predicted-volatility regime + hypothetical policies."""

from __future__ import annotations

from typing import Any

import numpy as np

from phase14.constants import COST_MULTS_CONFIRMATORY, FOLDS
from phase14.scoring import cost_robustness, score_trades
from phase27.constants import MIN_FOLD_POLICY_N, MIN_SUBGROUP_N


def _attach_vol(trades: list[dict], pred_vol: dict[str, float], regimes: dict[str, str]) -> list[dict]:
    out = []
    for t in trades:
        row = dict(t)
        dt = t["decision_time"]
        row["pred_fwd_vol_12"] = pred_vol.get(dt)
        row["pred_vol_regime"] = regimes.get(dt, "unknown")
        out.append(row)
    return out


def _block(trades: list[dict]) -> dict:
    return score_trades(trades, label="subset")["pooled"]


def regime_analysis(trades: list[dict]) -> dict[str, Any]:
    by_reg = {"low": [], "medium": [], "high": [], "unknown": []}
    by_side_reg: dict[str, dict[str, list]] = {
        side: {"low": [], "medium": [], "high": [], "unknown": []} for side in ("BUY", "SELL")
    }
    for t in trades:
        r = t.get("pred_vol_regime") or "unknown"
        by_reg.setdefault(r, []).append(t)
        by_side_reg[t["side"]].setdefault(r, []).append(t)

    def pack(rows: list[dict]) -> dict:
        sc = _block(rows)
        return {
            "n": sc["n"],
            "mean_r": sc["mean_r"],
            "net_r": sc["net_r"],
            "profit_factor": sc["profit_factor"],
            "win_rate": sc["win_rate"],
            "max_drawdown_usd": sc["max_drawdown_usd"],
            "bootstrap": sc["bootstrap"],
            "sufficient_n": sc["n"] >= MIN_SUBGROUP_N,
        }

    out = {
        "pooled_by_regime": {k: pack(v) for k, v in by_reg.items()},
        "by_side_regime": {
            side: {k: pack(v) for k, v in regs.items()} for side, regs in by_side_reg.items()
        },
        "fold_by_regime": {},
    }
    for fid in FOLDS:
        fold_trades = [t for t in trades if t["fold_id"] == fid]
        out["fold_by_regime"][fid] = {
            reg: pack([t for t in fold_trades if t.get("pred_vol_regime") == reg])
            for reg in ("low", "medium", "high")
        }

    # Continuous association
    xs, ys = [], []
    for t in trades:
        pv = t.get("pred_fwd_vol_12")
        if pv is None or not np.isfinite(pv):
            continue
        xs.append(float(pv))
        ys.append(float(t["net_r"]))
    if len(xs) >= 30 and float(np.std(xs)) > 0 and float(np.std(ys)) > 0:
        corr = float(np.corrcoef(xs, ys)[0, 1])
    else:
        corr = float("nan")
    out["continuous"] = {
        "n": len(xs),
        "corr_pred_vol_vs_net_r": corr,
        "note": "Decision-time predicted vol vs realized net R of frozen H13_C trades.",
    }
    return out


def hypothetical_policies(trades: list[dict]) -> dict[str, Any]:
    """Predeclared filters — no threshold search."""
    baseline = trades
    skip_high = [t for t in trades if t.get("pred_vol_regime") != "high"]
    skip_low = [t for t in trades if t.get("pred_vol_regime") != "low"]
    high_only = [t for t in trades if t.get("pred_vol_regime") == "high"]
    medium_only = [t for t in trades if t.get("pred_vol_regime") == "medium"]
    low_only = [t for t in trades if t.get("pred_vol_regime") == "low"]

    def score_policy(name: str, rows: list[dict]) -> dict:
        sc = score_trades(rows, label=name)
        cost = cost_robustness(rows, COST_MULTS_CONFIRMATORY)
        fold_means = {
            fid: sc["folds"][fid]["mean_r"]
            for fid in FOLDS
            if sc["folds"][fid]["n"] >= MIN_FOLD_POLICY_N
        }
        active = [m for m in fold_means.values() if m == m]
        return {
            "n": sc["pooled"]["n"],
            "mean_r": sc["pooled"]["mean_r"],
            "net_r": sc["pooled"]["net_r"],
            "profit_factor": sc["pooled"]["profit_factor"],
            "win_rate": sc["pooled"]["win_rate"],
            "max_drawdown_usd": sc["pooled"]["max_drawdown_usd"],
            "bootstrap": sc["pooled"]["bootstrap"],
            "folds": {fid: {"n": sc["folds"][fid]["n"], "mean_r": sc["folds"][fid]["mean_r"]} for fid in FOLDS},
            "active_folds_all_positive": bool(active) and all(m > 0 for m in active),
            "cost_1_5x_mean_r": (cost.get("1.5x") or {}).get("mean_r"),
            "cost_1_5x_positive": bool((cost.get("1.5x") or {}).get("mean_r_positive")),
        }

    policies = {
        "baseline_h13c": score_policy("baseline_h13c", baseline),
        "skip_high_pred_vol": score_policy("skip_high_pred_vol", skip_high),
        "skip_low_pred_vol": score_policy("skip_low_pred_vol", skip_low),
        "high_only": score_policy("high_only", high_only),
        "medium_only": score_policy("medium_only", medium_only),
        "low_only": score_policy("low_only", low_only),
    }
    base_mean = policies["baseline_h13c"]["mean_r"]
    for name, p in policies.items():
        if name == "baseline_h13c":
            p["delta_mean_r_vs_baseline"] = 0.0
        else:
            p["delta_mean_r_vs_baseline"] = (
                p["mean_r"] - base_mean
                if p["mean_r"] == p["mean_r"] and base_mean == base_mean
                else float("nan")
            )
    return {
        "policies": policies,
        "predeclared": True,
        "note": "Filters use predicted-vol tertile regimes only; H13_C cuts unchanged.",
    }


def statistical_validation(policies: dict, vol_audit: dict, regime: dict) -> dict[str, Any]:
    """Document fold stability, sample limits, Bonferroni context."""
    base = policies["policies"]["baseline_h13c"]
    skip_h = policies["policies"]["skip_high_pred_vol"]
    skip_l = policies["policies"]["skip_low_pred_vol"]
    cont = regime.get("continuous") or {}

    findings = []
    # Hypothesis checks (descriptive; Bonferroni noted)
    def better(a, b):
        return a == a and b == b and a > b

    findings.append({
        "id": "skip_high_vs_baseline_mean_r",
        "pass": better(skip_h["mean_r"], base["mean_r"]) and skip_h["n"] >= MIN_SUBGROUP_N,
        "detail": {
            "skip_high_mean_r": skip_h["mean_r"],
            "baseline_mean_r": base["mean_r"],
            "n": skip_h["n"],
        },
    })
    findings.append({
        "id": "skip_low_vs_baseline_mean_r",
        "pass": better(skip_l["mean_r"], base["mean_r"]) and skip_l["n"] >= MIN_SUBGROUP_N,
        "detail": {
            "skip_low_mean_r": skip_l["mean_r"],
            "baseline_mean_r": base["mean_r"],
            "n": skip_l["n"],
        },
    })
    buy = regime["by_side_regime"]["BUY"]
    sell = regime["by_side_regime"]["SELL"]
    findings.append({
        "id": "buy_high_vs_buy_low_mean_r",
        "pass": (
            buy["high"]["sufficient_n"]
            and buy["low"]["sufficient_n"]
            and better(buy["high"]["mean_r"], buy["low"]["mean_r"])
        ),
        "detail": {"high": buy["high"]["mean_r"], "low": buy["low"]["mean_r"], "n_high": buy["high"]["n"], "n_low": buy["low"]["n"]},
    })
    findings.append({
        "id": "sell_high_vs_sell_low_mean_r",
        "pass": (
            sell["high"]["sufficient_n"]
            and sell["low"]["sufficient_n"]
            and better(sell["high"]["mean_r"], sell["low"]["mean_r"])
        ),
        "detail": {"high": sell["high"]["mean_r"], "low": sell["low"]["mean_r"], "n_high": sell["high"]["n"], "n_low": sell["low"]["n"]},
    })
    corr = cont.get("corr_pred_vol_vs_net_r")
    findings.append({
        "id": "pred_vol_corr_net_r",
        "pass": corr == corr and abs(corr) >= 0.05 and cont.get("n", 0) >= MIN_SUBGROUP_N,
        "detail": cont,
    })
    findings.append({
        "id": "fwd_vol_mae_improves_all_folds",
        "pass": bool(vol_audit.get("all_folds_improved")),
        "detail": {"n_folds_improved": vol_audit.get("n_folds_improved")},
    })

    n_pass = sum(1 for f in findings if f["pass"])
    contradictory = []
    pooled_skip_high_better = (
        skip_h["mean_r"] == skip_h["mean_r"]
        and base["mean_r"] == base["mean_r"]
        and skip_h["mean_r"] > base["mean_r"]
    )
    for fid in FOLDS:
        b = base["folds"][fid]["mean_r"]
        s = skip_h["folds"][fid]["mean_r"]
        if (
            base["folds"][fid]["n"] >= MIN_FOLD_POLICY_N
            and skip_h["folds"][fid]["n"] >= MIN_FOLD_POLICY_N
            and b == b
            and s == s
            and pooled_skip_high_better
            and s < b
        ):
            contradictory.append(
                {"fold": fid, "issue": "skip_high_worse_on_fold_while_pooled_better"}
            )

    return {
        "bonferroni_alpha_per_test": 0.05 / 6,
        "primary_findings": findings,
        "n_primary_passed": n_pass,
        "contradictory_folds": contradictory,
        "limitations": [
            "H13_C trade count is modest (~226); regime subgroups are smaller.",
            "Predicted-vol tertiles are fold-local; regimes are not globally comparable levels.",
            "Multiple policies inflate false-positive risk; Bonferroni context applies to 6 primary tests.",
            "Volatility prediction improvement does not imply expectancy improvement.",
            "No MFE/MAE on H13_C path beyond existing outcome fields unless joined separately.",
        ],
    }


def decide_verdict(vol_audit: dict, policies: dict, stats: dict) -> dict[str, Any]:
    from phase27.constants import (
        CHAMPION_STATUS,
        H13C_STATUS,
        PHASE25_VERDICT,
        PHASE26_VERDICT,
        PRODUCTION_FINAL_ACTION,
        VALID_VERDICTS,
    )

    vol_ok = bool(vol_audit.get("all_folds_improved")) or int(vol_audit.get("n_folds_improved") or 0) >= 2
    base = policies["policies"]["baseline_h13c"]
    skip_h = policies["policies"]["skip_high_pred_vol"]
    skip_l = policies["policies"]["skip_low_pred_vol"]

    decision_gain = False
    # Require: policy mean_r improves vs baseline, cost 1.5x still positive or better, and >=2 folds agree on sign of delta
    for pol in (skip_h, skip_l):
        if pol["n"] < MIN_SUBGROUP_N or not (pol["mean_r"] == pol["mean_r"]):
            continue
        if pol["mean_r"] <= base["mean_r"]:
            continue
        fold_agree = 0
        for fid in FOLDS:
            if pol["folds"][fid]["n"] < MIN_FOLD_POLICY_N or base["folds"][fid]["n"] < MIN_FOLD_POLICY_N:
                continue
            if pol["folds"][fid]["mean_r"] > base["folds"][fid]["mean_r"]:
                fold_agree += 1
        if fold_agree >= 2:
            decision_gain = True
            break

    primary_decision_passes = sum(
        1
        for f in stats["primary_findings"]
        if f["pass"] and f["id"] != "fwd_vol_mae_improves_all_folds"
    )

    if decision_gain and primary_decision_passes >= 2 and vol_ok:
        # Still not candidate without stronger CI / cost evidence
        if (
            skip_h["bootstrap"]["ci_low"] == skip_h["bootstrap"]["ci_low"]
            and skip_h["bootstrap"]["ci_low"] > 0
            and skip_h.get("cost_1_5x_positive")
            and skip_h["active_folds_all_positive"]
        ):
            verdict = "CANDIDATE_FOR_FUTURE_SHADOW_TEST"
            why = "Predicted-vol filter shows multi-fold expectancy gains with supportive CI/cost checks — still not production."
        else:
            verdict = "PROMISING_BUT_UNCONFIRMED"
            why = "Some predicted-vol conditioned H13_C subsets look better, but CI/cost/fold confirmation is incomplete."
    elif vol_ok and not decision_gain:
        verdict = "VOLATILITY_PREDICTION_ONLY"
        why = "fwd_vol_12 prediction remains useful, but it does not improve H13_C decision expectancy under predeclared policies."
    elif decision_gain:
        verdict = "PROMISING_BUT_UNCONFIRMED"
        why = "Possible decision-quality signal under filters, but volatility prediction and/or fold evidence is incomplete."
    else:
        verdict = "NO_DECISION_VALUE"
        why = "No reliable decision-time value from predicted volatility for H13_C outcomes."

    assert verdict in VALID_VERDICTS
    return {
        "verdict": verdict,
        "rationale": why,
        "production_ready": False,
        "champion_status": CHAMPION_STATUS,
        "h13c_status": H13C_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "phase25_verdict_preserved": PHASE25_VERDICT,
        "phase26_verdict_preserved": PHASE26_VERDICT,
        "trading_edge_claimed": False,
    }


# re-export helper used by runner
def enrich_trades(trades, pred_vol, regimes):
    return _attach_vol(trades, pred_vol, regimes)
