"""Statistical discovery on frozen discovery dates only."""

from __future__ import annotations

from typing import Any

from phase49.constants import ALPHA, BONFERRONI_N
from phase49.stats import block_permutation_pvalue, date_block_bootstrap, leave_one_date_out, mean


def _tercile_edges(values: list[float]) -> tuple[float, float]:
    vs = sorted(values)
    n = len(vs)
    lo = vs[max(0, n // 3 - 1)]
    hi = vs[min(n - 1, (2 * n) // 3)]
    return lo, hi


def evaluate_hypotheses(
    events: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    *,
    freeze_edges: dict[str, tuple[float, float]] | None = None,
    fit_edges: bool = True,
) -> dict[str, Any]:
    """
    For each hypothesis: select tercile tail on feature; score action net_R.
    Effect = mean(selected net_R) - mean(unconditional action net_R on all events).
    """
    edges: dict[str, tuple[float, float]] = dict(freeze_edges or {})
    results = []

    for hyp in hypotheses:
        fid = hyp["feature_id"]
        action = hyp["action"]
        tail = hyp["tail"]
        key = f"{fid}"
        vals = []
        for e in events:
            v = e["features"].get(fid)
            if v is None:
                continue
            vals.append(float(v))
        if len(vals) < 30:
            results.append({**hyp, "status": "INSUFFICIENT_FEATURE_N", "n_feature": len(vals)})
            continue
        if fit_edges and key not in edges:
            edges[key] = _tercile_edges(vals)
        lo, hi = edges[key]

        selected_pairs: list[tuple[str, float]] = []
        universe_pairs: list[tuple[str, float]] = []
        for e in events:
            v = e["features"].get(fid)
            if v is None:
                continue
            outcome = e["buy"] if action == "BUY" else e["sell"]
            if outcome.get("data_quality_status") != "OK" or outcome.get("net_r") is None:
                continue
            nr = float(outcome["net_r"])
            universe_pairs.append((e["day"], nr))
            if tail == "high" and float(v) >= hi:
                selected_pairs.append((e["day"], nr))
            elif tail == "low" and float(v) <= lo:
                selected_pairs.append((e["day"], nr))

        if len(selected_pairs) < 20:
            results.append(
                {
                    **hyp,
                    "status": "INSUFFICIENT_SELECTED_N",
                    "n_selected": len(selected_pairs),
                    "edges": {"lo": lo, "hi": hi},
                }
            )
            continue

        sel_mean = mean([v for _, v in selected_pairs])
        uni_mean = mean([v for _, v in universe_pairs])
        effect = (sel_mean - uni_mean) if sel_mean is not None and uni_mean is not None else None
        # Bootstrap on selected net_R (absolute level) and on excess vs uni_mean
        boot = date_block_bootstrap(selected_pairs)
        excess_pairs = [(d, v - (uni_mean or 0)) for d, v in selected_pairs]
        boot_ex = date_block_bootstrap(excess_pairs, seed=49 + hash(hyp["hypothesis_id"]) % 1000)
        lodo = leave_one_date_out(selected_pairs)
        perm = block_permutation_pvalue(selected_pairs, universe_pairs)

        # Cost stress: STRESS_SPREAD_WIDEN_1_5X
        stress_pairs = []
        for e in events:
            v = e["features"].get(fid)
            if v is None:
                continue
            outcome = e["buy"] if action == "BUY" else e["sell"]
            if outcome.get("data_quality_status") != "OK":
                continue
            if (tail == "high" and float(v) >= hi) or (tail == "low" and float(v) <= lo):
                sn = (outcome.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
                if sn.get("net_r") is not None:
                    stress_pairs.append((e["day"], float(sn["net_r"])))
        boot_stress = date_block_bootstrap(stress_pairs) if len(stress_pairs) >= 20 else {"ok": False}

        survives = bool(
            boot.get("ok")
            and boot.get("bonferroni_excludes_zero")
            and (sel_mean or 0) > 0
            and lodo.get("ok")
            and lodo.get("frac_positive", 0) >= 0.7
            and boot_stress.get("ok")
            and boot_stress.get("mean", -1) > 0
        )

        results.append(
            {
                **hyp,
                "status": "EVALUATED",
                "edges": {"lo": lo, "hi": hi},
                "n_selected": len(selected_pairs),
                "n_universe": len(universe_pairs),
                "mean_net_r": sel_mean,
                "unconditional_mean_net_r": uni_mean,
                "effect_vs_unconditional": effect,
                "bootstrap": boot,
                "bootstrap_excess": boot_ex,
                "lodo": {k: v for k, v in lodo.items() if k != "rows"},
                "permutation": perm,
                "stress_bootstrap": boot_stress,
                "survives_discovery": survives,
                "alpha": ALPHA,
                "bonferroni_n": BONFERRONI_N,
            }
        )

    survivors = [r for r in results if r.get("survives_discovery")]
    return {
        "n_hypotheses": len(hypotheses),
        "n_evaluated": sum(1 for r in results if r.get("status") == "EVALUATED"),
        "n_survivors": len(survivors),
        "survivors": [r["hypothesis_id"] for r in survivors],
        "results": results,
        "frozen_edges": {k: {"lo": v[0], "hi": v[1]} for k, v in edges.items()},
        "note": "Discovery only. Confirmation sealed until survivors exist.",
    }


def baselines(events: list[dict[str, Any]]) -> dict[str, Any]:
    buy = [(e["day"], float(e["buy"]["net_r"])) for e in events if e["buy"].get("net_r") is not None]
    sell = [(e["day"], float(e["sell"]["net_r"])) for e in events if e["sell"].get("net_r") is not None]
    return {
        "ALWAYS_WAIT_mean": 0.0,
        "constant_BUY": {"mean": mean([v for _, v in buy]), "n": len(buy), "bootstrap": date_block_bootstrap(buy)},
        "constant_SELL": {"mean": mean([v for _, v in sell]), "n": len(sell), "bootstrap": date_block_bootstrap(sell)},
    }
