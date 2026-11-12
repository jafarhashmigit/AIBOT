"""Baselines, discovery/validation gates, Bonferroni date-block tests."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from phase49.stats import leave_one_date_out, mean
from phase58.constants import (
    ALPHA,
    BONFERRONI_N,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    MIN_POLICY_TRADES,
)
from phase58.policies import (
    POLICIES,
    apply_H58_W1_nogate,
    fit_thresholds,
)


def date_block_bootstrap(
    pairs: list[tuple[str, float]],
    *,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
    bonferroni_n: int = BONFERRONI_N,
) -> dict[str, Any]:
    by: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        by[d].append(v)
    days = sorted(by)
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rng = random.Random(seed)
    means = []
    for _ in range(n_draws):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals: list[float] = []
        for d in sample:
            vals.extend(by[d])
        if vals:
            means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    alpha_b = ALPHA / bonferroni_n
    q = max(0, int(alpha_b * len(means)))
    qh = min(len(means) - 1, int((1 - alpha_b) * len(means)) - 1)
    return {
        "ok": True,
        "n_dates": len(days),
        "mean": sum(means) / len(means),
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "bonferroni_alpha": alpha_b,
        "bonferroni_ci_low": means[q],
        "bonferroni_ci_high": means[qh],
        "bonferroni_excludes_zero": means[q] > 0 or means[qh] < 0,
        "prob_mean_le_0": sum(1 for m in means if m <= 0) / len(means),
    }


def calibrate(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [d for d in decisions if d["action"] in ("BUY", "SELL") and d.get("net_r") is not None]
    waits = [d for d in decisions if d["action"] == "WAIT"]
    nets = [float(d["net_r"]) for d in trades]
    all_nets = [float(d["net_r"]) for d in decisions if d.get("net_r") is not None]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None
    # drawdown on cumulative all_nets in order
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for x in all_nets:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n_decisions": len(decisions),
        "n_trades": len(trades),
        "n_wait": len(waits),
        "action_counts": {
            "BUY": sum(1 for d in decisions if d["action"] == "BUY"),
            "SELL": sum(1 for d in decisions if d["action"] == "SELL"),
            "WAIT": len(waits),
        },
        "p_positive_net_r_trades": (sum(1 for x in nets if x > 0) / len(nets)) if nets else None,
        "expected_net_r_trades": mean(nets),
        "expected_net_r_all_decisions": mean(all_nets),
        "profit_factor": pf,
        "max_drawdown_R": dd,
        "downside_p05_trades": sorted(nets)[max(0, int(0.05 * len(nets)))] if nets else None,
        "commission": None,
        "slippage": None,
        "note": "gross/net_R from bid/ask path only; commission/slippage UNKNOWN",
    }


def baseline_constant(events: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if action == "WAIT":
            out.append({"day": e["day"], "decision_idx": e["decision_idx"], "action": "WAIT", "net_r": 0.0})
        else:
            oc = e["buy"] if action == "BUY" else e["sell"]
            out.append(
                {
                    "day": e["day"],
                    "decision_idx": e["decision_idx"],
                    "action": action,
                    "net_r": float(oc["net_r"]) if oc.get("net_r") is not None else None,
                }
            )
    return out


def run_policy(events: list[dict[str, Any]], hyp_id: str, thr: dict[str, float]) -> list[dict[str, Any]]:
    fn = POLICIES[hyp_id]
    out = []
    for e in events:
        e2 = dict(e)
        e2["hypothesis_id"] = hyp_id
        out.append(fn(e2, thr))
    return out


def evaluate_hypothesis(
    hyp_id: str,
    discovery_events: list[dict[str, Any]],
    validation_events: list[dict[str, Any]],
) -> dict[str, Any]:
    thr = fit_thresholds(discovery_events)
    disc = run_policy(discovery_events, hyp_id, thr)
    cal = calibrate(disc)
    pairs = [(d["day"], float(d["net_r"])) for d in disc if d.get("net_r") is not None]
    boot = date_block_bootstrap(pairs)
    lodo = leave_one_date_out(pairs)

    # baselines
    b_wait = calibrate(baseline_constant(discovery_events, "WAIT"))
    b_buy = calibrate(baseline_constant(discovery_events, "BUY"))
    b_sell = calibrate(baseline_constant(discovery_events, "SELL"))
    # matched-frequency random control
    rng = random.Random(BOOTSTRAP_SEED + hash(hyp_id) % 10_000)
    n_trade = cal["n_trades"]
    idxs = list(range(len(discovery_events)))
    pick = set(rng.sample(idxs, min(n_trade, len(idxs)))) if n_trade else set()
    rand_dec = []
    for i, e in enumerate(discovery_events):
        if i in pick:
            side = "BUY" if rng.random() < 0.5 else "SELL"
            oc = e["buy"] if side == "BUY" else e["sell"]
            rand_dec.append({"day": e["day"], "action": side, "net_r": float(oc["net_r"])})
        else:
            rand_dec.append({"day": e["day"], "action": "WAIT", "net_r": 0.0})
    b_rand = calibrate(rand_dec)

    # W1-specific control: 1-bar sign without gate
    control_nogate = None
    if hyp_id == "H58_W1_COSTLY_SPREAD_WAIT":
        ng = [apply_H58_W1_nogate(e, thr) for e in discovery_events]
        control_nogate = calibrate(ng)

    disc_fail: list[str] = []
    if cal["n_trades"] < MIN_POLICY_TRADES:
        disc_fail.append("insufficient_trades")
    mean_all = cal["expected_net_r_all_decisions"]
    if mean_all is None or mean_all <= (b_wait["expected_net_r_all_decisions"] or 0):
        disc_fail.append("does_not_beat_WAIT")
    if not boot.get("ok") or not boot.get("bonferroni_excludes_zero"):
        disc_fail.append("bootstrap_ci_fails")
    if control_nogate and (mean_all or 0) <= (control_nogate.get("expected_net_r_all_decisions") or 0):
        disc_fail.append("does_not_beat_nogate_control")
    survives_discovery = len(disc_fail) == 0

    # validation only if discovery passes
    val = None
    val_boot = None
    val_ok = False
    fail = list(disc_fail)
    if survives_discovery:
        val_dec = run_policy(validation_events, hyp_id, thr)
        val = calibrate(val_dec)
        val_pairs = [(d["day"], float(d["net_r"])) for d in val_dec if d.get("net_r") is not None]
        val_boot = date_block_bootstrap(val_pairs, bonferroni_n=1)
        val_ok = bool(
            val_boot.get("ok")
            and val_boot.get("ci95_excludes_zero")
            and (val.get("expected_net_r_all_decisions") or 0) > 0
        )
        if not val_ok:
            fail.append("validation_fails")

    return {
        "hypothesis_id": hyp_id,
        "thresholds": thr,
        "discovery": cal,
        "bootstrap": boot,
        "lodo": lodo,
        "baselines": {"WAIT": b_wait, "BUY": b_buy, "SELL": b_sell, "random": b_rand},
        "control_nogate": control_nogate,
        "validation": val,
        "validation_bootstrap": val_boot,
        "survives_discovery": survives_discovery,
        "survives_validation": val_ok,
        "fail_reasons": fail,
    }
