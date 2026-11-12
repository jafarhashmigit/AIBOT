"""Statistical integrity checks — reconcile aggregates; no new edge search."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean
from phase32.constants import EVAL_SEED, OUTCOMES_PATH, PHASE30_SUMMARY, PHASE31_FINAL
import pandas as pd


def run_statistical_validation(gross_net: dict[str, Any] | None = None) -> dict[str, Any]:
    # Reconcile Phase30 stored nets vs recomputed nets if provided
    reconcile = {}
    if gross_net and PHASE30_SUMMARY.exists():
        summary = json.loads(PHASE30_SUMMARY.read_text(encoding="utf-8"))
        for sid, block in gross_net.get("strategies", {}).items():
            if sid == "H13_C":
                stored = summary["h13c_benchmark"]["metrics"]["score"]["pooled"]["mean_r"]
            else:
                stored = summary["strategies"][sid]["metrics"]["score"]["pooled"]["mean_r"]
            got = block["net"]["mean_r"]
            reconcile[sid] = {
                "stored_mean_r": stored,
                "recomputed_mean_r": got,
                "abs_diff": None if got is None else abs(float(got) - float(stored)),
                "match": got is not None and abs(float(got) - float(stored)) < 1e-9,
            }

    # Day-cluster bootstrap on eligible BUY sample (dependence-aware)
    df = pd.read_csv(OUTCOMES_PATH)
    elig = df[(df["eligible"] == True) & (df["side"] == "BUY")].dropna(subset=["net_r"])  # noqa: E712
    elig = elig.sort_values("decision_time").head(3000)
    values = elig["net_r"].to_numpy(dtype=float)
    times = elig["decision_time"].astype(str).tolist()
    boot = day_cluster_bootstrap_mean(times, values, n_samples=500, seed=EVAL_SEED)

    p31 = None
    if PHASE31_FINAL.exists():
        p31 = json.loads(PHASE31_FINAL.read_text(encoding="utf-8"))

    return {
        "phase30_aggregate_reconciliation": reconcile,
        "all_recomputed_nets_match_phase30": all(v.get("match") for v in reconcile.values()) if reconcile else None,
        "bootstrap": {
            "unit": "calendar_day_cluster",
            "n_trades_sample": int(len(values)),
            "result": boot,
            "note": "Overlapping trades → prefer day-cluster over IID trade bootstrap",
        },
        "phase31_permutation_note": (
            "Phase30 sign-randomization is not treated as proof of edge (Phase31 finding)."
        ),
        "phase31_final_verdict": None if not p31 else p31.get("phase_verdict"),
        "no_subgroup_search": True,
        "no_threshold_optimization": True,
    }
