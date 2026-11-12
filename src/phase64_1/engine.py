"""
CanonicalLifecycleEngine — subclasses Phase57.1 DurableLifecycleEngine.

Wires MarketSnapshot + canonical decision identity + Phase64 intent journal into the
real Phase54/56 paper path without modifying Phase0–63 source.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from phase49.outcomes import build_outcome
from phase50.experience_store import ExperienceStore
from phase54.constants import HORIZON_BARS
from phase54.decision import NullPolicy, decide
from phase54.experience import record_historical_hypothetical
from phase54.paper_exec import PaperExecutionError, force_horizon_exit_from_bars, monitor_and_maybe_exit, open_paper_position
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase54.timeutil import now_utc_iso
from phase56.candle_registry import CandleRegistry
from phase56.observer import MarketObserver
from phase57_1.durable_engine import DurableLifecycleEngine
from phase57_1.journal import CrashInjected as DurableCrash
from phase57_1.journal import TradeLifecycleJournal
from phase64.execution_intent import ExecutionIntentJournal
from phase64_1.constants import DOMAIN_AGENT_SHADOW, INTENT_DIR, SNAPSHOT_DIR
from phase64_1.identity import apply_canonical_identity
from phase64_1.intent_bridge import ensure_execution_intent, link_intent_experience, link_intent_outcome
from phase64_1.market_snapshot import CrashInjected, MarketSnapshotStore, commit_observation_snapshot


class CanonicalLifecycleEngine(DurableLifecycleEngine):
    """Production paper path + canonical identity + durable intent (no broker orders)."""

    def __init__(
        self,
        *,
        state: AgentState | None = None,
        risk: RiskManager | None = None,
        policy=None,
        record_counterfactuals: bool = False,
        immediate_monitor_through_horizon: bool = True,
        journal: TradeLifecycleJournal | None = None,
        intent_journal: ExecutionIntentJournal | None = None,
        snapshot_store: MarketSnapshotStore | None = None,
        hist_root: Path | None = None,
        shadow_root: Path | None = None,
        registry_path: Path | None = None,
        crash_at: str | None = None,
        account_profile: dict[str, Any] | None = None,
    ):
        # Map exit-commit crash alias onto phase57_1 journal crash points
        durable_crash = None
        if crash_at == "after_exit_commit_before_outcome":
            durable_crash = "after_durable_exit_commit"
        elif crash_at == "during_experience_reconstruction":
            durable_crash = "during_experience_reconstruction"
        elif crash_at in (
            "before_exit_detection",
            "after_exit_detection",
            "before_durable_exit_commit",
            "during_journal_write",
            "after_durable_exit_commit",
            "before_outcome_derivation",
            "during_outcome_persistence",
            "after_outcome_before_experience",
        ):
            durable_crash = crash_at

        super().__init__(
            state=state,
            risk=risk,
            policy=policy,
            record_counterfactuals=record_counterfactuals,
            immediate_monitor_through_horizon=immediate_monitor_through_horizon,
            journal=journal,
            hist_root=hist_root,
            shadow_root=shadow_root,
            registry_path=registry_path,
            crash_at=durable_crash,
        )
        self.crash_at = crash_at
        self.account_profile = account_profile or {
            "broker": "UNKNOWN",
            "environment": "DEMO",
            "platform": "MT5",
            "symbol": "UNKNOWN",
            "verification_status": "UNKNOWN",
            "digits": "UNKNOWN",
        }
        self.snapshot_store = snapshot_store or MarketSnapshotStore(SNAPSHOT_DIR)
        if crash_at == "after_snapshot_persistence":
            self.snapshot_store.crash_at = "after_snapshot_persistence"
        self.intent_journal = intent_journal or ExecutionIntentJournal(INTENT_DIR)
        if crash_at == "after_intent_persistence":
            self.intent_journal.crash_at = "after_intent_persistence"
        self._intent_by_decision: dict[str, str] = dict(self.state.data.get("intent_by_decision") or {})
        self._decision_by_position: dict[str, str] = dict(self.state.data.get("decision_by_position") or {})

    def persist(self) -> None:
        self.state.data["intent_by_decision"] = dict(self._intent_by_decision)
        self.state.data["decision_by_position"] = dict(self._decision_by_position)
        super().persist()

    def recover_pending(self) -> dict[str, Any]:
        """Recover durable exits + reload snapshot/intent journals."""
        # Reload journals from disk (WAL)
        self.snapshot_store._load()
        self.intent_journal._load()
        out = super().recover_pending()
        out["snapshots_n"] = len(self.snapshot_store._by_id)
        out["intents_n"] = len(self.intent_journal.all_intents())
        return out

    def _finalize_close(
        self,
        closed: dict[str, Any],
        day: str,
        decision: dict[str, Any] | None,
        obs: dict[str, Any] | None,
    ) -> None:
        super()._finalize_close(closed, day, decision, obs)
        # Link intent outcome after durable finalize (best-effort; idempotent stages)
        pid = closed.get("position_id")
        did = (decision or {}).get("decision_id") or closed.get("decision_id") or self._decision_by_position.get(pid or "")
        iid = self._intent_by_decision.get(str(did)) if did else None
        if did and iid:
            try:
                link_intent_outcome(
                    self.intent_journal,
                    decision_id=str(did),
                    intent_id=str(iid),
                    position_id=pid,
                    txn_id=closed.get("txn_id") or self._txn_by_position.get(pid or ""),
                    net_r=closed.get("net_r"),
                    exit_reason=closed.get("exit_reason"),
                )
                # Find latest experience id if present on shadow
                exp_id = None
                for rec in reversed(list(self.shadow.all())):
                    if (rec.get("decision_context") or {}).get("decision_id") == did or (
                        rec.get("decision_context") or {}
                    ).get("txn_id") == self._txn_by_position.get(pid or ""):
                        exp_id = rec.get("experience_id")
                        break
                link_intent_experience(
                    self.intent_journal,
                    decision_id=str(did),
                    intent_id=str(iid),
                    experience_id=exp_id,
                )
            except Exception as exc:
                self.state.record_error(f"intent_link:{exc}")

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

        monitored = self.monitor_open_positions(day=day, m5=m5, ticks_by_bar=ticks_by_bar, current_idx=idx)
        if monitored:
            trace.append(
                {
                    "stage": "POSITION_MONITORING",
                    "closed_n": len(monitored),
                    "reasons": [c.get("exit_reason") for c in monitored],
                }
            )

        if self.state.already_processed(day, idx):
            return {
                "skipped": True,
                "reason": "idempotent_already_processed",
                "day": day,
                "idx": idx,
                "monitored_closes": monitored,
                "trace": trace,
            }

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

        # MARKET_SNAPSHOT (immutable)
        snapshot = commit_observation_snapshot(
            self.snapshot_store,
            obs,
            account_profile=self.account_profile,
            source_domain=DOMAIN_AGENT_SHADOW,
        )
        trace.append({"stage": "MARKET_SNAPSHOT", "snapshot_id": snapshot["snapshot_id"], "hash": snapshot["snapshot_hash"]})
        if self.crash_at == "after_snapshot_persistence":
            self.persist()
            raise CrashInjected("after_snapshot_persistence")

        # DECISION (phase54 decide) then canonical identity
        decision = decide(obs, obs.get("features") or {}, None, self.risk.snapshot(), policy=self.policy)
        if not self.feed_safety.safe:
            decision["proposed_action"] = "WAIT"
            decision["action"] = "WAIT"
            decision["reason_codes"] = list(decision.get("reason_codes") or []) + ["FEED_UNSAFE_FORCE_WAIT"]
        pol_ver = str(getattr(self.policy, "version", "unknown"))
        decision = apply_canonical_identity(
            decision,
            snapshot=snapshot,
            domain=DOMAIN_AGENT_SHADOW,
            policy_version=pol_ver,
        )
        # Persist decision annotation in state (idempotent map)
        dec_map = dict(self.state.data.get("canonical_decisions") or {})
        if decision["decision_id"] not in dec_map:
            dec_map[decision["decision_id"]] = {
                "runtime_uuid_decision_id": decision.get("runtime_uuid_decision_id"),
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "bar_timestamp_utc": snapshot.get("bar_timestamp_utc"),
                "proposed_action": decision.get("proposed_action"),
            }
            self.state.data["canonical_decisions"] = dec_map
            self.persist()
        elif dec_map[decision["decision_id"]].get("proposed_action") not in (None, decision.get("proposed_action")):
            # Conflicting payload for same identity
            raise ValueError("conflicting_decision_payload_same_identity")

        if self.crash_at == "after_decision_persistence":
            raise CrashInjected("after_decision_persistence")

        trace.append(
            {
                "stage": "DECISION",
                "action": decision.get("proposed_action"),
                "id": decision.get("decision_id"),
                "runtime_uuid": decision.get("runtime_uuid_decision_id"),
            }
        )
        self.state.bump("decisions")

        gate = self.risk.evaluate(decision, obs)
        decision["action"] = gate["final_action"]
        decision["risk_gate"] = gate
        decision["reason_codes"] = list(decision.get("reason_codes") or []) + list(gate.get("reasons") or [])
        if not gate.get("allowed") and decision.get("proposed_action") in ("BUY", "SELL"):
            self.metrics["risk_rejections"] += 1
        trace.append({"stage": "RISK_CHECK", "final_action": gate["final_action"], "allowed": gate["allowed"]})

        if self.crash_at == "after_risk_approval":
            self.persist()
            raise CrashInjected("after_risk_approval")

        # EXECUTION_INTENT (before paper entry)
        intent = ensure_execution_intent(
            self.intent_journal,
            decision=decision,
            risk=gate,
            account_profile={**self.account_profile, "fixture": False},
            crash_at=self.crash_at,
        )
        self._intent_by_decision[decision["decision_id"]] = intent["intent_id"]
        self.persist()
        trace.append(
            {
                "stage": "EXECUTION_INTENT",
                "intent_id": intent["intent_id"],
                "status": intent["intent_status"],
                "executable": intent["executable"],
                "reused": intent["reused"],
            }
        )
        if self.crash_at == "after_intent_before_paper_entry":
            raise CrashInjected("after_intent_before_paper_entry")

        action = decision["action"]
        if action == "BUY":
            self.state.bump("buy")
        elif action == "SELL":
            self.state.bump("sell")
        else:
            self.state.bump("wait")

        position = None
        closed = None

        if action in ("BUY", "SELL") and intent["executable"]:
            entry_idx = idx + 1
            if entry_idx >= len(m5):
                decision["action"] = "WAIT"
                decision["reason_codes"].append("incomplete_entry_path")
                action = "WAIT"
                self.state.bump("wait")
            else:
                try:
                    # Idempotent: reuse open/closed position for this canonical decision
                    existing_open = None
                    for pid, prec in self.risk.open_positions.items():
                        if prec.get("canonical_decision_id") == decision["decision_id"] or prec.get(
                            "decision_id"
                        ) == decision["decision_id"]:
                            existing_open = copy.deepcopy(prec)
                            break
                    already_closed_pid = None
                    for pid, did in self._decision_by_position.items():
                        if did == decision["decision_id"] and pid in (
                            self.state.data.get("closed_position_ids") or []
                        ):
                            already_closed_pid = pid
                            break

                    if already_closed_pid:
                        trace.append(
                            {
                                "stage": "PAPER_ENTRY",
                                "idempotent": True,
                                "already_closed": already_closed_pid,
                            }
                        )
                    else:
                        if existing_open is not None:
                            position = existing_open
                            trace.append(
                                {
                                    "stage": "PAPER_ENTRY",
                                    "idempotent": True,
                                    "position_id": position["position_id"],
                                    "intent_id": intent["intent_id"],
                                }
                            )
                        else:
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
                            position["intent_id"] = intent["intent_id"]
                            position["canonical_decision_id"] = decision["decision_id"]
                            position["snapshot_id"] = snapshot["snapshot_id"]
                            self.risk.register_open(position["position_id"], position)
                            self._decision_by_position[position["position_id"]] = decision["decision_id"]
                            self.state.bump("opens")
                            trace.append(
                                {
                                    "stage": "PAPER_ENTRY",
                                    "position_id": position["position_id"],
                                    "intent_id": intent["intent_id"],
                                    "decision_id": decision["decision_id"],
                                }
                            )
                            self.persist()
                            if self.crash_at == "after_paper_entry":
                                raise CrashInjected("after_paper_entry")

                        if position is not None:
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
                                if monitor_idx >= entry_idx + HORIZON_BARS - 1:
                                    closed = force_horizon_exit_from_bars(
                                        position, m5=m5, ticks_by_bar=ticks_by_bar, horizon_bars=HORIZON_BARS
                                    )
                            if closed is not None:
                                closed["intent_id"] = intent["intent_id"]
                                closed["canonical_decision_id"] = decision["decision_id"]
                                trace.append(
                                    {
                                        "stage": "EXIT",
                                        "reason": closed.get("exit_reason"),
                                        "net_r": closed.get("net_r"),
                                    }
                                )
                                try:
                                    self._finalize_close(closed, day, decision, obs)
                                except DurableCrash:
                                    raise
                                trace.append({"stage": "OUTCOME", "via": "phase57_1_durable"})
                                trace.append(
                                    {"stage": "EXPERIENCE", "source": "AGENT_SHADOW", "via": "finalize_close"}
                                )
                            else:
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
            # WAIT experience via parent shadow path (non-durable txn) — keep phase56 behavior
            from phase54.experience import record_agent_shadow

            record_agent_shadow(
                store=self.shadow,
                decision=decision,
                market_state=obs,
                net_r=0.0,
                outcome_timestamp_utc=obs["bar_timestamp_utc"],
            )
            link_intent_outcome(
                self.intent_journal,
                decision_id=decision["decision_id"],
                intent_id=intent["intent_id"],
                position_id=None,
                txn_id=None,
                net_r=0.0,
                exit_reason="WAIT",
            )
            trace.append({"stage": "EXPERIENCE", "source": "AGENT_SHADOW", "action": "WAIT"})

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
            "snapshot": snapshot,
            "decision": decision,
            "intent": intent,
            "position": position,
            "closed": closed,
            "monitored_closes": monitored,
            "trace": trace,
            "sl_tp_integrated": True,
            "canonical_identity": True,
            "broker_order_send": False,
            "processed_at": now_utc_iso(),
        }


def make_canonical_engine(
    *,
    work: Path,
    policy=None,
    risk: RiskManager | None = None,
    record_counterfactuals: bool = False,
    immediate_monitor_through_horizon: bool = True,
    crash_at: str | None = None,
    account_profile: dict[str, Any] | None = None,
) -> CanonicalLifecycleEngine:
    work.mkdir(parents=True, exist_ok=True)
    return CanonicalLifecycleEngine(
        state=AgentState(path=work / "agent_state.json"),
        risk=risk or RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        policy=policy,
        record_counterfactuals=record_counterfactuals,
        immediate_monitor_through_horizon=immediate_monitor_through_horizon,
        journal=TradeLifecycleJournal(work / "journal", crash_at=None),
        intent_journal=ExecutionIntentJournal(work / "intent_journal", crash_at=None),
        snapshot_store=MarketSnapshotStore(work / "snapshots", crash_at=None),
        hist_root=work / "HISTORICAL_HYPOTHETICAL",
        shadow_root=work / "AGENT_SHADOW",
        registry_path=work / "candle_registry.json",
        crash_at=crash_at,
        account_profile=account_profile,
    )
