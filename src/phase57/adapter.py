"""Adapters wrapping Phase56 without modifying it — isolated Phase57 roots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase56.candle_registry import CandleRegistry
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.observer import MarketObserver
from phase57.constants import CHECKPOINT_DIR, HIST_DIR, SHADOW_DIR, STATE_DIR


def make_engine(
    *,
    state_path: Path | None = None,
    registry_path: Path | None = None,
    policy=None,
    risk: RiskManager | None = None,
    record_counterfactuals: bool = True,
    immediate_monitor_through_horizon: bool = True,
    max_spread_atr: float = 2.0,
    hist_root: Path | None = None,
    shadow_root: Path | None = None,
) -> IntegratedLifecycleEngine:
    """Construct IntegratedLifecycleEngine with Phase57-isolated stores/state."""
    sp = state_path or (STATE_DIR / "agent_state.json")
    rp = registry_path or (STATE_DIR / "candle_registry.json")
    sp.parent.mkdir(parents=True, exist_ok=True)
    hr = hist_root or HIST_DIR
    sr = shadow_root or SHADOW_DIR
    hr.mkdir(parents=True, exist_ok=True)
    sr.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    pol = policy if policy is not None else NullPolicy()
    eng = IntegratedLifecycleEngine(
        state=AgentState(path=sp),
        risk=risk or RiskManager({"max_spread_atr": max_spread_atr}),
        policy=pol,
        record_counterfactuals=record_counterfactuals,
        immediate_monitor_through_horizon=immediate_monitor_through_horizon,
        use_phase56_stores=True,  # temporarily; replaced below
    )
    # Isolate experience from Phase54/56 production roots
    eng.hist = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=hr)
    eng.shadow = ExperienceStore("AGENT_SHADOW", root=sr)
    eng.observer = MarketObserver(
        policy_version=str(getattr(pol, "version", "unknown")),
        registry=CandleRegistry(path=rp),
    )
    return eng


def reset_phase57_data() -> None:
    import shutil

    for d in (STATE_DIR, HIST_DIR, SHADOW_DIR, CHECKPOINT_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
