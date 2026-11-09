"""Tiny synthetic OOS-like pairs. Not trading evidence."""


def pair(stamp: str, fold: str = "WF1", buy_r: float = 0.1, sell_r: float = -0.1) -> dict:
    third = 1.0 / 3.0
    side = lambda r, tag: {
        "p_tp_rf": third, "p_sl_rf": third, "p_time_rf": third,
        "pred_r_rf": r, "pred_r_ridge": r, "pred_r_const": -0.05,
        "primary_clf_model_id": f"rfclf_{tag}_{fold}",
        "primary_reg_model_id": f"rfreg_{tag}_{fold}",
    }
    return {
        "timestamp": stamp,
        "fold_id": fold,
        "training_period_end": "2026-05-01 00:00:00",
        "feature_version": "m5_utc_corrected_allowlist_v1",
        "prediction_generated_at_utc": "2026-11-09T00:00:00Z",
        "buy": side(buy_r, "BUY"),
        "sell": side(sell_r, "SELL"),
    }


def ev(stamp: str, fold: str = "WF1", buy_r: float = -1.0, sell_r: float = 1.5) -> dict:
    return {
        "timestamp": stamp,
        "fold_id": fold,
        "actual_exit_reason_BUY": "SL",
        "actual_net_r_BUY": buy_r,
        "actual_net_pnl_BUY": -2.0,
        "actual_exit_reason_SELL": "TP",
        "actual_net_r_SELL": sell_r,
        "actual_net_pnl_SELL": 3.0,
    }
