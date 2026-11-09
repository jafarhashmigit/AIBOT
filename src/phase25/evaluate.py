"""Walk-forward evaluation vs frozen H13_C. No parameter search."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase14.scoring import cost_robustness, score_trades, session_vol_breakdown
from phase14.strategy import generate_h13c_trades
from phase25.base import generate_strategy_trades
from phase25.constants import (
    CANDIDATE_GATES,
    CANDIDATE_ID_H13C,
    CHAMPION_STATUS,
    COST_MULTS,
    EVAL_SEED,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STRATEGY_PARAMS,
    VALID_STATUSES,
)
from phase25.strategies import STRATEGIES


def _safe_gt0(x: float | None) -> bool:
    return x is not None and x == x and x > 0


def classify_strategy(
    *,
    score: dict,
    cost: dict,
    h13c_mean_r: float,
    strategy_id: str,
) -> dict[str, Any]:
    pooled = score["pooled"]
    gates = {
        "pooled_mean_r_gt_0": _safe_gt0(pooled["mean_r"]),
        "ci_low_gt_0": _safe_gt0(pooled["bootstrap"]["ci_low"]),
        "all_active_folds_mean_r_gt_0": bool(score.get("all_active_folds_positive")),
        "cost_1_5x_mean_r_gt_0": _safe_gt0((cost.get("1.5x") or {}).get("mean_r")),
        "min_pooled_n": pooled["n"] >= int(CANDIDATE_GATES["min_pooled_n"]),
        "min_days": pooled["n_days"] >= int(CANDIDATE_GATES["min_days"]),
        "beats_h13c_pooled_mean_r": _safe_gt0(pooled["mean_r"])
        and pooled["mean_r"] > h13c_mean_r,
    }
    n = pooled["n"]
    mean_r = pooled["mean_r"]

    if n < 20:
        status = "INCONCLUSIVE"
        why = "Too few trades for credible inference."
    elif mean_r == mean_r and mean_r <= 0 and not _safe_gt0(pooled["bootstrap"]["ci_high"]):
        status = "REJECTED"
        why = "Non-positive expectancy with CI not supporting upside."
    elif mean_r == mean_r and mean_r <= 0:
        status = "REJECTED"
        why = "Pooled mean net R <= 0 after costs."
    elif all(gates.values()):
        status = "CANDIDATE_FOR_FUTURE_SHADOW_TEST"
        why = "Positive expectancy, WF consistency, cost robustness, and beats H13_C pooled mean R."
    elif gates["pooled_mean_r_gt_0"] and (
        gates["all_active_folds_mean_r_gt_0"] or gates["cost_1_5x_mean_r_gt_0"]
    ):
        status = "PROMISING_BUT_UNCONFIRMED"
        why = "Positive pooled mean R but incomplete candidate gates."
    elif gates["pooled_mean_r_gt_0"]:
        status = "INCONCLUSIVE"
        why = "Positive pooled mean R without fold/cost/CI confirmation."
    else:
        status = "REJECTED"
        why = "Failed primary expectancy / robustness checks."

    assert status in VALID_STATUSES
    return {
        "strategy_id": strategy_id,
        "status": status,
        "rationale": why,
        "gates": gates,
        "production_ready": False,
        "champion_unchanged": CHAMPION_STATUS,
        "h13c_unchanged": H13C_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
    }


def compare_to_h13c(strat_score: dict, h13c_score: dict) -> dict[str, Any]:
    sp = strat_score["pooled"]
    hp = h13c_score["pooled"]
    return {
        "strat_n": sp["n"],
        "h13c_n": hp["n"],
        "strat_mean_r": sp["mean_r"],
        "h13c_mean_r": hp["mean_r"],
        "delta_mean_r": (sp["mean_r"] - hp["mean_r"])
        if sp["mean_r"] == sp["mean_r"] and hp["mean_r"] == hp["mean_r"]
        else float("nan"),
        "strat_profit_factor": sp["profit_factor"],
        "h13c_profit_factor": hp["profit_factor"],
        "strat_win_rate": sp["win_rate"],
        "h13c_win_rate": hp["win_rate"],
        "strat_max_dd_usd": sp["max_drawdown_usd"],
        "h13c_max_dd_usd": hp["max_drawdown_usd"],
        "strat_net_r": sp["net_r"],
        "h13c_net_r": hp["net_r"],
        "folds": {
            fid: {
                "strat_n": strat_score["folds"][fid]["n"],
                "strat_mean_r": strat_score["folds"][fid]["mean_r"],
                "h13c_n": h13c_score["folds"][fid]["n"],
                "h13c_mean_r": h13c_score["folds"][fid]["mean_r"],
            }
            for fid in ("WF1", "WF2", "WF3")
        },
    }


def evaluate_all(bundle: dict) -> dict[str, Any]:
    h13c_raw = generate_h13c_trades(bundle)
    h13c_score = score_trades(h13c_raw["trades"], label=CANDIDATE_ID_H13C)
    h13c_cost = cost_robustness(h13c_raw["trades"], COST_MULTS)
    h13c_sess = session_vol_breakdown(h13c_raw["trades"])
    h13c_mean = h13c_score["pooled"]["mean_r"]

    strategies_out: dict[str, Any] = {}
    for sid, decide in STRATEGIES.items():
        raw = generate_strategy_trades(bundle, decide, strategy_id=sid)
        score = score_trades(raw["trades"], label=sid)
        cost = cost_robustness(raw["trades"], COST_MULTS)
        sess = session_vol_breakdown(raw["trades"])
        decision = classify_strategy(
            score=score, cost=cost, h13c_mean_r=h13c_mean, strategy_id=sid
        )
        strategies_out[sid] = {
            "params": STRATEGY_PARAMS[sid],
            "n_signals": raw["n_signals"],
            "n_trades": raw["n_trades"],
            "n_buy": raw["n_buy"],
            "n_sell": raw["n_sell"],
            "n_wait": raw["n_wait"],
            "score": score,
            "cost_robustness": cost,
            "session_vol": sess,
            "vs_h13c": compare_to_h13c(score, h13c_score),
            "decision": decision,
        }

    statuses = [v["decision"]["status"] for v in strategies_out.values()]
    any_candidate = any(s == "CANDIDATE_FOR_FUTURE_SHADOW_TEST" for s in statuses)
    phase_verdict = "NEW_EDGE_CANDIDATE_FOUND" if any_candidate else "NO_NEW_EDGE_FOUND"

    return {
        "recipe": RECIPE_ID,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": EVAL_SEED,
        "champion_status": CHAMPION_STATUS,
        "h13c_status": H13C_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "phase_verdict": phase_verdict,
        "h13c_benchmark": {
            "candidate_id": CANDIDATE_ID_H13C,
            "n_signals": h13c_raw.get("n_selected_before_outcome", len(h13c_raw["trades"])),
            "n_trades": h13c_raw["n_trades"],
            "n_buy": sum(1 for t in h13c_raw["trades"] if t["side"] == "BUY"),
            "n_sell": sum(1 for t in h13c_raw["trades"] if t["side"] == "SELL"),
            "h1_coverage": h13c_raw.get("h1_coverage"),
            "score": h13c_score,
            "cost_robustness": h13c_cost,
            "session_vol": h13c_sess,
            "frozen": True,
            "note": "H13_C thresholds and generator unchanged; benchmark only.",
        },
        "strategies": strategies_out,
        "multiple_testing_note": (
            "Five predeclared strategies + one frozen benchmark evaluated once. "
            "No iterative parameter search against validation folds."
        ),
    }


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize(v) for v in obj]
    return obj


def write_reports(result: dict, reports_dir: Path | None = None) -> dict[str, str]:
    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    summary_path = out_dir / "phase25_summary.json"
    summary_path.write_text(json.dumps(_sanitize(result), indent=2), encoding="utf-8")
    paths["summary"] = str(summary_path)

    cmp_rows = []
    h = result["h13c_benchmark"]["score"]["pooled"]
    cmp_rows.append(
        {
            "strategy": CANDIDATE_ID_H13C,
            "role": "benchmark",
            "status": H13C_STATUS,
            "n": h["n"],
            "mean_r": h["mean_r"],
            "net_r": h["net_r"],
            "profit_factor": h["profit_factor"],
            "win_rate": h["win_rate"],
            "max_dd_usd": h["max_drawdown_usd"],
            "ci_low": h["bootstrap"]["ci_low"],
            "ci_high": h["bootstrap"]["ci_high"],
        }
    )
    for sid, block in result["strategies"].items():
        p = block["score"]["pooled"]
        cmp_rows.append(
            {
                "strategy": sid,
                "role": "experimental",
                "status": block["decision"]["status"],
                "n": p["n"],
                "mean_r": p["mean_r"],
                "net_r": p["net_r"],
                "profit_factor": p["profit_factor"],
                "win_rate": p["win_rate"],
                "max_dd_usd": p["max_drawdown_usd"],
                "ci_low": p["bootstrap"]["ci_low"],
                "ci_high": p["bootstrap"]["ci_high"],
            }
        )
    cmp_path = out_dir / "comparative_results.json"
    cmp_path.write_text(json.dumps(_sanitize(cmp_rows), indent=2), encoding="utf-8")
    paths["comparative"] = str(cmp_path)

    decisions = {sid: block["decision"] for sid, block in result["strategies"].items()}
    decisions["phase_verdict"] = result["phase_verdict"]
    dec_path = out_dir / "strategy_decisions.json"
    dec_path.write_text(json.dumps(_sanitize(decisions), indent=2), encoding="utf-8")
    paths["decisions"] = str(dec_path)
    return paths
