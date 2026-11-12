"""Centralized paper risk manager — configurable limits; never invents edge."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from phase54.constants import DEFAULT_RISK


class RiskManager:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = {**DEFAULT_RISK, **(config or {})}
        self._validate_config()
        self.daily_realized_r: dict[str, float] = {}
        self.peak_equity_r = 0.0
        self.equity_r = 0.0
        self.open_positions: dict[str, dict[str, Any]] = {}
        self.error_streak = 0
        self.circuit_open = False
        self.safety_state = "NORMAL"

    def _validate_config(self) -> None:
        for k, v in self.config.items():
            if isinstance(v, (int, float)) and float(v) < 0:
                raise ValueError(f"risk config {k} must be >= 0")
        if int(self.config["max_simultaneous_positions"]) < 1:
            raise ValueError("max_simultaneous_positions must be >= 1")

    def snapshot(self) -> dict[str, Any]:
        return {
            "config": deepcopy(self.config),
            "daily_realized_r": dict(self.daily_realized_r),
            "peak_equity_r": self.peak_equity_r,
            "equity_r": self.equity_r,
            "n_open": len(self.open_positions),
            "open_ids": sorted(self.open_positions),
            "error_streak": self.error_streak,
            "circuit_open": self.circuit_open,
            "safety_state": self.safety_state,
        }

    def load_snapshot(self, snap: dict[str, Any]) -> None:
        self.daily_realized_r = dict(snap.get("daily_realized_r") or {})
        self.peak_equity_r = float(snap.get("peak_equity_r") or 0)
        self.equity_r = float(snap.get("equity_r") or 0)
        self.error_streak = int(snap.get("error_streak") or 0)
        self.circuit_open = bool(snap.get("circuit_open"))
        self.safety_state = str(snap.get("safety_state") or "NORMAL")
        # open_positions restored by lifecycle

    def register_open(self, position_id: str, rec: dict[str, Any]) -> None:
        self.open_positions[position_id] = rec

    def register_close(self, position_id: str, realized_r: float, day: str) -> None:
        self.open_positions.pop(position_id, None)
        self.daily_realized_r[day] = self.daily_realized_r.get(day, 0.0) + float(realized_r)
        self.equity_r += float(realized_r)
        self.peak_equity_r = max(self.peak_equity_r, self.equity_r)

    def note_error(self) -> None:
        self.error_streak += 1
        if self.error_streak >= int(self.config["circuit_breaker_errors"]):
            self.circuit_open = True
            self.safety_state = "CIRCUIT_BREAKER_WAIT"

    def note_success(self) -> None:
        self.error_streak = 0

    def position_size(self, *, atr: float | None, equity_units: float = 1.0) -> dict[str, Any]:
        """Size from risk-per-trade and stop distance (ATR multiple). Not a profitability claim."""
        if atr is None or atr <= 0:
            return {"ok": False, "reason": "invalid_atr", "units": 0.0, "stop_distance": None}
        stop = float(atr) * float(self.config["stop_atr_multiple"])
        if stop <= 0:
            return {"ok": False, "reason": "invalid_stop", "units": 0.0, "stop_distance": stop}
        risk_budget = float(self.config["max_risk_per_trade_r"]) * float(equity_units)
        units = risk_budget / stop
        return {"ok": True, "reason": "ok", "units": units, "stop_distance": stop, "risk_budget_r": risk_budget}

    def evaluate(self, decision: dict[str, Any], market_state: dict[str, Any]) -> dict[str, Any]:
        """May convert BUY/SELL → WAIT. Never creates a directional signal from WAIT."""
        action = decision.get("proposed_action") or decision.get("action") or "WAIT"
        reasons: list[str] = []
        allowed = True

        if self.circuit_open or self.safety_state == "CIRCUIT_BREAKER_WAIT":
            allowed = False
            reasons.append("circuit_breaker")

        if action == "WAIT":
            return {
                "allowed": True,
                "final_action": "WAIT",
                "reasons": reasons or ["raw_wait"],
                "sizing": None,
                "safety_state": self.safety_state,
            }

        day = str(market_state.get("day") or "")[:10]
        daily = self.daily_realized_r.get(day, 0.0)
        if daily <= -float(self.config["max_daily_loss_r"]):
            allowed = False
            reasons.append("max_daily_loss")

        dd = self.peak_equity_r - self.equity_r
        if dd >= float(self.config["max_drawdown_r"]):
            allowed = False
            reasons.append("max_drawdown")

        if len(self.open_positions) >= int(self.config["max_simultaneous_positions"]):
            allowed = False
            reasons.append("max_simultaneous_positions")

        # Duplicate protection: same market_state_id already open
        msid = market_state.get("market_state_id")
        for p in self.open_positions.values():
            if p.get("market_state_id") == msid:
                allowed = False
                reasons.append("duplicate_position")
                break
            if p.get("side") == action and p.get("symbol") == market_state.get("symbol"):
                allowed = False
                reasons.append("duplicate_side_exposure")
                break

        spread = market_state.get("spread")
        atr = market_state.get("atr")
        if spread is not None and float(spread) > float(self.config["max_spread_price"]):
            allowed = False
            reasons.append("max_spread_price")
        if atr and spread is not None and atr > 0:
            if float(spread) / float(atr) > float(self.config["max_spread_atr"]):
                allowed = False
                reasons.append("max_spread_atr")

        sizing = self.position_size(atr=atr)
        if not sizing.get("ok"):
            allowed = False
            reasons.append(sizing.get("reason") or "invalid_stop")

        if not allowed:
            self.safety_state = "WAIT_FORCED"
            return {
                "allowed": False,
                "final_action": "WAIT",
                "reasons": reasons,
                "sizing": sizing,
                "safety_state": self.safety_state,
            }

        self.safety_state = "NORMAL"
        return {
            "allowed": True,
            "final_action": action,
            "reasons": ["risk_ok"],
            "sizing": sizing,
            "safety_state": self.safety_state,
        }
