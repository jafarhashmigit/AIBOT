"""Future MT5 parity protocol — no MT5 connection in Phase 33."""

from __future__ import annotations

from typing import Any

from phase33.constants import (
    MT5_FEATURES_PATH,
    POINT_SIZE,
    RESEARCH_CUTOFF_UTC,
    SYMBOL,
    TIMEFRAME,
)
from phase33.progress import write_json


def inspect_mt5_dataset() -> dict[str, Any]:
    """Read-only metadata about approved historical MT5 features (no new MT5 access)."""
    exists = MT5_FEATURES_PATH.is_file()
    meta: dict[str, Any] = {
        "path": str(MT5_FEATURES_PATH).replace("\\", "/"),
        "exists": exists,
        "mt5_connected_this_phase": False,
        "new_mt5_data_accessed": False,
    }
    if not exists:
        return meta
    # Inspect header + first/last lines only
    with MT5_FEATURES_PATH.open("r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        first = f.readline().strip()
        # seek near end
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read().splitlines()
        last = tail[-1] if tail else ""
    meta.update(
        {
            "columns": header,
            "has_open": "open" in header,
            "has_high": "high" in header,
            "has_low": "low" in header,
            "has_close": "close" in header,
            "has_spread": "spread" in header,
            "has_bid_ohlc": any(c.startswith("bid_") for c in header),
            "has_ask_ohlc": any(c.startswith("ask_") for c in header),
            "first_row_prefix": first[:120],
            "last_row_prefix": last[:120],
            "price_convention_note": (
                "Feature OHLC is mid/broker candle convention used throughout research; "
                "spread column is min-within-bar points, not full bid/ask OHLC."
            ),
        }
    )
    return meta


def define_parity_protocol() -> dict[str, Any]:
    mt5 = inspect_mt5_dataset()
    protocol = {
        "status": "MT5_PARITY_PENDING",
        "authorized_this_phase": False,
        "mt5_connection_performed": False,
        "distinction": {
            "source_data_comparison": (
                "Compare Dukascopy-constructed M5 bid/ask/mid to existing approved MT5 feature file "
                "on overlapping UTC timestamps (mid close vs feature close; spread vs Dukascopy spread)."
            ),
            "genuine_mt5_parity_test": (
                "Requires identical-window MT5 bid AND ask series (or tick) exported under the same "
                "UTC M5 boundaries — NOT authorized / not available as separate bid/ask OHLC in the "
                "approved features file. Cannot report PASS without both sides observed."
            ),
        },
        "identity_requirements": {
            "instrument": SYMBOL,
            "timeframe": TIMEFRAME,
            "utc_intervals": True,
            "m5_boundaries": "floor to 5-minute UTC opens",
            "price_convention": "USD absolute; point_size=0.01",
            "bid_definition": "executable sell / long-exit price",
            "ask_definition": "executable buy / short-exit price",
            "decimal_precision": "compare at 0.001 native quantum; report diffs in USD and points",
            "missing_candle_behavior": "omit gaps; never invent OHLC",
            "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        },
        "comparison_metrics": [
            "matched_candle_count",
            "missing_candle_percentage",
            "bid_close_difference",
            "ask_close_difference",
            "mid_price_difference",
            "spread_difference",
            "median_absolute_difference",
            "p95_absolute_difference",
            "p99_absolute_difference",
            "maximum_absolute_difference",
            "session_wise_differences",
            "dst_related_differences",
        ],
        "pass_criteria_frozen_before_test": {
            "note": "Declare before running genuine parity; do not loosen post-hoc.",
            "min_matched_coverage_of_reference": 0.95,
            "median_abs_mid_close_usd": 0.50,
            "p95_abs_mid_close_usd": 2.00,
            "max_abs_mid_close_usd": 5.00,
            "median_abs_spread_usd": 0.20,
            "point_size": POINT_SIZE,
        },
        "approved_mt5_dataset": mt5,
        "phase33_parity_result": "NOT_RUN",
        "parity_pass": False,
        "limitations": [
            "No MT5 terminal connection in Phase 33.",
            "Approved MT5 feature file lacks separate bid/ask OHLC columns.",
            "Comparing Dukascopy mid to MT5 close is a source-data diagnostic, not full bid/ask parity.",
            "Do not report MT5_PARITY_PASS without comparable bid/ask observations from both sources.",
        ],
    }
    write_json("mt5_parity_protocol.json", protocol)
    return protocol
