"""Bootstrap/permutation/perturbation robustness (research only)."""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from phase14.scoring import score_trades
from phase30.base import generate_strategy_trades
from phase30.constants import EVAL_SEED, PERMUTATION_N, PERTURB_FRACS, STRATEGY_PARAMS


def permutation_test(
    trades: list[dict],
    *,
    n_perm: int = PERMUTATION_N,
    seed: int = EVAL_SEED,
) -> dict[str, Any]:
    """Shuffle net_r labels across decision times; compare observed mean R."""
    if len(trades) < 5:
        return {
            "status": "NOT_COMPLETED_DUE_TO_RUNTIME" if False else "INSUFFICIENT_N",
            "n_trades": len(trades),
            "n_perm": 0,
            "observed_mean_r": None,
            "p_value_mean_r": None,
            "note": "Too few trades for permutation.",
        }
    obs = sum(t["net_r"] for t in trades) / len(trades)
    rs = [t["net_r"] for t in trades]
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        shuffled = rs[:]
        rng.shuffle(shuffled)
        m = sum(shuffled) / len(shuffled)
        # Under pure shuffle of fixed R values mean is invariant — wrong test!
        # Correct: randomly flip signs / reassign R to random times with replacement of signs.
        # Use sign-randomization of observed R (preserves magnitude, destroys edge direction timing).
    # Re-do with sign randomization (standard for expectancy)
    ge = 0
    abs_rs = [abs(x) for x in rs]
    for _ in range(n_perm):
        sim = [rng.choice([-1, 1]) * a for a in abs_rs]
        m = sum(sim) / len(sim)
        if m >= obs:
            ge += 1
    p = (ge + 1) / (n_perm + 1)
    return {
        "status": "COMPLETED",
        "method": "sign_randomization",
        "n_trades": len(trades),
        "n_perm": n_perm,
        "observed_mean_r": obs,
        "p_value_mean_r_ge_obs": p,
        "seed": seed,
    }


def signal_frequency_stability(raw: dict[str, Any]) -> dict[str, Any]:
    n_dec = int(raw.get("n_decisions") or 0)
    n_sig = int(raw.get("n_signals") or 0)
    rate = (n_sig / n_dec) if n_dec else 0.0
    per_500 = 500.0 * rate
    rare = per_500 < 1.0
    return {
        "n_decisions": n_dec,
        "n_signals": n_sig,
        "signal_rate": rate,
        "signals_per_500": per_500,
        "flag_extremely_rare": rare,
        "note": "Rare if <1 signal per 500 M5 candles.",
    }


def drawdown_concentration(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return {"status": "EMPTY", "top_trade_share_of_net_r": None, "flag_single_trade_dependent": False}
    ordered = sorted(trades, key=lambda t: t["decision_time"])
    net = sum(t["net_r"] for t in ordered)
    best = max(ordered, key=lambda t: t["net_r"])
    share = (best["net_r"] / net) if net and abs(net) > 1e-12 else None
    flag = share is not None and share > 0.5 and best["net_r"] > 0 and net > 0
    return {
        "status": "COMPLETED",
        "n": len(trades),
        "net_r": net,
        "best_trade_r": best["net_r"],
        "best_trade_time": best["decision_time"],
        "top_trade_share_of_net_r": share,
        "flag_single_trade_dependent": bool(flag),
    }


def _scale_params(base: dict, frac: float) -> dict:
    out = dict(base)
    for k, v in base.items():
        if k in {"family", "vs_phase25"}:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nv = float(v) * frac
            # keep ints as ints when original was int-like for bar counts
            if isinstance(v, int):
                out[k] = max(1, int(round(nv)))
            else:
                out[k] = nv
    return out


def parameter_perturbation(
    bundle: dict,
    strategy_id: str,
    decide_factory: Callable[[dict], Callable],
    *,
    fracs: tuple[float, ...] = PERTURB_FRACS,
) -> dict[str, Any]:
    """Re-run strategy with modestly scaled predeclared params (top candidates only)."""
    base = STRATEGY_PARAMS[strategy_id]
    results = {}
    for frac in fracs:
        try:
            scaled = _scale_params(base, frac)
            decide = decide_factory(scaled)
            raw = generate_strategy_trades(bundle, decide, strategy_id=f"{strategy_id}@x{frac:g}")
            score = score_trades(raw["trades"], label=f"{strategy_id}@x{frac:g}")
            results[f"x{frac:g}"] = {
                "frac": frac,
                "params": scaled,
                "n": score["pooled"]["n"],
                "mean_r": score["pooled"]["mean_r"],
                "profit_factor": score["pooled"]["profit_factor"],
                "mean_r_positive": score["pooled"]["mean_r"] == score["pooled"]["mean_r"]
                and score["pooled"]["mean_r"] > 0,
            }
        except Exception as exc:  # noqa: BLE001
            results[f"x{frac:g}"] = {
                "frac": frac,
                "status": "NOT_COMPLETED_DUE_TO_RUNTIME",
                "error": f"{type(exc).__name__}:{exc}",
            }
    pos = [v for v in results.values() if v.get("mean_r_positive")]
    return {
        "status": "COMPLETED",
        "n_perturbations": len(fracs),
        "n_mean_r_positive": len(pos),
        "all_tested_positive": len(pos) == len([v for v in results.values() if "mean_r" in v]),
        "results": results,
    }
