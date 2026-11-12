"""Bounded autonomous replay stress — restarts, duplicates, provider interruption."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.archive_loader import list_archived_m5_days
from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.poller import BoundedPoller
from phase56.provider import HistoricalReplayProvider
from phase56.shutdown import graceful_shutdown
from phase57.adapter import make_engine
from phase57.constants import ARCHIVE_ROOT
from phase57.fixtures import clean_bundle, conflicting_duplicate_bar


class InterruptibleProvider:
    """Wraps historical provider; stops after N yields to simulate interruption."""

    def __init__(self, inner: HistoricalReplayProvider, stop_after: int):
        self.inner = inner
        self.stop_after = stop_after
        self.provenance = getattr(inner, "provenance", {})

    def candles(self):
        n = 0
        for ctx in self.inner.candles():
            if n >= self.stop_after:
                return
            n += 1
            yield ctx


def run_stress(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    days = list_archived_m5_days(ARCHIVE_ROOT)[:2]
    evidence = {}

    # 1) Multi-restart NullPolicy replay
    state = work_dir / "stress_state.json"
    reg = work_dir / "stress_candles.json"
    hist = work_dir / "hist"
    shadow = work_dir / "shadow"
    eng = make_engine(
        state_path=state,
        registry_path=reg,
        policy=NullPolicy(),
        record_counterfactuals=False,
        hist_root=hist,
        shadow_root=shadow,
    )
    p1 = InterruptibleProvider(HistoricalReplayProvider(days=days, stride=12, max_candles=40), stop_after=8)
    m1 = BoundedPoller(eng, p1, config={"max_candles": 8, "max_iterations": 50, "max_wall_seconds": 60}).run()
    keys1 = list(eng.state.data.get("processed_decision_keys") or [])
    eng2 = make_engine(
        state_path=state,
        registry_path=reg,
        policy=NullPolicy(),
        record_counterfactuals=False,
        hist_root=hist,
        shadow_root=shadow,
    )
    p2 = HistoricalReplayProvider(days=days, stride=12, max_candles=20)
    # Continue — duplicates should skip via candle registry / processed keys
    m2 = BoundedPoller(
        eng2, p2, config={"max_candles": 20, "max_iterations": 100, "max_wall_seconds": 90}
    ).run()
    keys2 = list(eng2.state.data.get("processed_decision_keys") or [])
    evidence["multi_restart"] = {
        "first_candles": m1.get("candles"),
        "second_candles": m2.get("candles"),
        "keys_first": len(keys1),
        "keys_after": len(keys2),
        "keys_grew_or_stable": len(keys2) >= len(keys1),
        "no_dup_keys": len(keys2) == len(set(keys2)),
        "ok": len(keys2) == len(set(keys2)) and len(keys2) >= len(keys1),
    }

    # 2) Duplicate + conflicting observations under EngineeringTestPolicy sequence
    day, m5, h1, by = clean_bundle(day="2099-09-01", move_after_entry=-5.0)
    e = make_engine(
        state_path=work_dir / "dup_s.json",
        registry_path=work_dir / "dup_c.json",
        policy=EngineeringTestPolicy(["BUY", "WAIT", "WAIT"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        immediate_monitor_through_horizon=True,
        hist_root=work_dir / "dup_h",
        shadow_root=work_dir / "dup_sh",
    )
    r1 = e.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48, require_new_candle=True)
    r_dup = e.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48, require_new_candle=True)
    # conflicting hash on same ts via registry directly
    bar = m5[48]
    conf = conflicting_duplicate_bar(bar)
    gate = e.observer.registry.evaluate(conf, policy_version=e.observer.policy_version)
    evidence["duplicates"] = {
        "first_action": (r1.get("decision") or {}).get("action"),
        "second_skipped_or_rejected": bool(r_dup.get("skipped") or r_dup.get("rejected")),
        "conflict_reason": gate.get("reason"),
        "ok": bool(r_dup.get("skipped") or r_dup.get("rejected"))
        and gate.get("reason") == "CONFLICTING_DUPLICATE_HASH",
    }

    # 3) Long open/close sequence
    e3 = make_engine(
        state_path=work_dir / "seq.json",
        registry_path=work_dir / "seq_c.json",
        policy=EngineeringTestPolicy(["BUY", "SELL", "WAIT", "BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5, "max_simultaneous_positions": 1}),
        immediate_monitor_through_horizon=True,
        record_counterfactuals=True,
        hist_root=work_dir / "seq_h",
        shadow_root=work_dir / "seq_sh",
    )
    actions = []
    for i, idx in enumerate([48, 60, 72, 84]):
        day_i = f"2099-09-0{2+i}"
        d, m, h, b = clean_bundle(day=day_i, move_after_entry=-5.0 if i % 2 == 0 else 5.0)
        rr = e3.process_bar(day=d, m5=m, h1=h, ticks_by_bar=b, idx=48, require_new_candle=False)
        actions.append((rr.get("decision") or {}).get("action"))
    evidence["sequence"] = {
        "actions": actions,
        "closed_ids": list(e3.state.data.get("closed_position_ids") or []),
        "open_n": len(e3.risk.open_positions),
        "shadow_n": e3.shadow.n,
        "hist_n": e3.hist.n,
        "ok": len(e3.state.data.get("closed_position_ids") or []) == len(set(e3.state.data.get("closed_position_ids") or [])),
    }

    # 4) Deterministic replay comparison (two fresh engines, same inputs)
    d, m, h, b = clean_bundle(day="2099-09-20", move_after_entry=-5.0)
    outs = []
    for name in ("A", "B"):
        ex = make_engine(
            state_path=work_dir / f"det_{name}.json",
            registry_path=work_dir / f"det_{name}_c.json",
            policy=EngineeringTestPolicy(["BUY"]),
            risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
            immediate_monitor_through_horizon=True,
            hist_root=work_dir / f"det_{name}_h",
            shadow_root=work_dir / f"det_{name}_sh",
        )
        rr = ex.process_bar(day=d, m5=m, h1=h, ticks_by_bar=b, idx=48)
        c = rr.get("closed") or {}
        outs.append(
            {
                "action": (rr.get("decision") or {}).get("action"),
                "exit_reason": c.get("exit_reason"),
                "entry_fill": c.get("entry_fill"),
                "exit_fill": c.get("exit_fill"),
                "net_r": c.get("net_r"),
            }
        )
    evidence["deterministic"] = {
        "a": outs[0],
        "b": outs[1],
        "ok": outs[0] == outs[1],
    }

    ok = all(v.get("ok") for v in evidence.values())
    return {"ok": ok, "evidence": evidence}
