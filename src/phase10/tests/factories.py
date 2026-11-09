"""Synthetic fixtures. No holdout. No invented live market data."""

from __future__ import annotations

from phase10.constants import SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_schema import HistoricalDecisionFields, HistoricalExperience, HistoricalOutcomeFields
from phase10.paper_schema import EntryReference, PaperDecision
from phase10.validation import historical_id, paper_decision_id


def hist_exp(
    ts: str = "2026-06-19 10:00:00",
    side: str = "BUY",
    *,
    outcome_end: str = "2026-06-19 11:00:00",
    net_r: float = 0.5,
) -> HistoricalExperience:
    decision = HistoricalDecisionFields(
        experience_id=historical_id(ts, side),
        source_type=SOURCE_HISTORICAL,
        decision_timestamp=ts,
        side=side,
        fold_id="WF1",
        model_id="phase2_rf_oos",
        p_tp_rf=0.4,
        p_sl_rf=0.3,
        p_time_rf=0.3,
        pred_r_rf=0.1,
        pred_r_ridge=0.05,
        provenance="synthetic_fixture",
        hypothetical_entry_reference=None,
    )
    outcome = HistoricalOutcomeFields(
        outcome_end=outcome_end,
        exit_reason="TP",
        actual_net_r=net_r,
        realized_pnl=net_r * 2.0,
        outcome_status="completed",
    )
    return HistoricalExperience(decision, outcome)


def paper_decision(
    ts: str = "2026-06-19 10:00:00",
    *,
    raw: str = "WAIT",
    final: str = "WAIT",
    gate: str = "ALLOW",
) -> PaperDecision:
    return PaperDecision(
        decision_id=paper_decision_id(ts),
        source_type=SOURCE_PAPER,
        decision_timestamp=ts,
        market_symbol="XAUUSD",
        timeframe="M5",
        model_id="fixture",
        expected_buy_r=0.1,
        expected_sell_r=-0.1,
        uncertainty_buy=0.0,
        uncertainty_sell=0.0,
        raw_proposed_action=raw,
        risk_gate_result=gate,
        final_action=final,
        decision_status="fixture",
        provenance="synthetic_fixture",
    )


def entry(ts: str = "2026-06-19 10:00:00", price: float = 2300.0) -> EntryReference:
    return EntryReference(
        timestamp=ts,
        price=price,
        stop_loss=2290.0,
        take_profit=2320.0,
        provenance="synthetic_fixture",
    )
