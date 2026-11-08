"""Reproduce existing RF validation and conditional-edge results in memory.

Does not write models or overwrite research CSVs. Comparisons are against the
saved reports/CSVs. Calculation paths are the original functions imported
from backtest_rf_m5.py and research_rf_m5_conditional_edge.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_rf_m5 import (
    TRADES_PATH,
    check_against_validation,
    generate_signals,
    load_market,
    load_model,
    load_validation_period,
    run_backtest,
)
from evaluation.constants import RF_VALIDATION_PUBLISHED, TIME_FORMAT
from evaluation.metrics import closed_trade_metrics
from evaluation.splits import walk_forward_windows
from label_m5 import RAW_PATH
from research_kronos_m5 import assert_no_test_rows
from research_rf_m5_conditional_edge import (
    RESULTS_PATH as CE_RESULTS_PATH,
    analyse_groups,
    attach_context,
    normalize_trades,
    walk_forward_trades,
)
from train_rf_m5 import MODEL_PATH
from analyze_rf_m5_trades import atr_pct_bucket_edges


def regenerate_validation_trades() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Saved-model validation backtest, identical path to backtest_rf_m5.main()."""
    model, model_features = load_model(MODEL_PATH)
    val, start, end = load_validation_period(TRADES_PATH.parent / "xauusd_m5_validation.csv")
    raw, features, positions, bar_limit = load_market(start, end)
    check_against_validation(features, val, model_features)
    signals = generate_signals(model, features, model_features)
    trades, skipped = run_backtest(raw, features, positions, signals)
    saved = pd.read_csv(TRADES_PATH)
    saved_metrics = closed_trade_metrics(saved)
    regen_metrics = closed_trade_metrics(trades)
    return trades, saved, {
        "regenerated": regen_metrics,
        "saved_csv": saved_metrics,
        "skipped": dict(skipped),
        "bar_limit": str(bar_limit),
        "n_signals": int(len(signals)),
    }


def _match_trades(regen: pd.DataFrame, saved: pd.DataFrame) -> dict:
    r = regen.copy()
    s = saved.copy()
    for df in (r, s):
        for col in ("signal_time", "entry_time", "exit_time"):
            df[col] = pd.to_datetime(df[col])
    r = r.sort_values("signal_time").reset_index(drop=True)
    s = s.sort_values("signal_time").reset_index(drop=True)
    n = len(r)
    if len(s) != n:
        return {"trades_equal": False, "regen_n": n, "saved_n": len(s)}
    checks = {
        "n": n,
        "signal_time": bool((r["signal_time"] == s["signal_time"]).all()),
        "side": bool((r["side"] == s["side"]).all()),
        "exit_reason": bool((r["exit_reason"] == s["exit_reason"]).all()),
        "net_pnl": bool(np.allclose(r["net_pnl"], s["net_pnl"], rtol=0, atol=1e-12)),
        "net_pnl_r": bool(np.allclose(r["net_pnl_r"], s["net_pnl_r"], rtol=0, atol=1e-12)),
    }
    checks["trades_equal"] = all(checks[k] for k in ("signal_time", "side", "exit_reason", "net_pnl", "net_pnl_r"))
    return checks


def compare_to_published(metrics: dict) -> dict:
    pub = RF_VALIDATION_PUBLISHED
    return {
        "trades": {"value": int(metrics["trades"]), "published": pub["trades"],
                   "match": int(metrics["trades"]) == pub["trades"]},
        "net_pnl": {"value": float(metrics["net_pnl"]), "published": pub["net_pnl"],
                    "abs_diff": abs(float(metrics["net_pnl"]) - pub["net_pnl"]),
                    "within_0_01": abs(float(metrics["net_pnl"]) - pub["net_pnl"]) < 0.01},
        "avg_r": {"value": float(metrics["avg_r"]), "published": pub["avg_r"],
                  "abs_diff": abs(float(metrics["avg_r"]) - pub["avg_r"]),
                  "within_5e-5": abs(float(metrics["avg_r"]) - pub["avg_r"]) < 5e-5},
        "profit_factor": {"value": float(metrics["profit_factor"]), "published": pub["profit_factor"],
                          "abs_diff": abs(float(metrics["profit_factor"]) - pub["profit_factor"]),
                          "within_5e-4": abs(float(metrics["profit_factor"]) - pub["profit_factor"]) < 5e-4},
        "max_drawdown_usd": {"value": float(metrics["max_drawdown_usd"]), "published": pub["max_drawdown_usd"],
                             "abs_diff": abs(float(metrics["max_drawdown_usd"]) - pub["max_drawdown_usd"]),
                             "within_0_02": abs(float(metrics["max_drawdown_usd"]) - pub["max_drawdown_usd"]) < 0.02},
    }


def reproduce_rf_validation() -> dict:
    regen, saved, info = regenerate_validation_trades()
    match = _match_trades(regen, saved)
    published = compare_to_published(info["regenerated"])
    exact = match.get("trades_equal", False)
    rounded_ok = all(published[k][flag] for k, flag in (
        ("trades", "match"), ("net_pnl", "within_0_01"), ("avg_r", "within_5e-5"),
        ("profit_factor", "within_5e-4"), ("max_drawdown_usd", "within_0_02"),
    ))
    return {
        "exact_match_to_saved_csv": exact,
        "rounded_match_to_published_report": rounded_ok,
        "trade_equality": match,
        "published_comparison": published,
        "regenerated_metrics": {k: info["regenerated"][k] for k in
                                ("trades", "net_pnl", "avg_r", "profit_factor",
                                 "max_drawdown_usd", "buy_trades", "sell_trades")},
        "skipped": info["skipped"],
        "discrepancies": [] if exact and rounded_ok else _list_rf_discrepancies(match, published),
    }


def _list_rf_discrepancies(match: dict, published: dict) -> list[dict]:
    out = []
    if not match.get("trades_equal", False):
        out.append({"metric": "trade_table", "detail": match})
    for name, row in published.items():
        flag = [k for k in row if k.startswith("within") or k == "match"]
        if flag and not row[flag[0]]:
            out.append({"metric": name, "value": row["value"], "published": row["published"],
                        "abs_diff": row.get("abs_diff")})
    return out


def reproduce_conditional_edge(raw, features, full_labeled) -> dict:
    """Retrain the three walk-forward RFs in memory (frozen params) and compare
    subgroup tables to the saved research CSV. No files are written.
    """
    times = features["time"]
    wf_windows = walk_forward_windows(times)
    atr_edges, _ = atr_pct_bucket_edges()

    # Baseline integrity: saved model regenerates the validation trades.
    regen, saved, _ = regenerate_validation_trades()
    baseline_ok = _match_trades(regen, saved).get("trades_equal", False)

    main = attach_context(normalize_trades(pd.read_csv(TRADES_PATH)), features, atr_edges)
    wf_trades, wf_meta = walk_forward_trades(raw, features, full_labeled, wf_windows)
    wf_trades = attach_context(wf_trades, features, atr_edges)
    groups = analyse_groups(main, wf_trades)

    saved_groups = pd.read_csv(CE_RESULTS_PATH)
    saved_g = saved_groups[saved_groups["section"] == "group"].copy()
    compare_cols = [
        "dimension", "group", "main_trades", "main_avg_r",
        "WF1_trades", "WF1_avg_r", "WF2_trades", "WF2_avg_r", "WF3_trades", "WF3_avg_r",
        "wf_mean_avg_r", "wf_candidate", "fdr_reject", "wf_candidate_after_fdr", "classification",
    ]
    merged = groups[compare_cols].merge(saved_g[compare_cols], on=["dimension", "group"], suffixes=("_new", "_old"))
    mismatches = []
    bool_cols = {"wf_candidate", "fdr_reject", "wf_candidate_after_fdr"}
    int_cols = {"main_trades", "WF1_trades", "WF2_trades", "WF3_trades"}
    for _, row in merged.iterrows():
        for col in compare_cols[2:]:
            a, b = row[f"{col}_new"], row[f"{col}_old"]
            if _cells_equal(a, b, col, bool_cols, int_cols):
                continue
            item = {"group": row["group"], "dimension": row["dimension"], "column": col, "new": a, "old": b}
            try:
                item["abs_diff"] = abs(float(a) - float(b))
            except (TypeError, ValueError):
                pass
            mismatches.append(item)

    all_row = groups[(groups["dimension"] == "SIDE") & (groups["group"] == "ALL")].iloc[0]
    conclusion = ("No stable conditional edge found."
                  if not groups["wf_candidate_after_fdr"].any()
                  else "REPEATED_BEHAVIOUR_CANDIDATE present")
    return {
        "baseline_trades_match": baseline_ok,
        "wf_meta": wf_meta,
        "wf_trade_counts": {m["window"]: m["trades"] for m in wf_meta},
        "all_group": {
            "wf_pooled_trades": int(all_row["wf_pooled_trades"]),
            "wf_pooled_avg_r": float(all_row["wf_pooled_avg_r"]),
            "WF1_avg_r": float(all_row["WF1_avg_r"]),
            "WF2_avg_r": float(all_row["WF2_avg_r"]),
            "WF3_avg_r": float(all_row["WF3_avg_r"]),
            "classification": all_row["classification"],
        },
        "n_groups": int(len(groups)),
        "n_wf_candidates": int(groups["wf_candidate"].sum()),
        "n_fdr_reject": int(groups["fdr_reject"].sum()),
        "n_repeated_behaviour": int(groups["wf_candidate_after_fdr"].sum()),
        "conclusion": conclusion,
        "conclusion_matches_saved": conclusion == "No stable conditional edge found.",
        "n_mismatches_vs_saved_csv": len(mismatches),
        "mismatches": mismatches[:40],
        "wf_trades": wf_trades,
        "groups": groups,
    }


def _as_bool(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes"}
    return bool(v)


def _cells_equal(a, b, col, bool_cols, int_cols) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if col in bool_cols:
        return _as_bool(a) == _as_bool(b)
    if col in int_cols:
        try:
            return int(a) == int(b)
        except (TypeError, ValueError):
            return False
    if col == "classification":
        return str(a).strip() == str(b).strip()
    try:
        if not np.isfinite(a) and not np.isfinite(b):
            return True
        return bool(np.allclose(float(a), float(b), rtol=0, atol=1e-10))
    except (TypeError, ValueError):
        return str(a) == str(b)


def load_labeled_research(val_end, cutoff=None) -> pd.DataFrame:
    labeled_path = RAW_PATH.parent / "xauusd_m5_labeled.csv"
    labeled = pd.read_csv(labeled_path)
    labeled["time"] = pd.to_datetime(labeled["time"], format=TIME_FORMAT)
    labeled = labeled[labeled["time"] <= val_end].reset_index(drop=True)
    assert_no_test_rows(labeled)
    return labeled
