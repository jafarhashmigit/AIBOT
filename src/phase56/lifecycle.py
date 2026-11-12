"""
IntegratedLifecycleEngine — subclasses Phase54 LifecycleEngine.

Fixes SL/TP defect: every observation monitors open positions via
monitor_and_maybe_exit BEFORE horizon force-exit. Phase54 source unmodified.
"""

from __future__ import annotations

import copy
from typing import Any

from phase49.outcomes import build_outcome
from phase50.experience_store import ExperienceStore
from phase54.constants import HORIZON_BARS
from phase54.decision import NullPolicy, decide
from phase54.experience import record_agent_shadow, record_historical_hypothetical
from phase54.lifecycle import LifecycleEngine
from phase54.paper_exec import PaperExecutionError, force_horizon_exit_from_bars, monitor_and_maybe_exit, open_paper_position
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase54.timeutil import now_utc_iso
from phase56.constants import HIST_DIR, HORIZON_BARS as H56, SHADOW_DIR
from phase56.feed_safety import FeedSafety
from phase56.observer import MarketObserver


class IntegratedLifecycleEngine(LifecycleEngine):
    """Production agent lifecycle path for Phase56 (NullPolicy default)."""

    def __init__(
        self,
        *,
        state: AgentState | None = None,
        risk: RiskManager | None = None,
        policy=None,
        record_counterfactuals: bool = False,
        observer: MarketObserver | None = None,
        feed_safety: FeedSafety | None = None,
        use_phase56_stores: bool = True,
        immediate_monitor_through_horizon: bool = True,
    ):
        # Parent sets hist/shadow to phase54 roots — replace when isolated
        super().__init__(
            state=state,
            risk=risk,
            policy=policy or NullPolicy(),
            record_counterfactuals=record_counterfactuals,
        )
        if use_phase56_stores:
            self.hist = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=HIST_DIR)
            self.shadow = ExperienceStore("AGENT_SHADOW", root=SHADOW_DIR)
        pol_ver = getattr(self.policy, "version", "unknown")
        self.observer = observer or MarketObserver(policy_version=str(pol_ver))
        self.feed_safety = feed_safety or FeedSafety()
        self.immediate_monitor_through_horizon = immediate_monitor_through_horizon
        self.pending_outcomes: list[dict[str, Any]] = list(self.state.data.get("pending_outcomes") or [])
        self.shutting_down = False
        self.metrics = {
            "candles_received": 0,
            "candles_accepted": 0,
            "candles_rejected": 0,
            "duplicates": 0,
            "sl_exits": 0,
            "tp_exits": 0,
            "horizon_exits": 0,
            "risk_rejections": 0,
            "monitor_passes": 0,
        }

    def persist(self) -> None:
        self.state.data["pending_outcomes"] = list(self.pending_outcomes)
        self.state.data["metrics"] = dict(self.metrics)
        self.state.data["feed_safety"] = self.feed_safety.snapshot()
        self.state.data["last_candle"] = self.observer.last_success
        super().persist()

    def _finalize_close(self, closed: dict[str, Any], day: str, decision: dict[str, Any] | None, obs: dict[str, Any] | None) -> None:
        pid = closed["position_id"]
        if pid in (self.state.data.get("closed_position_ids") or []):
            return  # prevent multiple exits / duplicate outcomes
        self.risk.register_close(pid, float(closed.get("net_r") or 0), day)
        self.state.bump("closes")
        closed_ids = list(self.state.data.get("closed_position_ids") or [])
        closed_ids.append(pid)
        self.state.data["closed_position_ids"] = closed_ids
        reason = closed.get("exit_reason")
        if reason == "STOP_LOSS":
            self.metrics["sl_exits"] += 1
        elif reason == "TAKE_PROFIT":
            self.metrics["tp_exits"] += 1
        elif reason == "HORIZON_EXIT":
            self.metrics["horizon_exits"] += 1
        if decision is None:
            decision = {
                "decision_id": closed.get("decision_id"),
                "timestamp_utc": closed.get("entry_timestamp"),
                "market_state_id": closed.get("market_state_id"),
                "action": closed.get("side"),
                "reason_codes": ["POSITION_EXIT"],
                "model_policy_version": getattr(self.policy, "version", None),
                "data_quality_status": "OK",
                "risk_estimate": {},
                "confidence": None,
            }
        record_agent_shadow(
            store=self.shadow,
            decision=decision,
            market_state=obs or {"regime": {}, "market_state_id": closed.get("market_state_id")},
            net_r=float(closed.get("net_r") or 0),
            outcome_timestamp_utc=str(closed.get("exit_timestamp")),
        )

    def monitor_open_positions(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
        current_idx: int,
    ) -> list[dict[str, Any]]:
        """Update every open paper position on new market observation. SL/TP before horizon."""
        closed_list = []
        for pid, position in list(self.risk.open_positions.items()):
            if position.get("status") != "OPEN":
                continue
            if pid in (self.state.data.get("closed_position_ids") or []):
                continue
            pos = copy.deepcopy(position)
            try:
                closed = monitor_and_maybe_exit(
                    pos,
                    m5=m5,
                    ticks_by_bar=ticks_by_bar,
                    current_idx=current_idx,
                    horizon_bars=HORIZON_BARS,
                )
            except PaperExecutionError as exc:
                self.feed_safety.note_dq_failure(str(exc))
                self.state.record_error(f"monitor:{exc}")
                continue
            self.metrics["monitor_passes"] += 1
            if closed is None:
                # Keep open; persist snapshot
                self.risk.open_positions[pid] = pos
                continue
            self._finalize_close(closed, day, None, None)
            closed_list.append(closed)
        self.persist()
        return closed_list

    def process_bar(
        self,
        *,
        day: str,
        m5: list[dict[str, Any]],
        h1: list[dict[str, Any]],
        ticks_by_bar: dict[str, list],
        idx: int,
        require_new_candle: bool = False,
    ) -> dict[str, Any]:
        if self.shutting_down:
            return {"skipped": True, "reason": "SHUTTING_DOWN"}

        trace: list[dict[str, Any]] = []
        self.metrics["candles_received"] += 1

        # Always monitor open positions on this observation first
        monitored = self.monitor_open_positions(day=day, m5=m5, ticks_by_bar=ticks_by_bar, current_idx=idx)
        if monitored:
            trace.append({"stage": "POSITION_MONITORING", "closed_n": len(monitored), "reasons": [c.get("exit_reason") for c in monitored]})

        if self.state.already_processed(day, idx):
            return {
                "skipped": True,
                "reason": "idempotent_already_processed",
                "day": day,
                "idx": idx,
                "monitored_closes": monitored,
                "trace": trace,
            }

        # Feed unsafe → WAIT / reject without treating as valid market signal
        if not self.feed_safety.safe:
            self.state.bump("dq_reject")
            self.metrics["candles_rejected"] += 1
            self.state.mark_processed(day, idx)
            self.persist()
            return {
                "skipped": False,
                "rejected": True,
                "reason_codes": ["FEED_UNSAFE", self.feed_safety.reason],
                "forced_wait": True,
                "monitored_closes": monitored,
                "trace": trace + [{"stage": "FEED_SAFETY", "safe": False}],
            }

        obs = self.observer.observe(
            day=day,
            m5=m5,
            idx=idx,
            h1=h1,
            ticks_by_bar=ticks_by_bar,
            require_new_candle=require_new_candle,
        )
        trace.append({"stage": "OBSERVATION", "ok": obs.get("accepted"), "id": obs.get("observation_id")})
        self.state.bump("observations")

        if not obs.get("accepted"):
            self.metrics["candles_rejected"] += 1
            reasons = obs.get("reason_codes") or []
            if "DUPLICATE_CANDLE_TIMESTAMP" in reasons:
                self.metrics["duplicates"] += 1
            self.feed_safety.note_dq_failure(",".join(reasons))
            self.state.bump("dq_reject")
            # Duplicates should not burn decision keys the same way — still mark idx for decision idempotency
            if "DUPLICATE_CANDLE_TIMESTAMP" not in reasons and "CONFLICTING_DUPLICATE_HASH" not in reasons:
                self.state.mark_processed(day, idx, obs.get("observation_id"))
            self.persist()
            return {
                "skipped": False,
                "rejected": True,
                "observation": obs,
                "reason_codes": reasons,
                "monitored_closes": monitored,
                "trace": trace,
            }

        self.metrics["candles_accepted"] += 1
        self.feed_safety.note_success()
        self.observer.commit_candle(m5[idx])

        # DECISION
        decision = decide(obs, obs.get("features") or {}, None, self.risk.snapshot(), policy=self.policy)
        # If feed became unsafe mid-flight, force WAIT
        if not self.feed_safety.safe:
            decision["proposed_action"] = "WAIT"
            decision["action"] = "WAIT"
            decision["reason_codes"] = list(decision.get("reason_codes") or []) + ["FEED_UNSAFE_FORCE_WAIT"]
        trace.append({"stage": "DECISION", "action": decision.get("proposed_action"), "id": decision.get("decision_id")})
        self.state.bump("decisions")

        gate = self.risk.evaluate(decision, obs)
        decision["action"] = gate["final_action"]
        decision["risk_gate"] = gate
        decision["reason_codes"] = list(decision.get("reason_codes") or []) + list(gate.get("reasons") or [])
        if not gate.get("allowed") and decision.get("proposed_action") in ("BUY", "SELL"):
            self.metrics["risk_rejections"] += 1
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
                    self.persist()  # open position durable before monitor

                    # SL/TP monitoring BEFORE horizon force-exit
                    monitor_idx = (
                        min(len(m5) - 1, entry_idx + HORIZON_BARS - 1)
                        if self.immediate_monitor_through_horizon
                        else idx
                    )
                    closed = monitor_and_maybe_exit(
                        position,
                        m5=m5,
                        ticks_by_bar=ticks_by_bar,
                        current_idx=monitor_idx,
                        horizon_bars=HORIZON_BARS,
                    )
                    trace.append(
                        {
                            "stage": "POSITION_MONITORING",
                            "exit": None if closed is None else closed.get("exit_reason"),
                            "monitor_idx": monitor_idx,
                        }
                    )
                    if closed is None and self.immediate_monitor_through_horizon:
                        # Fallback only if monitor returned None incorrectly at full horizon
                        if monitor_idx >= entry_idx + HORIZON_BARS - 1:
                            closed = force_horizon_exit_from_bars(
                                position, m5=m5, ticks_by_bar=ticks_by_bar, horizon_bars=HORIZON_BARS
                            )
                    if closed is not None:
                        trace.append({"stage": "EXIT", "reason": closed.get("exit_reason"), "net_r": closed.get("net_r")})
                        self._finalize_close(closed, day, decision, obs)
                    else:
                        # Remains OPEN for later candles
                        trace.append({"stage": "EXIT", "reason": "REMAINS_OPEN"})
                except PaperExecutionError as exc:
                    decision["action"] = "WAIT"
                    decision["reason_codes"].append(f"exec_fail:{exc}")
                    action = "WAIT"
                    self.risk.note_error()
                    self.feed_safety.note_dq_failure(str(exc))
                    self.state.record_error(str(exc))
                    trace.append({"stage": "PAPER_ENTRY", "ok": False, "error": str(exc)})

        if action == "WAIT":
            record_agent_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=0.0,
                outcome_timestamp_utc=obs["bar_timestamp_utc"],
            )
            trace.append({"stage": "EXPERIENCE", "source": "AGENT_SHADOW", "action": "WAIT"})
        elif closed is not None:
            trace.append({"stage": "EXPERIENCE", "source": "AGENT_SHADOW", "action": action, "via": "finalize_close"})

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
            "monitored_closes": monitored,
            "trace": trace,
            "sl_tp_integrated": True,
            "processed_at": now_utc_iso(),
        }
