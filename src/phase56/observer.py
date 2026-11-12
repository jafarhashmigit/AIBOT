"""Unified market observer — wraps Phase54/49 feature path; no feature duplication."""

from __future__ import annotations

from typing import Any

from phase54.observer import build_observation, validate_bar, validate_tick_path
from phase54.timeutil import dual_stamp, now_utc_iso
from phase56.candle_registry import CandleRegistry, candle_hash


class MarketObserver:
    def __init__(self, *, policy_version: str, registry: CandleRegistry | None = None):
        self.policy_version = policy_version
        self.registry = registry or CandleRegistry()
        self.last_success: dict[str, Any] | None = None

    def observe(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        idx: int,
        h1: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
        require_new_candle: bool = True,
    ) -> dict[str, Any]:
        if idx < 0 or idx >= len(m5):
            return {
                "accepted": False,
                "reason_codes": ["INDEX_OOB"],
                "created_iso": now_utc_iso(),
            }
        bar = m5[idx]
        ts = str(bar["timestamp_utc"])
        errs = validate_bar(bar)
        if errs:
            self.registry.reject("INVALID_OHLC", ts, {"errors": errs})
            return {
                "accepted": False,
                "reason_codes": ["INVALID_OHLC"] + errs,
                "bar_timestamp_utc": ts,
                "timestamps": dual_stamp(ts),
                "candle_hash": candle_hash(bar),
            }

        if require_new_candle:
            gate = self.registry.evaluate(bar, policy_version=self.policy_version)
            if not gate["accept"]:
                self.registry.reject(gate["reason"], ts, gate)
                return {
                    "accepted": False,
                    "reason_codes": [gate["reason"]],
                    "bar_timestamp_utc": ts,
                    "timestamps": dual_stamp(ts),
                    "candle_hash": gate.get("hash"),
                    "candle_gate": gate,
                }

        # Incomplete candle: require bid/ask ticks on decision bar
        tick_errs = validate_tick_path(ticks_by_bar, ts)
        if tick_errs:
            self.registry.reject("INCOMPLETE_OR_INVALID_BIDASK", ts, {"errors": tick_errs})
            return {
                "accepted": False,
                "reason_codes": ["INCOMPLETE_OR_INVALID_BIDASK"] + tick_errs,
                "bar_timestamp_utc": ts,
                "timestamps": dual_stamp(ts),
                "candle_hash": candle_hash(bar),
            }

        obs = build_observation(m5=m5, idx=idx, h1=h1, ticks_by_bar=ticks_by_bar, day=day)
        if not obs.get("accepted"):
            self.registry.reject("OBSERVER_REJECTED", ts, {"errors": obs.get("errors")})
            return {**obs, "reason_codes": ["OBSERVER_REJECTED"] + list(obs.get("errors") or [])}

        obs["candle_hash"] = candle_hash(bar)
        obs["policy_version"] = self.policy_version
        obs["reason_codes"] = ["OK"]
        self.last_success = {
            "timestamp_utc": ts,
            "hash": obs["candle_hash"],
            "day": day,
            "idx": idx,
            "iso": now_utc_iso(),
            "stamps": dual_stamp(ts),
        }
        return obs

    def commit_candle(self, bar: dict[str, Any]) -> None:
        self.registry.commit(bar, policy_version=self.policy_version)
