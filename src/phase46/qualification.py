"""Phase46 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    contract_ok: bool,
    independent_ok: bool,
    data_gate_ok: bool,
    n_ok_buy: int,
    n_ok_sell: int,
    n_wait: int,
    scenarios_present: bool,
    mid_price_used: bool,
) -> tuple[str, str]:
    if not contract_ok:
        return "RESEARCH_CONTRACT_FAILURE", "Research contract missing or hash inconsistent."
    if mid_price_used:
        return "DATA_INTEGRITY_FAILURE", "Mid-price fills detected — forbidden."
    if not data_gate_ok:
        return "DATA_INTEGRITY_FAILURE", "Forbidden validation/holdout date access detected."
    if not independent_ok:
        return "DATA_INTEGRITY_FAILURE", "Independent recomputation mismatched primary outcomes."
    if n_ok_buy < 10 or n_ok_sell < 10 or n_wait < 10:
        return (
            "PARTIAL_COSTED_EV_FOUNDATION",
            f"Outcome architecture present but thin sample (buy={n_ok_buy}, sell={n_ok_sell}, wait={n_wait}).",
        )
    if not scenarios_present:
        return "EXECUTION_MODEL_INSUFFICIENT", "Cost scenario registry incomplete."
    return (
        "COSTED_EV_FOUNDATION_READY",
        (
            "BUY/SELL/WAIT outcomes defined with bid/ask fills, gross/net separation, "
            "explicit unknown costs, exposure accounting, and independent verification. "
            "No profitability claim."
        ),
    )
