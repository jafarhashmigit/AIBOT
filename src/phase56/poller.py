"""Bounded autonomous polling engine — explicit CLI only, never auto-start."""

from __future__ import annotations

import time
from typing import Any

from phase56.constants import DEFAULT_POLL
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.provider import HistoricalReplayProvider, MarketDataProvider
from phase56.shutdown import graceful_shutdown


class BoundedPoller:
    def __init__(
        self,
        engine: IntegratedLifecycleEngine,
        provider: MarketDataProvider,
        *,
        config: dict[str, Any] | None = None,
    ):
        self.engine = engine
        self.provider = provider
        self.config = {**DEFAULT_POLL, **(config or {})}
        self.stopped = False
        self.stop_reason = None
        self.results: list[dict[str, Any]] = []

    def request_stop(self, reason: str = "SIGNAL") -> None:
        self.stopped = True
        self.stop_reason = reason

    def run(self) -> dict[str, Any]:
        assert self.config.get("auto_start") is not True
        t0 = time.monotonic()
        iterations = 0
        candles = 0
        max_iter = int(self.config["max_iterations"])
        max_wall = float(self.config["max_wall_seconds"])
        max_candles = int(self.config["max_candles"])
        interval = float(self.config["poll_interval_seconds"])
        ck_every = int(self.config["checkpoint_every"])

        for ctx in self.provider.candles():
            if self.stopped:
                self.stop_reason = self.stop_reason or "REQUESTED_STOP"
                break
            if iterations >= max_iter:
                self.stop_reason = "max_iterations"
                break
            if time.monotonic() - t0 >= max_wall:
                self.stop_reason = "max_wall_seconds"
                break
            if candles >= max_candles:
                self.stop_reason = "max_candles"
                break

            iterations += 1
            candles += 1
            rec = self.engine.process_bar(
                day=ctx["day"],
                m5=ctx["m5"],
                h1=ctx["h1"],
                ticks_by_bar=ctx["ticks_by_bar"],
                idx=ctx["idx"],
                require_new_candle=True,
            )
            self.results.append(
                {
                    "day": ctx["day"],
                    "idx": ctx["idx"],
                    "skipped": rec.get("skipped"),
                    "rejected": rec.get("rejected"),
                    "action": (rec.get("decision") or {}).get("action"),
                    "exit": (rec.get("closed") or {}).get("exit_reason"),
                    "monitored": len(rec.get("monitored_closes") or []),
                }
            )
            if iterations % ck_every == 0:
                self.engine.persist()
            if interval > 0:
                time.sleep(interval)

        shutdown = graceful_shutdown(self.engine, reason=self.stop_reason or "COMPLETED")
        return {
            "iterations": iterations,
            "candles": candles,
            "stop_reason": self.stop_reason or "COMPLETED",
            "duration_s": time.monotonic() - t0,
            "sample_results": self.results[:30],
            "n_results": len(self.results),
            "metrics": dict(self.engine.metrics),
            "shutdown": {"ok": shutdown["ok"], "checkpoint": shutdown["path"]},
            "provenance": getattr(self.provider, "provenance", {}),
            "live_mt5": False,
            "streaming": False,
            "auto_started": False,
        }
