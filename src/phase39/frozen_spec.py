"""Freeze and verify candidate specs against Phase36 artifacts before evaluation."""

from __future__ import annotations

import json
from typing import Any

from phase39.constants import (
    FROZEN_MEAN_REVERSION,
    H13C_FROZEN_CUTS,
    HORIZON_BARS,
    PHASE36_FROZEN,
    RECIPE_ID,
    SL_MULT,
    TP_MULT,
)
from phase39.progress import write_json


def verify_and_freeze() -> dict[str, Any]:
    discrepancies: list[str] = []
    p36 = {}
    if PHASE36_FROZEN.is_file():
        p36 = json.loads(PHASE36_FROZEN.read_text(encoding="utf-8"))
        params = p36.get("parameters") or {}
        for k, v in FROZEN_MEAN_REVERSION.items():
            if k not in params:
                discrepancies.append(f"Phase36 missing param {k}")
            elif params[k] != v:
                discrepancies.append(f"MR param mismatch {k}: phase25={v} phase36={params[k]}")
        exit_rules = p36.get("exit_rules") or {}
        if exit_rules.get("horizon_bars") != HORIZON_BARS:
            discrepancies.append(
                f"horizon mismatch: phase39={HORIZON_BARS} phase36={exit_rules.get('horizon_bars')}"
            )
        if exit_rules.get("tp_atr_multiple") != TP_MULT:
            discrepancies.append(f"TP mismatch: {TP_MULT} vs {exit_rules.get('tp_atr_multiple')}")
        if exit_rules.get("sl_atr_multiple") != SL_MULT:
            discrepancies.append(f"SL mismatch: {SL_MULT} vs {exit_rules.get('sl_atr_multiple')}")
    else:
        discrepancies.append("Phase36 frozen_experiment_registry.json missing")

    spec = {
        "recipe_id": RECIPE_ID,
        "frozen_before_evaluation": True,
        "optimization_forbidden": True,
        "discrepancies": discrepancies,
        "spec_ok": len(discrepancies) == 0,
        "candidates": {
            "H13_C": {
                "status": "PAUSED_FROZEN_BENCHMARK",
                "cuts": {
                    "close_ema_low": H13C_FROZEN_CUTS["close_ema_low"],
                    "close_ema_high": H13C_FROZEN_CUTS["close_ema_high"],
                    "q_low": H13C_FROZEN_CUTS.get("q_low"),
                    "q_high": H13C_FROZEN_CUTS.get("q_high"),
                    "train_cutoff": H13C_FROZEN_CUTS.get("train_cutoff"),
                },
                "rules": {
                    "BUY": "h1_trend==up AND close_to_ema_20<=close_ema_low AND ema_9_20_spread>0",
                    "SELL": "h1_trend==down AND close_to_ema_20>=close_ema_high AND ema_9_20_spread<0",
                },
                "execution": {
                    "entry": "next M5 open; BUY ask / SELL bid",
                    "exit": "BUY bid / SELL ask; TP 1.5 ATR; SL 1.0 ATR; horizon 12",
                },
                "data_dependency_note": (
                    "H1 EMA20 requires 20 completed H1 bars. Phase38 isolated days typically "
                    "cannot supply this within a single session → expect missing H1 context."
                ),
            },
            "mean_reversion": {
                "parameters": dict(FROZEN_MEAN_REVERSION),
                "rules": (p36.get("entry_rules") if p36 else {}),
                "execution": {
                    "entry": "next M5 open; BUY ask / SELL bid",
                    "exit": "BUY bid / SELL ask; TP 1.5 ATR; SL 1.0 ATR; horizon 12",
                    "source": "Phase36 frozen_experiment_registry.json + Phase25 STRATEGY_PARAMS",
                },
            },
        },
        "phase36_source_hashes": (p36.get("source_hashes") if p36 else {}),
    }
    write_json("frozen_candidate_spec.json", spec)
    return spec
