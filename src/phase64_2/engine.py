"""
HardenedLifecycleEngine — subclasses Phase64.1 CanonicalLifecycleEngine.

Fixes intent terminal status, bar-level identity stability, durable WAIT.
Does not modify Phase0–64.1 source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase54.state import AgentState
from phase56.candle_registry import CandleRegistry
from phase57_1.durable_engine import DurableLifecycleEngine
from phase57_1.journal import TradeLifecycleJournal
from phase64_1.engine import CanonicalLifecycleEngine
from phase64_1.market_snapshot import MarketSnapshotStore
from phase64_2.hardened_journal import HardenedIntentJournal
from phase64_2.identity_guard import IdentityConflictError, register_or_reuse_bar_decision
from phase64_2.intent_state import (
    CrashInjected,
    audit_intent_consistency,
    finalize_paper_intent,
    repair_incomplete_intents,
)
from phase64_2.wait_durable import record_wait_experience_durable


class HardenedLifecycleEngine(CanonicalLifecycleEngine):
    def __init__(self, *args: Any, crash_at: str | None = None, **kwargs: Any):
        # Force hardened journal if not provided
        intent_journal = kwargs.pop("intent_journal", None)
        work_intent = kwargs.get("shadow_root")  # unused marker
        super().__init__(*args, intent_journal=intent_journal, crash_at=crash_at, **kwargs)
        if not isinstance(self.intent_journal, HardenedIntentJournal):
            # Replace with hardened journal at same root
            root = self.intent_journal.root
            self.intent_journal = HardenedIntentJournal(root, crash_at=None)
        self.crash_at = crash_at
        self._bar_decisions: dict[str, Any] = dict(self.state.data.get("bar_decisions") or {})
        self._wait_experience_by_decision: dict[str, str] = dict(
            self.state.data.get("wait_experience_by_decision") or {}
        )

    def persist(self) -> None:
        self.state.data["bar_decisions"] = dict(self._bar_decisions)
        self.state.data["wait_experience_by_decision"] = dict(self._wait_experience_by_decision)
        super().persist()

    def _finalize_close(
        self,
        closed: dict[str, Any],
        day: str,
        decision: dict[str, Any] | None,
        obs: dict[str, Any] | None,
    ) -> None:
        # Durable paper finalize (57.1) without Phase64.1's status=None intent links
        DurableLifecycleEngine._finalize_close(self, closed, day, decision, obs)
        pid = closed.get("position_id")
        did = (decision or {}).get("decision_id") or closed.get("decision_id") or self._decision_by_position.get(
            pid or ""
        )
        iid = self._intent_by_decision.get(str(did)) if did else None
        if not (did and iid):
            return
        exp_id = None
        for rec in reversed(list(self.shadow.all())):
            ctx = rec.get("decision_context") or {}
            if ctx.get("decision_id") == did or ctx.get("txn_id") == self._txn_by_position.get(pid or ""):
                exp_id = rec.get("experience_id")
                break
        try:
            finalize_paper_intent(
                self.intent_journal,  # type: ignore[arg-type]
                decision_id=str(did),
                intent_id=str(iid),
                position_id=pid,
                txn_id=closed.get("txn_id") or self._txn_by_position.get(pid or ""),
                net_r=closed.get("net_r"),
                exit_reason=closed.get("exit_reason"),
                experience_id=exp_id,
                crash_at=self.crash_at,
            )
        except CrashInjected:
            raise
        except Exception as exc:
            self.state.record_error(f"intent_finalize:{exc}")

    def _complete_unfinalized_waits(self) -> list[dict[str, Any]]:
        """Finish WAIT durable experience if process crashed after mark_processed / before finalize."""
        done = []
        for intent in list(self.intent_journal.all_intents()):
            st = intent.get("intent_status")
            if st not in ("NO_TRADE_WAIT", "RISK_REJECTED"):
                continue
            if st == "WAIT_FINALIZED":
                continue
            did = str(intent.get("decision_id"))
            iid = str(intent.get("intent_id"))
            meta = (self.state.data.get("canonical_decisions") or {}).get(did) or {}
            decision = {
                "decision_id": did,
                "timestamp_utc": meta.get("bar_timestamp_utc") or "UNKNOWN",
                "market_state_id": meta.get("market_state_id") or "UNKNOWN",
                "action": "WAIT",
                "runtime_uuid_decision_id": meta.get("runtime_uuid_decision_id"),
                "snapshot_id": meta.get("snapshot_id"),
                "model_policy_version": meta.get("policy_version"),
                "reason_codes": ["WAIT_RECOVERY"],
            }
            obs = {
                "bar_timestamp_utc": meta.get("bar_timestamp_utc"),
                "market_state_id": decision["market_state_id"],
                "regime": {},
            }
            try:
                wait_rec = record_wait_experience_durable(
                    shadow=self.shadow,
                    journal=self.intent_journal,  # type: ignore[arg-type]
                    decision=decision,
                    market_state=obs,
                    intent_id=iid,
                    crash_at=None,
                )
                self._wait_experience_by_decision[did] = wait_rec["experience_id"]
                done.append(wait_rec)
            except CrashInjected:
                raise
            except Exception as exc:
                self.state.record_error(f"wait_recovery:{exc}")
        if done:
            self.persist()
        return done

    def recover_pending(self) -> dict[str, Any]:
        out = super().recover_pending()
        wait_done = self._complete_unfinalized_waits()
        # Repair incomplete intent statuses after durable recovery
        closed = set(self.state.data.get("closed_position_ids") or [])
        repair = repair_incomplete_intents(
            self.intent_journal,  # type: ignore[arg-type]
            closed_position_ids=closed,
            decision_by_position=dict(self._decision_by_position),
            intent_by_decision=dict(self._intent_by_decision),
            experience_by_decision=dict(self._wait_experience_by_decision),
            crash_at=self.crash_at if self.crash_at == "during_intent_status_repair" else None,
        )
        audit = audit_intent_consistency(
            self.intent_journal,  # type: ignore[arg-type]
            open_position_ids=set(self.risk.open_positions.keys()),
            closed_position_ids=closed,
        )
        out["wait_recovery"] = {"n": len(wait_done)}
        out["intent_repair"] = repair
        out["intent_audit"] = audit
        self.persist()
        return out

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
        import phase54.experience as exp_mod
        import phase64_1.engine as e641
        import phase64_1.identity as ident_mod
        from phase64_2.stable_snapshot import commit_stable_observation_snapshot

        saved_shadow = exp_mod.record_agent_shadow
        saved_out = e641.link_intent_outcome
        saved_exp = e641.link_intent_experience
        saved_apply = ident_mod.apply_canonical_identity
        saved_snap = e641.commit_observation_snapshot
        engine_self = self
        e641.commit_observation_snapshot = commit_stable_observation_snapshot  # type: ignore[assignment]

        def skip_shadow(**kwargs: Any) -> dict[str, Any]:
            return {"deferred_phase64_2": True}

        def skip_link(*_a: Any, **_k: Any) -> dict[str, Any]:
            return {"deferred_phase64_2": True}

        def apply_with_guard(decision: dict[str, Any], *, snapshot: dict[str, Any], domain: str, policy_version: str):
            d = saved_apply(decision, snapshot=snapshot, domain=domain, policy_version=policy_version)
            # Always key by process_bar (day, idx) — not snapshot-derived — for stable restarts
            try:
                reg = register_or_reuse_bar_decision(
                    engine_self._bar_decisions,
                    day=day,
                    idx=idx,
                    canonical_decision_id=str(d["decision_id"]),
                    snapshot_hash=str(snapshot.get("snapshot_hash")),
                    proposed_action=d.get("proposed_action"),
                )
                d["bar_decision_registration"] = reg.get("status")
            except IdentityConflictError as exc:
                d["identity_conflict"] = str(exc)
                raise
            engine_self.persist()
            return d

        exp_mod.record_agent_shadow = skip_shadow  # type: ignore[assignment]
        e641.link_intent_outcome = skip_link  # type: ignore[assignment]
        e641.link_intent_experience = skip_link  # type: ignore[assignment]
        ident_mod.apply_canonical_identity = apply_with_guard  # type: ignore[assignment]
        try:
            out = CanonicalLifecycleEngine.process_bar(
                self,
                day=day,
                m5=m5,
                h1=h1,
                ticks_by_bar=ticks_by_bar,
                idx=idx,
                require_new_candle=require_new_candle,
            )
        finally:
            exp_mod.record_agent_shadow = saved_shadow  # type: ignore[assignment]
            e641.link_intent_outcome = saved_out  # type: ignore[assignment]
            e641.link_intent_experience = saved_exp  # type: ignore[assignment]
            ident_mod.apply_canonical_identity = saved_apply  # type: ignore[assignment]
            e641.commit_observation_snapshot = saved_snap  # type: ignore[assignment]

        if out.get("rejected"):
            return out

        if out.get("skipped"):
            # Crash may have marked bar processed before WAIT finalize
            self._complete_unfinalized_waits()
            closed = set(self.state.data.get("closed_position_ids") or [])
            repair_incomplete_intents(
                self.intent_journal,  # type: ignore[arg-type]
                closed_position_ids=closed,
                decision_by_position=dict(self._decision_by_position),
                intent_by_decision=dict(self._intent_by_decision),
                experience_by_decision=dict(self._wait_experience_by_decision),
            )
            return out

        decision = out.get("decision") or {}
        intent = out.get("intent") or {}
        action = decision.get("action")

        if action == "WAIT" and intent.get("intent_id"):
            wait_rec = record_wait_experience_durable(
                shadow=self.shadow,
                journal=self.intent_journal,  # type: ignore[arg-type]
                decision=decision,
                market_state=out.get("observation") or {},
                intent_id=str(intent["intent_id"]),
                crash_at=self.crash_at,
            )
            self._wait_experience_by_decision[str(decision["decision_id"])] = wait_rec["experience_id"]
            out["wait_durable"] = wait_rec
            out["intent"] = {
                **intent,
                "intent_status": wait_rec.get("intent_status"),
                "executable": False,
            }
            # Update trace
            trace = list(out.get("trace") or [])
            trace.append(
                {
                    "stage": "EXPERIENCE",
                    "source": "AGENT_SHADOW",
                    "action": "WAIT",
                    "durable": True,
                    "experience_id": wait_rec["experience_id"],
                    "created": wait_rec["created"],
                }
            )
            out["trace"] = trace
            self.persist()

        # Refresh intent status from journal for BUY/SELL closed in same bar
        if intent.get("intent_id"):
            live = self.intent_journal.get_intent(str(intent["intent_id"]))
            if live:
                out["intent"] = {
                    **(out.get("intent") or {}),
                    "intent_status": live.get("intent_status"),
                    "executable": live.get("intent_status") in ("PENDING", "ORDER_LINKED", "PARTIAL_FILL", "UNFILLED"),
                }

        out["phase64_2_hardened"] = True
        out["intent_audit"] = audit_intent_consistency(
            self.intent_journal,  # type: ignore[arg-type]
            open_position_ids=set(self.risk.open_positions.keys()),
            closed_position_ids=set(self.state.data.get("closed_position_ids") or []),
        )
        return out


def make_hardened_engine(
    *,
    work: Path,
    policy=None,
    risk: RiskManager | None = None,
    record_counterfactuals: bool = False,
    immediate_monitor_through_horizon: bool = True,
    crash_at: str | None = None,
    account_profile: dict[str, Any] | None = None,
) -> HardenedLifecycleEngine:
    work.mkdir(parents=True, exist_ok=True)
    return HardenedLifecycleEngine(
        state=AgentState(path=work / "agent_state.json"),
        risk=risk or RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        policy=policy,
        record_counterfactuals=record_counterfactuals,
        immediate_monitor_through_horizon=immediate_monitor_through_horizon,
        journal=TradeLifecycleJournal(work / "journal", crash_at=None),
        intent_journal=HardenedIntentJournal(work / "intent_journal", crash_at=None),
        snapshot_store=MarketSnapshotStore(work / "snapshots", crash_at=None),
        hist_root=work / "HISTORICAL_HYPOTHETICAL",
        shadow_root=work / "AGENT_SHADOW",
        registry_path=work / "candle_registry.json",
        crash_at=crash_at,
        account_profile=account_profile,
    )
