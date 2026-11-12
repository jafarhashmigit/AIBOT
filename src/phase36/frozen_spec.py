"""Immutable frozen mean_reversion experiment registration — before evaluation."""

from __future__ import annotations

from typing import Any

from phase36.constants import (
    EXCLUDED_EVAL_DAYS,
    FROZEN_MEAN_REVERSION_PARAMS,
    HORIZON_BARS,
    PROJECT_ROOT,
    RECIPE_ID,
    RESEARCH_CUTOFF_UTC,
    SL_MULT,
    TP_MULT,
    file_sha256,
)
from phase36.progress import write_json

SOURCE_FILES = (
    "src/phase25/strategies/mean_reversion.py",
    "src/phase25/constants.py",
    "src/phase25/indicators.py",
)


def register_frozen_experiment() -> dict[str, Any]:
    hashes = {}
    for rel in SOURCE_FILES:
        path = PROJECT_ROOT / rel
        hashes[rel] = file_sha256(path) if path.is_file() else None

    spec = {
        "recipe_id": RECIPE_ID,
        "strategy_id": "mean_reversion",
        "frozen_before_evaluation": True,
        "source_hashes": hashes,
        "parameters": dict(FROZEN_MEAN_REVERSION_PARAMS),
        "entry_rules": {
            "indicators": ["zscore(closes, z_window)", "rsi_14", "atr_14_pct", "volatility_ratio_12_48"],
            "BUY": "z <= -z_entry AND rsi <= rsi_buy_max AND atr_pct in [min,max] AND vol_ratio <= vol_ratio_max",
            "SELL": "z >= z_entry AND rsi >= rsi_sell_min AND atr_pct in [min,max] AND vol_ratio <= vol_ratio_max",
            "WAIT": "otherwise / insufficient_history",
        },
        "exit_rules": {
            "horizon_bars": HORIZON_BARS,
            "tp_atr_multiple": TP_MULT,
            "sl_atr_multiple": SL_MULT,
            "entry_timing": "next M5 bar open after signal bar close",
            "overlap": "independent signals per bar; no portfolio netting in this phase",
            "BUY_entry": "ASK",
            "BUY_exit": "BID",
            "SELL_entry": "BID",
            "SELL_exit": "ASK",
            "barrier_path": "chronological tick path; never M5 OHLC first-touch alone",
        },
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "excluded_phase34_35_days": sorted(EXCLUDED_EVAL_DAYS),
        "date_selection_algorithm": (
            "All Mon–Fri in [2026-02-16, 2026-09-29] excluding EXCLUDED_EVAL_DAYS; "
            "select up to 20 evenly spaced indices (deterministic round((i*(n-1)/(k-1)))). "
            "No performance/volatility/direction/signal-based selection."
        ),
        "execution_methodology": (
            "Phase35-equivalent bid/ask tick-path simulation on reconstructed M5 from Dukascopy bi5; "
            "UNRESOLVED_DATA_GAP when path incomplete; no fabricated ticks/candles; "
            "no silent $0.05/side on primary view."
        ),
        "rules_locked": True,
        "optimization_forbidden": True,
    }
    write_json("frozen_experiment_registry.json", spec)
    return spec
