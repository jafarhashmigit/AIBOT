from phase8.experience_schema import DecisionTimeFields, ExperienceRecord, OutcomeFields


def decision(ts: str, action: str = "WAIT", fold: str = "WF1") -> DecisionTimeFields:
    third = 1.0 / 3.0
    return DecisionTimeFields(
        experience_id=f"{ts}_XAUUSD_M5",
        timestamp=ts,
        fold_id=fold,
        action=action,
        raw_decision=action,
        final_decision=action,
        model_id="phase2_rf_oos",
        expected_buy_r=0.0,
        expected_sell_r=0.0,
        p_tp_buy=third, p_sl_buy=third, p_time_buy=third,
        p_tp_sell=third, p_sl_sell=third, p_time_sell=third,
        uncertainty_buy=0.0,
        uncertainty_sell=0.0,
        estimated_cost=0.25,
    )


def record(ts: str, outcome_end: str, action: str = "WAIT", r=None) -> ExperienceRecord:
    return ExperienceRecord(
        decision_time_fields=decision(ts, action),
        outcome_fields=OutcomeFields(
            outcome_end=outcome_end,
            selected_exit_reason="" if action == "WAIT" else "TP",
            selected_realized_r=r,
            selected_realized_pnl=None,
            hypothetical_buy_net_r=-1.0,
            hypothetical_sell_net_r=1.5,
            hypothetical_buy_exit_reason="SL",
            hypothetical_sell_exit_reason="TP",
        ),
    )
