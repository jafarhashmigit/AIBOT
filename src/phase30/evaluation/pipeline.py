"""Full Phase 30 evaluation pipeline with checkpointing."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from phase14.scoring import score_trades
from phase14.strategy import generate_h13c_trades
from phase30.base import generate_strategy_trades
from phase30.constants import (
    CANDIDATE_ID_H13C,
    CHAMPION_STATUS,
    COST_MULTS,
    EVAL_SEED,
    H13C_ROLE,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STRATEGY_PARAMS,
    TOP_N_FOR_ROBUSTNESS,
)
from phase30.evaluation.metrics import evaluate_trades
from phase30.progress import load_progress, log, save_progress
from phase30.ranking.rank import (
    classify_strategy,
    composite_rank,
    multiple_testing_summary,
    phase_verdict,
)
from phase30.robustness.checks import (
    drawdown_concentration,
    parameter_perturbation,
    permutation_test,
    signal_frequency_stability,
)
from phase30.strategies import STRATEGIES


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


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(obj), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _strategy_artifact_path(reports_dir: Path, sid: str) -> Path:
    return reports_dir / "checkpoints" / f"{sid}.json"


def _make_decide_factory(strategy_id: str) -> Callable[[dict], Callable]:
    """Build decide(ctx) using temporarily scaled STRATEGY_PARAMS."""

    def factory(scaled: dict) -> Callable:
        import phase30.constants as c
        import importlib

        mod_name = {
            "vol_norm_momentum": "phase30.strategies.vol_norm_momentum",
            "compression_expansion": "phase30.strategies.compression_expansion",
            "robust_mad_reversion": "phase30.strategies.robust_mad_reversion",
            "regression_residual_mr": "phase30.strategies.regression_residual_mr",
            "wick_exhaustion": "phase30.strategies.wick_exhaustion",
            "regime_cond_momentum": "phase30.strategies.regime_cond_momentum",
            "london_open_imbalance": "phase30.strategies.london_open_imbalance",
            "m15_trend_m5_trigger": "phase30.strategies.m15_trend_m5_trigger",
            "body_persistence": "phase30.strategies.body_persistence",
            "momentum_structure_ensemble": "phase30.strategies.momentum_structure_ensemble",
        }[strategy_id]

        def decide(ctx: dict) -> tuple[str, str, float]:
            old = dict(c.STRATEGY_PARAMS[strategy_id])
            c.STRATEGY_PARAMS[strategy_id] = scaled
            try:
                mod = importlib.import_module(mod_name)
                # Refresh module-level P binding
                mod.P = scaled
                return mod.decide(ctx)
            finally:
                c.STRATEGY_PARAMS[strategy_id] = old
                mod.P = old

        return decide

    return factory


def evaluate_all(bundle: dict, *, reports_dir: Path | None = None, resume: bool = True) -> dict[str, Any]:
    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    prog = load_progress(out_dir) if resume else {
        "stage": "init",
        "completed_strategies": [],
        "completed_folds": ["WF1", "WF2", "WF3"],
        "completed_robustness": [],
        "last_successful_operation": None,
    }
    prog["stage"] = "h13c_benchmark"
    save_progress(prog, out_dir)

    log("H13_C frozen benchmark ...")
    h13c_raw = generate_h13c_trades(bundle)
    h13c_metrics = evaluate_trades(h13c_raw["trades"], label=CANDIDATE_ID_H13C, cost_mults=COST_MULTS)
    h13c_mean = h13c_metrics["mean_r"]
    prog["last_successful_operation"] = "h13c_benchmark"
    save_progress(prog, out_dir)
    log("H13_C benchmark complete")

    n_strats = len(STRATEGIES)
    strategies_out: dict[str, Any] = {}
    completed = set(prog.get("completed_strategies") or [])

    for i, (sid, decide) in enumerate(STRATEGIES.items(), start=1):
        art = _strategy_artifact_path(out_dir, sid)
        if resume and sid in completed and art.exists():
            log(f"Strategy {i}/{n_strats}: {sid} (resume checkpoint)")
            strategies_out[sid] = json.loads(art.read_text(encoding="utf-8"))
            continue
        log(f"Strategy {i}/{n_strats}: {sid}")
        prog["stage"] = f"strategy:{sid}"
        save_progress(prog, out_dir)
        raw = generate_strategy_trades(bundle, decide, strategy_id=sid)
        metrics = evaluate_trades(raw["trades"], label=sid, cost_mults=COST_MULTS)
        freq = signal_frequency_stability(raw)
        dd = drawdown_concentration(raw["trades"])
        block = {
            "params": STRATEGY_PARAMS[sid],
            "n_decisions": raw["n_decisions"],
            "n_signals": raw["n_signals"],
            "n_trades": raw["n_trades"],
            "n_buy": raw["n_buy"],
            "n_sell": raw["n_sell"],
            "n_wait": raw["n_wait"],
            "signal_rate": raw["signal_rate"],
            "signals_per_500": raw["signals_per_500"],
            "metrics": metrics,
            "frequency": freq,
            "drawdown_concentration": dd,
            "robustness": None,
            "decision": None,
        }
        _write(art, block)
        strategies_out[sid] = block
        completed.add(sid)
        prog["completed_strategies"] = sorted(completed)
        prog["last_successful_operation"] = f"strategy:{sid}"
        save_progress(prog, out_dir)

    # Initial classification without full robustness (for shortlist)
    log("WF evaluation / initial gates ...")
    for sid, block in strategies_out.items():
        block["decision"] = classify_strategy(
            strategy_id=sid,
            metrics=block["metrics"],
            robustness=None,
            h13c_mean_r=h13c_mean if isinstance(h13c_mean, float) else float("nan"),
            n_strategies_tested=n_strats,
        )

    # Shortlist top N by mean R among mean_r>0 OR by composite prelim
    prelim_rows = []
    for sid, block in strategies_out.items():
        prelim_rows.append(
            {
                "strategy_id": sid,
                "metrics": block["metrics"],
                "decision": block["decision"],
                "robustness": None,
            }
        )
    prelim_ranked = composite_rank(prelim_rows)
    shortlist = [r["strategy_id"] for r in prelim_ranked[:TOP_N_FOR_ROBUSTNESS]]
    # Prefer positive expectancy for robustness budget
    pos = [r["strategy_id"] for r in prelim_ranked if r["decision"]["gates"]["B_mean_r_gt_0"]]
    if pos:
        shortlist = list(dict.fromkeys(pos[:TOP_N_FOR_ROBUSTNESS] + shortlist))[:TOP_N_FOR_ROBUSTNESS]
    log(f"Robustness shortlist: {shortlist}")

    prog["stage"] = "robustness"
    save_progress(prog, out_dir)
    rob_done = set(prog.get("completed_robustness") or [])

    for sid in shortlist:
        if resume and sid in rob_done and strategies_out[sid].get("robustness"):
            log(f"Robustness {sid} (resume)")
            continue
        log(f"Bootstrap already in score; permutation {sid} ...")
        trades = []  # regenerate lightly via checkpoint metrics only — need trades again
        # Re-generate trades for robustness (deterministic)
        raw = generate_strategy_trades(bundle, STRATEGIES[sid], strategy_id=sid)
        trades = raw["trades"]
        log(f"Permutation {sid} ...")
        perm = permutation_test(trades)
        log(f"Parameter perturbation {sid} ...")
        try:
            perturb = parameter_perturbation(
                bundle, sid, _make_decide_factory(sid)
            )
        except Exception as exc:  # noqa: BLE001
            perturb = {"status": "NOT_COMPLETED_DUE_TO_RUNTIME", "error": f"{type(exc).__name__}:{exc}"}
        rob = {
            "permutation": perm,
            "parameter_perturbation": perturb,
            "frequency": signal_frequency_stability(raw),
            "drawdown_concentration": drawdown_concentration(trades),
        }
        strategies_out[sid]["robustness"] = rob
        strategies_out[sid]["decision"] = classify_strategy(
            strategy_id=sid,
            metrics=strategies_out[sid]["metrics"],
            robustness=rob,
            h13c_mean_r=h13c_mean if isinstance(h13c_mean, float) else float("nan"),
            n_strategies_tested=n_strats,
        )
        _write(_strategy_artifact_path(out_dir, sid), strategies_out[sid])
        rob_done.add(sid)
        prog["completed_robustness"] = sorted(rob_done)
        prog["last_successful_operation"] = f"robustness:{sid}"
        save_progress(prog, out_dir)

    # Reclassify all (non-shortlist keep gates F=None/False)
    for sid, block in strategies_out.items():
        block["decision"] = classify_strategy(
            strategy_id=sid,
            metrics=block["metrics"],
            robustness=block.get("robustness"),
            h13c_mean_r=h13c_mean if isinstance(h13c_mean, float) else float("nan"),
            n_strategies_tested=n_strats,
        )

    log("Ranking ...")
    prog["stage"] = "ranking"
    save_progress(prog, out_dir)
    rank_rows = []
    for sid, block in strategies_out.items():
        rank_rows.append(
            {
                "strategy_id": sid,
                "metrics": block["metrics"],
                "decision": block["decision"],
                "robustness": block.get("robustness"),
                "n_trades": block["n_trades"],
                "signals_per_500": block["signals_per_500"],
            }
        )
    ranked = composite_rank(rank_rows)
    decisions = {sid: strategies_out[sid]["decision"] for sid in strategies_out}
    mt = multiple_testing_summary(decisions)
    verdict = phase_verdict(decisions)

    # Fold results table
    fold_results = {"H13_C": h13c_metrics["score"]["folds"]}
    for sid, block in strategies_out.items():
        fold_results[sid] = block["metrics"]["score"]["folds"]

    result = {
        "recipe": RECIPE_ID,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": EVAL_SEED,
        "champion_status": CHAMPION_STATUS,
        "h13c_status": H13C_STATUS,
        "h13c_role": H13C_ROLE,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "phase_verdict": verdict,
        "h13c_benchmark": {
            "candidate_id": CANDIDATE_ID_H13C,
            "role": H13C_ROLE,
            "n_trades": h13c_raw["n_trades"],
            "n_buy": sum(1 for t in h13c_raw["trades"] if t["side"] == "BUY"),
            "n_sell": sum(1 for t in h13c_raw["trades"] if t["side"] == "SELL"),
            "metrics": h13c_metrics,
            "frozen": True,
        },
        "strategies": strategies_out,
        "ranking": [
            {
                "rank": r["rank"],
                "strategy_id": r["strategy_id"],
                "composite_score": r["composite_score"],
                "status": r["decision"]["status"],
                "n": r["metrics"]["n"],
                "mean_r": r["metrics"]["mean_r"],
                "profit_factor": r["metrics"]["profit_factor"],
                "max_drawdown_usd": r["metrics"]["max_drawdown_usd"],
                "signals_per_500": r.get("signals_per_500"),
            }
            for r in ranked
        ],
        "fold_results": fold_results,
        "multiple_testing": mt,
        "robustness_shortlist": shortlist,
        "diversity": {
            "n_positive_mean_r": sum(
                1 for b in strategies_out.values() if b["decision"]["gates"]["B_mean_r_gt_0"]
            ),
            "n_fold_stable": sum(
                1 for b in strategies_out.values() if b["decision"]["gates"]["D_fold_stability"]
            ),
            "n_research_candidate": sum(
                1 for b in strategies_out.values() if b["decision"]["status"] == "RESEARCH_CANDIDATE"
            ),
            "n_promising": sum(
                1
                for b in strategies_out.values()
                if b["decision"]["status"] == "PROMISING_BUT_UNCONFIRMED"
            ),
        },
    }
    prog["stage"] = "complete"
    prog["last_successful_operation"] = "evaluate_all_complete"
    save_progress(prog, out_dir)
    log(f"Final verdict ... {verdict}")
    return result


def write_json_reports(result: dict[str, Any], reports_dir: Path | None = None) -> dict[str, str]:
    out = reports_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    mapping = {
        "strategy_results.json": {
            "h13c_benchmark": result["h13c_benchmark"],
            "strategies": result["strategies"],
            "phase_verdict": result["phase_verdict"],
        },
        "fold_results.json": result["fold_results"],
        "robustness_results.json": {
            sid: block.get("robustness")
            for sid, block in result["strategies"].items()
            if block.get("robustness")
        },
        "ranking.json": {
            "ranking": result["ranking"],
            "multiple_testing": result["multiple_testing"],
            "diversity": result["diversity"],
        },
        "final_verdict.json": {
            "phase_verdict": result["phase_verdict"],
            "champion_status": result["champion_status"],
            "h13c_status": result["h13c_status"],
            "production_final_action": result["production_final_action"],
            "ranking_top": result["ranking"][:5],
            "diversity": result["diversity"],
            "multiple_testing": result["multiple_testing"],
        },
    }
    for name, obj in mapping.items():
        p = out / name
        _write(p, obj)
        paths[name] = str(p)
    summary = out / "phase30_summary.json"
    _write(summary, result)
    paths["phase30_summary.json"] = str(summary)
    return paths
