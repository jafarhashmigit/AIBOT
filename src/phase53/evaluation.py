"""Policy evaluation, baselines, controls, discovery/confirmation gates."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from phase49.stats import leave_one_date_out, mean
from phase53.constants import ALPHA, BONFERRONI_N, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, MIN_POLICY_TRADES
from phase53.policies import apply_policy, fit_ood_bounds


def date_block_bootstrap(
    pairs: list[tuple[str, float]],
    *,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
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
    alpha_b = ALPHA / BONFERRONI_N
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


def _pairs(decisions: list[dict[str, Any]], key: str = "net_r") -> list[tuple[str, float]]:
    out = []
    for d in decisions:
        v = d.get(key)
        if v is None:
            continue
        out.append((d["day"], float(v)))
    return out


def calibrate(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [d for d in decisions if d["action"] in ("BUY", "SELL") and d.get("net_r") is not None]
    waits = [d for d in decisions if d["action"] == "WAIT"]
    nets = [float(d["net_r"]) for d in trades]
    all_nets = [float(d["net_r"]) for d in decisions if d.get("net_r") is not None]
    downside = sorted(nets)[max(0, int(0.05 * len(nets)))] if nets else None
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
        "downside_p05_trades": downside,
        "mean_stress_trades": mean(
            [float(d["stress_net_r"]) for d in trades if d.get("stress_net_r") is not None]
        ),
    }


def baseline_constant(events: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    out = []
    for e in sorted(events, key=lambda x: (x["day"], x["decision_idx"])):
        if action == "WAIT":
            net_r, stress = 0.0, 0.0
        else:
            oc = e["buy"] if action == "BUY" else e["sell"]
            net_r = float(oc["net_r"]) if oc.get("net_r") is not None else None
            sn = (oc.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
            stress = float(sn["net_r"]) if sn.get("net_r") is not None else None
        out.append(
            {
                "day": e["day"],
                "decision_bar": e["decision_bar"],
                "action": action,
                "net_r": net_r,
                "stress_net_r": stress,
            }
        )
    return out


def _outcome_nets(event: dict[str, Any], action: str) -> tuple[float | None, float | None]:
    if action == "WAIT":
        return 0.0, 0.0
    oc = event["buy"] if action == "BUY" else event["sell"]
    net_r = float(oc["net_r"]) if oc.get("net_r") is not None else None
    sn = (oc.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
    stress = float(sn["net_r"]) if sn.get("net_r") is not None else None
    return net_r, stress


def randomized_action_control(
    events: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    seed: int = BOOTSTRAP_SEED,
) -> list[dict[str, Any]]:
    """Shuffle action labels across events; realize net_R from each event's BUY/SELL/WAIT path."""
    rng = random.Random(seed)
    actions = [d["action"] for d in decisions]
    rng.shuffle(actions)
    by_key = {(e["day"], e["decision_idx"]): e for e in events}
    out = []
    for d, action in zip(decisions, actions):
        ev = by_key[(d["day"], d["decision_idx"])]
        net_r, stress = _outcome_nets(ev, action)
        out.append(
            {
                "day": d["day"],
                "decision_bar": d["decision_bar"],
                "decision_idx": d["decision_idx"],
                "action": action,
                "net_r": net_r,
                "stress_net_r": stress,
                "randomized": True,
            }
        )
    return out


def static_policy_control(
    events: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep WAIT schedule; on trade slots force majority direction and realize that path's net_R."""
    trades = [d["action"] for d in decisions if d["action"] in ("BUY", "SELL")]
    if not trades:
        return list(decisions)
    maj = "BUY" if trades.count("BUY") >= trades.count("SELL") else "SELL"
    by_key = {(e["day"], e["decision_idx"]): e for e in events}
    out = []
    for d in decisions:
        ev = by_key[(d["day"], d["decision_idx"])]
        if d["action"] == "WAIT":
            out.append(dict(d))
            continue
        net_r, stress = _outcome_nets(ev, maj)
        out.append(
            {
                "day": d["day"],
                "decision_bar": d["decision_bar"],
                "decision_idx": d["decision_idx"],
                "action": maj,
                "net_r": net_r,
                "stress_net_r": stress,
                "static_control": True,
            }
        )
    return out


def summarize_decisions(decisions: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    pairs = _pairs(decisions)
    stress_pairs = _pairs(decisions, "stress_net_r")
    cal = calibrate(decisions)
    boot = (
        date_block_bootstrap(pairs, n_draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED)
        if len({d for d, _ in pairs}) >= 2
        else {"ok": False}
    )
    lodo = leave_one_date_out(pairs) if len({d for d, _ in pairs}) >= 3 else {"ok": False}
    trade_days = sorted({d["day"] for d in decisions if d["action"] in ("BUY", "SELL")})
    return {
        "label": label,
        "calibration": cal,
        "bootstrap": boot,
        "lodo": {k: v for k, v in lodo.items() if k != "rows"} if isinstance(lodo, dict) else lodo,
        "stress_mean": mean([v for _, v in stress_pairs]),
        "stress_bootstrap": date_block_bootstrap(stress_pairs) if len({d for d, _ in stress_pairs}) >= 2 else {"ok": False},
        "n_trade_dates": len(trade_days),
        "trade_dates": trade_days,
    }


def discovery_gate(summary: dict[str, Any], baselines: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    cal = summary.get("calibration") or {}
    boot = summary.get("bootstrap") or {}
    lodo = summary.get("lodo") or {}
    stress_b = summary.get("stress_bootstrap") or {}
    pol_mean = cal.get("expected_net_r_all_decisions")
    buy_m = (baselines.get("CONSTANT_BUY") or {}).get("calibration", {}).get("expected_net_r_all_decisions")
    sell_m = (baselines.get("CONSTANT_SELL") or {}).get("calibration", {}).get("expected_net_r_all_decisions")
    wait_m = 0.0
    rand_m = (controls.get("randomized") or {}).get("calibration", {}).get("expected_net_r_all_decisions")
    static_m = (controls.get("static") or {}).get("calibration", {}).get("expected_net_r_all_decisions")

    reasons = []
    if (cal.get("n_trades") or 0) < MIN_POLICY_TRADES:
        reasons.append("insufficient_trades")
    if (summary.get("n_trade_dates") or 0) < 3:
        reasons.append("depends_on_too_few_dates")
    if pol_mean is None or pol_mean <= wait_m:
        reasons.append("does_not_beat_ALWAYS_WAIT")
    if buy_m is not None and (pol_mean is None or pol_mean <= buy_m):
        reasons.append("does_not_beat_CONSTANT_BUY")
    if sell_m is not None and (pol_mean is None or pol_mean <= sell_m):
        reasons.append("does_not_beat_CONSTANT_SELL")
    if rand_m is not None and (pol_mean is None or pol_mean <= rand_m):
        reasons.append("does_not_beat_randomized_action")
    if static_m is not None and (pol_mean is None or pol_mean <= static_m):
        reasons.append("does_not_beat_static_control")
    if not boot.get("ok") or not boot.get("bonferroni_excludes_zero") or boot.get("ci95_low", -1) <= 0:
        reasons.append("bootstrap_ci_fails")
    if not lodo.get("ok") or (lodo.get("frac_positive") or 0) < 0.7:
        reasons.append("lodo_not_robust")
    if not stress_b.get("ok") or (stress_b.get("mean") or -1) <= 0:
        # stress on all decisions includes WAIT zeros — require trade stress mean > 0
        if (cal.get("mean_stress_trades") or -1) <= 0:
            reasons.append("cost_stress_eliminates_edge")

    survives = len(reasons) == 0
    return {
        "survives_discovery": survives,
        "fail_reasons": reasons,
        "policy_mean_all": pol_mean,
        "baseline_means": {"BUY": buy_m, "SELL": sell_m, "WAIT": wait_m, "random": rand_m, "static": static_m},
    }


def confirmation_gate(summary: dict[str, Any], baselines: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    """Stricter one-shot confirmation: CI95>0, beat wait+const+random, stress ok, LODO ok."""
    gate = discovery_gate(summary, baselines, controls)
    boot = summary.get("bootstrap") or {}
    extra = []
    if not boot.get("ok") or boot.get("ci95_low", -1) <= 0:
        extra.append("confirmation_ci95_not_positive")
    # At confirmation, Bonferroni already applied at discovery; still require ci95
    ok = gate["survives_discovery"] and not extra
    return {
        "confirmed": ok,
        "fail_reasons": gate["fail_reasons"] + extra,
        "policy_mean_all": gate["policy_mean_all"],
        "baseline_means": gate["baseline_means"],
    }


def evaluate_family(
    events: list[dict[str, Any]],
    family_id: str,
    *,
    ood_bounds: dict[str, Any] | None,
    fit_ood: bool,
) -> dict[str, Any]:
    bounds = fit_ood_bounds(events) if fit_ood else (ood_bounds or {})
    decisions = apply_policy(events, family_id, ood_bounds=bounds)
    summary = summarize_decisions(decisions, label=family_id)

    bas_buy = summarize_decisions(baseline_constant(events, "BUY"), label="CONSTANT_BUY")
    bas_sell = summarize_decisions(baseline_constant(events, "SELL"), label="CONSTANT_SELL")
    bas_wait = summarize_decisions(baseline_constant(events, "WAIT"), label="ALWAYS_WAIT")
    rnd = summarize_decisions(randomized_action_control(events, decisions), label="RANDOMIZED_ACTION")
    stc = summarize_decisions(static_policy_control(events, decisions), label="STATIC_POLICY")

    baselines = {"CONSTANT_BUY": bas_buy, "CONSTANT_SELL": bas_sell, "ALWAYS_WAIT": bas_wait}
    controls = {"randomized": rnd, "static": stc}
    gate = discovery_gate(summary, baselines, controls)

    return {
        "family_id": family_id,
        "ood_bounds": bounds,
        "summary": summary,
        "baselines": {k: v.get("calibration") for k, v in baselines.items()},
        "baseline_full": baselines,
        "controls": {k: v.get("calibration") for k, v in controls.items()},
        "controls_full": controls,
        "gate": gate,
        "n_decisions": len(decisions),
        "decisions_sample": decisions[:5],
    }


def run_discovery(events: list[dict[str, Any]], family_ids: list[str]) -> dict[str, Any]:
    results = []
    frozen_ood: dict[str, Any] = {}
    for fid in family_ids:
        # Fit OOD once on discovery for first family then reuse same bounds for all (shared regime)
        if not frozen_ood:
            frozen_ood = fit_ood_bounds(events)
        rec = evaluate_family(events, fid, ood_bounds=frozen_ood, fit_ood=False)
        rec["ood_bounds"] = frozen_ood
        results.append(rec)
    survivors = [r for r in results if r["gate"]["survives_discovery"]]
    return {
        "n_families": len(family_ids),
        "frozen_ood_bounds": frozen_ood,
        "results": results,
        "n_survivors": len(survivors),
        "survivors": [r["family_id"] for r in survivors],
        "note": "Discovery only. Confirmation sealed until freeze.",
    }


def run_confirmation(
    events: list[dict[str, Any]],
    survivor_ids: list[str],
    *,
    frozen_ood: dict[str, Any],
) -> dict[str, Any]:
    if not survivor_ids:
        return {"opened": False, "reason": "no_discovery_survivors", "n_confirmed": 0, "confirmed_ids": []}
    results = []
    confirmed = []
    for fid in survivor_ids:
        rec = evaluate_family(events, fid, ood_bounds=frozen_ood, fit_ood=False)
        conf = confirmation_gate(rec["summary"], rec["baseline_full"], rec["controls_full"])
        rec["confirmation_gate"] = conf
        results.append(rec)
        if conf["confirmed"]:
            confirmed.append(fid)
    return {
        "opened": True,
        "n_events": len(events),
        "n_survivors_tested": len(survivor_ids),
        "n_confirmed": len(confirmed),
        "confirmed_ids": confirmed,
        "results": results,
        "note": "Opened exactly once after freeze. No retuning.",
    }
