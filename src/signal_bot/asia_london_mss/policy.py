"""Phase54-compatible policy wrapper — never submits broker orders."""

from __future__ import annotations

from typing import Any

from signal_bot.asia_london_mss.constants import HYPOTHESIS_ID, POLICY_VERSION, SYMBOL
from signal_bot.asia_london_mss.engine import evaluate_at


class AsiaLondonMssPolicy:
    """Isolated experimental policy. Champion remains NO_MODEL until gates pass."""

    version = POLICY_VERSION
    hypothesis_id = HYPOTHESIS_ID

    def propose(
        self,
        market_state: dict[str, Any],
        features: dict[str, Any],
        model_output: dict[str, Any] | None,
        risk_state: dict[str, Any],
    ) -> dict[str, Any]:
        if market_state.get("forming_bar") is True:
            return {
                "action": "WAIT",
                "calibrated": False,
                "expected_net_r": None,
                "prob_positive": None,
                "confidence": None,
                "uncertainty": 1.0,
                "reason_codes": ["FORMING_BAR_REJECTED"],
            }
        if str(market_state.get("data_quality_status") or "OK") not in {"OK", "ACCEPTED"}:
            return {
                "action": "WAIT",
                "calibrated": False,
                "expected_net_r": None,
                "prob_positive": None,
                "confidence": None,
                "uncertainty": 1.0,
                "reason_codes": ["DATA_QUALITY_WAIT", str(market_state.get("data_quality_status"))],
            }

        bars = market_state.get("bars") or market_state.get("m5") or []
        if not bars:
            return {
                "action": "WAIT",
                "calibrated": False,
                "expected_net_r": None,
                "prob_positive": None,
                "confidence": None,
                "uncertainty": 1.0,
                "reason_codes": ["BARS_MISSING"],
            }

        idx = market_state.get("decision_idx")
        if idx is None:
            idx = len(bars) - 1
        idx = int(idx)
        symbol = str(market_state.get("symbol") or SYMBOL)
        out = evaluate_at(bars, idx, forming_bar=False, symbol=symbol)

        return {
            "action": out.get("action") or "WAIT",
            "expected_net_r": None,  # never fabricate EV
            "prob_positive": None,
            "calibrated": False,
            "confidence": out.get("confidence"),
            "uncertainty": out.get("uncertainty", 1.0),
            "reason_codes": list(out.get("reason_codes") or []),
            "setup_id": out.get("setup_id"),
            "entry_reference": out.get("entry_reference"),
            "stop_loss": out.get("stop_loss"),
            "take_profit": out.get("take_profit"),
            "reward_risk": out.get("reward_risk"),
            "signal_expiry_utc": out.get("signal_expiry_utc"),
            "signal_expiry_bars": out.get("signal_expiry_bars"),
            "max_hold_bars": out.get("max_hold_bars"),
            "invalidation": out.get("invalidation"),
            "hypothesis_id": HYPOTHESIS_ID,
            "policy_version": POLICY_VERSION,
            "asia_range": out.get("asia_range"),
            "sweep": out.get("sweep"),
            "mss": out.get("mss"),
            "authorizes_execution": False,
            "order_send": "PROHIBITED",
        }
