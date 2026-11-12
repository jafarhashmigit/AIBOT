"""Planned shadow Entry/TP/SL from frozen Phase 18 barrier multiples."""

from __future__ import annotations

from typing import Any

from phase18.barrier import floored_spread_usd
from phase18.constants import EXTRA_COST_PER_SIDE, SL_ATR_MULTIPLE, TP_ATR_MULTIPLE


def planned_shadow_levels(
    *,
    side: str,
    reference_price: float,
    atr: float,
    spread_points: float | int | None = None,
) -> dict[str, Any]:
    """Mirror Phase 18 barrier distances using signal close as entry reference.

    Actual fills still occur at next-bar open during outcome evaluation.
    Distances: TP=1.5×ATR, SL=1.0×ATR; spread floor + per-side costs unchanged.
    """
    action = str(side).upper()
    if action not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if not (atr and atr > 0):
        raise ValueError("atr must be positive")
    spread = floored_spread_usd(spread_points)
    tp_dist = TP_ATR_MULTIPLE * float(atr)
    sl_dist = SL_ATR_MULTIPLE * float(atr)
    ref = float(reference_price)
    if action == "BUY":
        entry = ref + spread + EXTRA_COST_PER_SIDE
        tp = entry + tp_dist
        sl = entry - sl_dist
    else:
        entry = ref - EXTRA_COST_PER_SIDE
        tp = entry - tp_dist
        sl = entry + sl_dist
    return {
        "entry": entry,
        "tp_level": tp,
        "sl_level": sl,
        "atr": float(atr),
        "spread_usd": spread,
        "tp_atr_multiple": TP_ATR_MULTIPLE,
        "sl_atr_multiple": SL_ATR_MULTIPLE,
        "reference_price": ref,
        "note": "Planned shadow levels from frozen Phase 18 multiples; fill = next open at outcome time.",
    }


def format_price(value: float) -> str:
    return f"${value:,.2f}"
