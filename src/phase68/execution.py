"""Execution realism — MetaQuotes archive ≠ Exness; unknown costs stay unknown."""

from __future__ import annotations

from typing import Any

from phase68.constants import canonical_json_sha256
from phase68.displacement import _mean, _pct


def execution_realism(bundle: dict[str, Any], live_spreads: list[float] | None = None) -> dict[str, Any]:
    events = bundle["events"]
    # Gross close-to-close moves at h12 (direction-adjusted) — NOT executable fills
    gross = []
    for e in events:
        o = e["outcomes"].get(12) or {}
        if o.get("ok") and o.get("end_return") is not None:
            gross.append(abs(float(o["end_return"])))

    live_spreads = live_spreads or []
    # Archive M5 has spread points field sometimes — not Exness executable
    assumed_spreads = [0.1, 0.25, 0.5, 1.0, 2.0]  # price units — LABELED ASSUMPTIONS only

    be = []
    mean_gross = _mean(gross)
    for s in assumed_spreads:
        be.append(
            {
                "assumed_roundtrip_spread_price_units": s,
                "label": "ASSUMPTION_NOT_MEASURED_EXNESS_COST",
                "mean_abs_gross_h12": mean_gross,
                "fraction_events_gross_exceeds_assumed_spread": (
                    _mean([1.0 if g > s else 0.0 for g in gross]) if gross else None
                ),
                "commission": "UNKNOWN",
                "swap": "UNKNOWN_FOR_EXECUTION",
                "slippage": "UNKNOWN",
            }
        )

    out = {
        "historical_symbol": "XAUUSD",
        "historical_broker": "MetaQuotes-Demo",
        "live_symbol": "XAUUSDm",
        "live_broker": "Exness",
        "exact_historical_executable_returns_claimed": False,
        "reason": (
            "Archive outcomes use OHLC/close path proxies without contemporaneous Exness bid/ask fills. "
            "Cannot claim exact executable P&L."
        ),
        "gross_price_movement_h12_abs": {
            "n": len(gross),
            "mean": mean_gross,
            "p50": _pct(gross, 0.5),
            "p90": _pct(gross, 0.9),
        },
        "available_spread_evidence": {
            "archive": "tick bid/ask exist on many archive days but not used here as Exness costs; M5.spread is points field",
            "live_exness_quote_spreads_n": len(live_spreads),
            "live_exness_mean_spread": _mean(live_spreads) if live_spreads else None,
            "live_exness_median_spread": _pct(live_spreads, 0.5) if live_spreads else None,
        },
        "cost_sensitivity_scenarios": be,
        "break_even_note": (
            "Break-even vs assumed spread only; UNKNOWN commission/swap/slippage excluded "
            "(not set to zero). Real break-even is higher once unknowns are stressed."
        ),
        "unknown_costs_zeroed": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
