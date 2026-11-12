"""Isolated verification harness — reuses Phase54 primitives; Phase55 test stores only."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from phase54.archive_loader import load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase54.constants import HORIZON_BARS
from phase54.decision import NullPolicy, decide
from phase54.observer import build_observation
from phase54.paper_exec import (
    PaperExecutionError,
    force_horizon_exit_from_bars,
    monitor_and_maybe_exit,
    open_paper_position,
)
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase55.constants import ARCHIVE_ROOT, ENGINEERING_TAG, STATE_DIR
from phase55.engineering_policy import EngineeringTestPolicy
from phase55.independent import compare_to_engine, recompute_path
from phase55.stores import (
    assert_not_production_path,
    record_test_shadow,
    test_historical_store,
    test_shadow_store,
)


class VerificationHarness:
    def __init__(
        self,
        *,
        policy: EngineeringTestPolicy | None = None,
        risk: RiskManager | None = None,
        state_path: Path | None = None,
        defer_exit: bool = False,
    ):
        self.policy = policy or EngineeringTestPolicy(["BUY", "SELL", "WAIT"])
        if not isinstance(self.policy, EngineeringTestPolicy):
            raise TypeError("Phase55 harness requires EngineeringTestPolicy")
        self.risk = risk or RiskManager()
        self.state = AgentState(path=state_path or (STATE_DIR / "verify_state.json"))
        if self.state.data.get("risk_snapshot"):
            self.risk.load_snapshot(self.state.data["risk_snapshot"])
        for pid, prec in (self.state.data.get("open_positions") or {}).items():
            self.risk.register_open(pid, prec)
        self.shadow = test_shadow_store()
        self.hist = test_historical_store()
        assert_not_production_path(self.shadow.path)
        assert_not_production_path(self.hist.path)
        self.defer_exit = defer_exit
        self.results: list[dict[str, Any]] = []

    def persist(self) -> None:
        self.state.data["risk_snapshot"] = self.risk.snapshot()
        self.state.data["open_positions"] = dict(self.risk.open_positions)
        self.state.data[ENGINEERING_TAG] = True
        self.state.save()
        self.shadow.flush()
        self.hist.flush()

    def process_decision(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        h1: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
        idx: int,
        force_action: str | None = None,
    ) -> dict[str, Any]:
        if self.state.already_processed(day, idx):
            return {"skipped": True, "reason": "idempotent_already_processed", "day": day, "idx": idx}

        obs = build_observation(m5=m5, idx=idx, h1=h1, ticks_by_bar=ticks_by_bar, day=day)
        if not obs.get("accepted"):
            self.state.mark_processed(day, idx, obs.get("observation_id"))
            self.persist()
            return {
                "skipped": False,
                "rejected": True,
                "observation": obs,
                "reason_codes": ["INVALID_OR_STALE_OBSERVATION"] + list(obs.get("errors") or []),
            }

        if force_action:
            # Temporary one-shot sequence override without mutating shared policy mid-flight incorrectly
            pol = EngineeringTestPolicy([force_action])
        else:
            pol = self.policy

        decision = decide(obs, obs.get("features") or {}, None, self.risk.snapshot(), policy=pol)
        decision["reason_codes"] = list(decision.get("reason_codes") or []) + [ENGINEERING_TAG]
        gate = self.risk.evaluate(decision, obs)
        decision["action"] = gate["final_action"]
        decision["risk_gate"] = gate
        decision["reason_codes"] = list(decision.get("reason_codes") or []) + list(gate.get("reasons") or [])

        action = decision["action"]
        position = None
        closed = None
        indep = None
        compare = None

        if action in ("BUY", "SELL"):
            entry_idx = idx + 1
            if entry_idx >= len(m5):
                decision["action"] = "WAIT"
                decision["reason_codes"].append("incomplete_entry_path")
                action = "WAIT"
            else:
                try:
                    entry_bar = str(m5[entry_idx]["timestamp_utc"])
                    position = open_paper_position(
                        decision=decision,
                        market_state=obs,
                        entry_bar_ts=entry_bar,
                        ticks_by_bar=ticks_by_bar,
                        sizing=gate.get("sizing") or {},
                        m5=m5,
                        entry_idx=entry_idx,
                    )
                    position[ENGINEERING_TAG] = True
                    self.risk.register_open(position["position_id"], position)
                    if self.defer_exit:
                        # Leave OPEN for recovery tests
                        self.state.mark_processed(day, idx, obs.get("observation_id"))
                        self.persist()
                        rec = {
                            "skipped": False,
                            "rejected": False,
                            "observation": obs,
                            "decision": decision,
                            "position": position,
                            "closed": None,
                            "deferred": True,
                            "stages": ["OBSERVATION", "DECISION", "RISK_CHECK", "PAPER_ENTRY"],
                        }
                        self.results.append(rec)
                        return rec

                    # Monitor path first (may hit SL/TP); else horizon
                    exit_idx = entry_idx + HORIZON_BARS - 1
                    closed = monitor_and_maybe_exit(
                        position,
                        m5=m5,
                        ticks_by_bar=ticks_by_bar,
                        current_idx=exit_idx,
                        horizon_bars=HORIZON_BARS,
                    )
                    if closed is None:
                        closed = force_horizon_exit_from_bars(
                            position, m5=m5, ticks_by_bar=ticks_by_bar, horizon_bars=HORIZON_BARS
                        )
                    closed[ENGINEERING_TAG] = True
                    self.risk.register_close(closed["position_id"], float(closed.get("net_r") or 0), day)
                    closed_ids = list(self.state.data.get("closed_position_ids") or [])
                    closed_ids.append(closed["position_id"])
                    self.state.data["closed_position_ids"] = closed_ids

                    # Independent path walk (does not call paper_exec)
                    indep = recompute_path(
                        side=action,
                        m5=m5,
                        ticks_by_bar=ticks_by_bar,
                        entry_idx=entry_idx,
                        horizon_bars=HORIZON_BARS,
                        atr=obs.get("atr"),
                        stop_distance=float((gate.get("sizing") or {}).get("stop_distance") or 0),
                    )
                    compare = compare_to_engine(closed, indep)
                except PaperExecutionError as exc:
                    decision["action"] = "WAIT"
                    decision["reason_codes"].append(f"exec_fail:{exc}")
                    action = "WAIT"

        # Experience — test namespace only
        if action == "WAIT":
            record_test_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=0.0,
                outcome_timestamp_utc=obs["bar_timestamp_utc"],
            )
        elif closed is not None:
            record_test_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=float(closed.get("net_r") or 0),
                outcome_timestamp_utc=str(closed.get("exit_timestamp")),
            )

        self.state.mark_processed(day, idx, obs.get("observation_id"))
        self.persist()
        rec = {
            "skipped": False,
            "rejected": False,
            "observation": obs,
            "decision": decision,
            "position": position,
            "closed": closed,
            "independent": indep,
            "compare": compare,
            "stages": [
                "OBSERVATION",
                "DECISION",
                "RISK_CHECK",
                "PAPER_ENTRY" if position else "NO_ENTRY",
                "EXIT" if closed else ("WAIT_ONLY" if action == "WAIT" else "DEFERRED"),
                "OUTCOME",
                "EXPERIENCE",
            ],
        }
        self.results.append(rec)
        return rec

    def continue_open_to_exit(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
    ) -> list[dict[str, Any]]:
        """Complete deferred OPEN positions (restart recovery path)."""
        out = []
        opens = list(self.risk.open_positions.items())
        for pid, position in opens:
            pos = copy.deepcopy(position)
            entry_idx = int(pos["entry_idx"])
            exit_idx = entry_idx + HORIZON_BARS - 1
            closed = monitor_and_maybe_exit(
                pos, m5=m5, ticks_by_bar=ticks_by_bar, current_idx=exit_idx, horizon_bars=HORIZON_BARS
            )
            if closed is None:
                closed = force_horizon_exit_from_bars(
                    pos, m5=m5, ticks_by_bar=ticks_by_bar, horizon_bars=HORIZON_BARS
                )
            closed[ENGINEERING_TAG] = True
            self.risk.register_close(pid, float(closed.get("net_r") or 0), day)
            indep = recompute_path(
                side=closed["side"],
                m5=m5,
                ticks_by_bar=ticks_by_bar,
                entry_idx=entry_idx,
                horizon_bars=HORIZON_BARS,
                atr=closed.get("atr_at_entry"),
                stop_distance=abs(float(closed["entry_fill"]) - float(closed["stop_loss"])),
            )
            compare = compare_to_engine(closed, indep)
            # Shadow outcome for recovered close
            fake_decision = {
                "decision_id": closed.get("decision_id"),
                "timestamp_utc": closed.get("entry_timestamp"),
                "market_state_id": closed.get("market_state_id"),
                "action": closed["side"],
                "reason_codes": [ENGINEERING_TAG, "RECOVERY_EXIT"],
                "model_policy_version": self.policy.version,
            }
            record_test_shadow(
                store=self.shadow,
                decision=fake_decision,
                market_state={"regime": {}, "market_state_id": closed.get("market_state_id")},
                net_r=float(closed.get("net_r") or 0),
                outcome_timestamp_utc=str(closed.get("exit_timestamp")),
            )
            self.persist()
            out.append({"closed": closed, "independent": indep, "compare": compare, "recovered": True})
        return out


def load_day_bundle(day: str, archive_root: Path | None = None) -> dict[str, Any]:
    root = Path(archive_root or ARCHIVE_ROOT)
    m5 = load_m5(root, day)
    h1 = load_h1(root, day)
    by = ticks_by_m5_bar(load_ticks(root, day))
    return {"day": day, "m5": m5, "h1": h1, "ticks_by_bar": by, "archive_root": str(root)}


def assert_production_policy_untouched() -> dict[str, Any]:
    from phase54.lifecycle import LifecycleEngine

    eng = LifecycleEngine()
    ok = isinstance(eng.policy, NullPolicy)
    return {
        "ok": ok,
        "policy_type": type(eng.policy).__name__,
        "policy_version": getattr(eng.policy, "version", None),
        "engineering_policy_not_default": ok,
    }
