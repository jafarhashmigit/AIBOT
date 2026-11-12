"""Hypothesis evaluation — reuse Phase58 bootstrap/calibrate; Bonferroni family=3."""

from __future__ import annotations

import random
from typing import Any

from phase49.stats import leave_one_date_out
from phase58.evaluation import baseline_constant, calibrate, date_block_bootstrap
from phase65.constants import BONFERRONI_N, BOOTSTRAP_SEED, MIN_POLICY_TRADES
from phase65.policies import POLICIES, fit_thresholds


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
    boot = date_block_bootstrap(pairs, bonferroni_n=BONFERRONI_N, seed=BOOTSTRAP_SEED)
    lodo = leave_one_date_out(pairs)

    b_wait = calibrate(baseline_constant(discovery_events, "WAIT"))
    b_buy = calibrate(baseline_constant(discovery_events, "BUY"))
    b_sell = calibrate(baseline_constant(discovery_events, "SELL"))

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

    disc_fail: list[str] = []
    if cal["n_trades"] < MIN_POLICY_TRADES:
        disc_fail.append("insufficient_trades")
    mean_all = cal["expected_net_r_all_decisions"]
    if mean_all is None or mean_all <= (b_wait["expected_net_r_all_decisions"] or 0):
        disc_fail.append("does_not_beat_WAIT")
    if not boot.get("ok") or not boot.get("bonferroni_excludes_zero") or not (
        boot.get("bonferroni_ci_low", 0) > 0
    ):
        # require positive side exclusion for edge claim
        disc_fail.append("bootstrap_ci_fails")
    survives_discovery = len(disc_fail) == 0

    val = None
    val_boot = None
    val_ok = False
    fail = list(disc_fail)
    if survives_discovery:
        val_dec = run_policy(validation_events, hyp_id, thr)
        val = calibrate(val_dec)
        val_pairs = [(d["day"], float(d["net_r"])) for d in val_dec if d.get("net_r") is not None]
        val_boot = date_block_bootstrap(val_pairs, bonferroni_n=1, seed=BOOTSTRAP_SEED)
        val_ok = bool(
            val_boot.get("ok")
            and val_boot.get("ci95_excludes_zero")
            and (val_boot.get("ci95_low") or 0) > 0
            and (val.get("expected_net_r_all_decisions") or 0) > 0
        )
        if not val_ok:
            fail.append("validation_fails")

    incr = (mean_all or 0) - (b_wait["expected_net_r_all_decisions"] or 0)
    return {
        "hypothesis_id": hyp_id,
        "thresholds": thr,
        "discovery": cal,
        "bootstrap": boot,
        "lodo": lodo,
        "baselines": {"WAIT": b_wait, "BUY": b_buy, "SELL": b_sell, "random": b_rand},
        "incremental_vs_WAIT": incr,
        "validation": val,
        "validation_bootstrap": val_boot,
        "survives_discovery": survives_discovery,
        "survives_validation": val_ok,
        "fail_reasons": fail,
    }
