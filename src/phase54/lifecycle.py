"""Full paper lifecycle FSM with idempotency and restart recovery."""

from __future__ import annotations

from typing import Any

from phase49.outcomes import build_outcome
from phase54.constants import HORIZON_BARS
from phase54.decision import NullPolicy, decide
from phase54.experience import (
    historical_store,
    record_agent_shadow,
    record_historical_hypothetical,
    shadow_store,
)
from phase54.observer import build_observation
from phase54.paper_exec import PaperExecutionError, force_horizon_exit_from_bars, open_paper_position
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase54.timeutil import now_utc_iso


STAGES = (
    "OBSERVATION",
    "DECISION",
    "RISK_CHECK",
    "PAPER_ENTRY",
    "POSITION_MONITORING",
    "EXIT",
    "OUTCOME",
    "EXPERIENCE",
)


class LifecycleEngine:
    def __init__(
        self,
        *,
        state: AgentState | None = None,
        risk: RiskManager | None = None,
        policy=None,
        record_counterfactuals: bool = True,
    ):
        self.state = state or AgentState()
        self.risk = risk or RiskManager()
        if self.state.data.get("risk_snapshot"):
            self.risk.load_snapshot(self.state.data["risk_snapshot"])
        # restore open positions into risk
        for pid, prec in (self.state.data.get("open_positions") or {}).items():
            self.risk.register_open(pid, prec)
        self.policy = policy or NullPolicy()
        self.hist = historical_store()
        self.shadow = shadow_store()
        self.record_counterfactuals = record_counterfactuals
        self.last_stage_trace: list[dict[str, Any]] = []

    def persist(self) -> None:
        self.state.data["risk_snapshot"] = self.risk.snapshot()
        self.state.data["open_positions"] = dict(self.risk.open_positions)
        self.state.save()
        self.hist.flush()
        self.shadow.flush()

    def process_bar(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        h1: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
        idx: int,
    ) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        if self.state.already_processed(day, idx):
            return {"skipped": True, "reason": "idempotent_already_processed", "day": day, "idx": idx}

        # 1 OBSERVATION
        obs = build_observation(m5=m5, idx=idx, h1=h1, ticks_by_bar=ticks_by_bar, day=day)
        trace.append({"stage": "OBSERVATION", "ok": obs.get("accepted"), "id": obs.get("observation_id")})
        self.state.bump("observations")
        if not obs.get("accepted"):
            self.state.bump("dq_reject")
            self.risk.note_error()
            self.state.record_error(f"dq:{obs.get('errors')}")
            self.state.mark_processed(day, idx, obs.get("observation_id"))
            self.persist()
            return {"skipped": False, "rejected": True, "observation": obs, "trace": trace}

        self.risk.note_success()

        # 2 DECISION
        decision = decide(obs, obs.get("features") or {}, None, self.risk.snapshot(), policy=self.policy)
        trace.append({"stage": "DECISION", "action": decision.get("proposed_action"), "id": decision.get("decision_id")})
        self.state.bump("decisions")

        # 3 RISK_CHECK
        gate = self.risk.evaluate(decision, obs)
        decision["action"] = gate["final_action"]
        decision["risk_gate"] = gate
        decision["reason_codes"] = list(decision.get("reason_codes") or []) + list(gate.get("reasons") or [])
        trace.append({"stage": "RISK_CHECK", "final_action": gate["final_action"], "allowed": gate["allowed"]})

        action = decision["action"]
        if action == "BUY":
            self.state.bump("buy")
        elif action == "SELL":
            self.state.bump("sell")
        else:
            self.state.bump("wait")

        position = None
        closed = None
        # 4–6 ENTRY / MONITOR / EXIT (only if directional)
        if action in ("BUY", "SELL"):
            entry_idx = idx + 1
            if entry_idx >= len(m5):
                decision["action"] = "WAIT"
                decision["reason_codes"].append("incomplete_entry_path")
                action = "WAIT"
                self.state.bump("wait")
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
                    self.risk.register_open(position["position_id"], position)
                    self.state.bump("opens")
                    trace.append({"stage": "PAPER_ENTRY", "position_id": position["position_id"]})
                    # Immediate horizon exit for deterministic replay stride
                    closed = force_horizon_exit_from_bars(
                        position, m5=m5, ticks_by_bar=ticks_by_bar, horizon_bars=HORIZON_BARS
                    )
                    trace.append({"stage": "EXIT", "reason": closed.get("exit_reason"), "net_r": closed.get("net_r")})
                    self.risk.register_close(closed["position_id"], float(closed.get("net_r") or 0), day)
                    self.state.bump("closes")
                    closed_ids = list(self.state.data.get("closed_position_ids") or [])
                    closed_ids.append(closed["position_id"])
                    self.state.data["closed_position_ids"] = closed_ids
                except PaperExecutionError as exc:
                    decision["action"] = "WAIT"
                    decision["reason_codes"].append(f"exec_fail:{exc}")
                    action = "WAIT"
                    self.risk.note_error()
                    self.state.record_error(str(exc))
                    trace.append({"stage": "PAPER_ENTRY", "ok": False, "error": str(exc)})

        # 7–8 OUTCOME + EXPERIENCE
        if action == "WAIT":
            # WAIT outcome matures at same decision time with 0 incremental PnL
            outcome_ts = obs["bar_timestamp_utc"]
            net_r = 0.0
            record_agent_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=net_r,
                outcome_timestamp_utc=outcome_ts,
            )
            trace.append({"stage": "EXPERIENCE", "source": "AGENT_SHADOW", "action": "WAIT", "net_r": 0.0})
        elif closed is not None:
            record_agent_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=float(closed.get("net_r") or 0),
                outcome_timestamp_utc=str(closed.get("exit_timestamp")),
            )
            trace.append(
                {
                    "stage": "EXPERIENCE",
                    "source": "AGENT_SHADOW",
                    "action": action,
                    "net_r": closed.get("net_r"),
                }
            )

        if self.record_counterfactuals:
            for side in ("BUY", "SELL"):
                oc = build_outcome(action=side, day=day, decision_idx=idx, m5=m5, ticks_by_bar=ticks_by_bar)
                if oc.get("data_quality_status") == "OK" and oc.get("net_r") is not None:
                    record_historical_hypothetical(
                        store=self.hist,
                        day=day,
                        decision_idx=idx,
                        bar_ts=obs["bar_timestamp_utc"],
                        market_state_id=obs["market_state_id"],
                        action=side,
                        net_r=float(oc["net_r"]),
                        outcome_timestamp_utc=str(oc.get("exit_timestamp") or obs["bar_timestamp_utc"]),
                        regime=obs.get("regime") or {},
                        provenance="phase49.build_outcome",
                    )
            trace.append({"stage": "EXPERIENCE", "source": "HISTORICAL_HYPOTHETICAL", "actions": ["BUY", "SELL"]})

        self.state.mark_processed(day, idx, obs.get("observation_id"))
        self.persist()
        self.last_stage_trace = trace
        return {
            "skipped": False,
            "rejected": False,
            "observation": obs,
            "decision": decision,
            "position": position,
            "closed": closed,
            "trace": trace,
            "processed_at": now_utc_iso(),
        }
