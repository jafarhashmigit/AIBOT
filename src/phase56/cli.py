"""Explicit CLI entry — never auto-start."""

from __future__ import annotations

import argparse
from pathlib import Path

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase56.constants import DEFAULT_POLL, STATE_DIR
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.poller import BoundedPoller
from phase56.provider import HistoricalReplayProvider
from phase56.health import build_health_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase56 bounded historical-replay agent (explicit start only)")
    p.add_argument("--max-candles", type=int, default=DEFAULT_POLL["max_candles"])
    p.add_argument("--max-iterations", type=int, default=DEFAULT_POLL["max_iterations"])
    p.add_argument("--max-wall-seconds", type=float, default=DEFAULT_POLL["max_wall_seconds"])
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--state", type=str, default=str(STATE_DIR / "agent_state.json"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state = AgentState(path=Path(args.state))
    engine = IntegratedLifecycleEngine(
        state=state,
        risk=RiskManager(),
        policy=NullPolicy(),
        immediate_monitor_through_horizon=False,
    )
    provider = HistoricalReplayProvider(stride=args.stride, max_candles=args.max_candles)
    poller = BoundedPoller(
        engine,
        provider,
        config={
            "max_candles": args.max_candles,
            "max_iterations": args.max_iterations,
            "max_wall_seconds": args.max_wall_seconds,
        },
    )
    meta = poller.run()
    build_health_report(engine, meta)
    print({"stop_reason": meta["stop_reason"], "candles": meta["candles"], "metrics": meta["metrics"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
