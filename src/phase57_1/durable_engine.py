"""DurableLifecycleEngine — wraps Phase56 without modifying it."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase54.constants import HORIZON_BARS
from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase56.candle_registry import CandleRegistry
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.observer import MarketObserver
from phase57_1.constants import HIST_DIR, JOURNAL_DIR, SHADOW_DIR, STATE_DIR
from phase57_1.journal import CrashInjected, TradeLifecycleJournal
from phase57_1.outcome import build_exit_payload, derive_outcome, experience_from_exit


class DurableLifecycleEngine(IntegratedLifecycleEngine):
    """
    Journal-backed finalize path.

    EXIT_COMMITTED is durable before closed_ids / experience are treated as final.
    Experience is derived and idempotent via deterministic experience_id(txn_id).
    """

    def __init__(
        self,
        *,
        state: AgentState | None = None,
        risk: RiskManager | None = None,
        policy=None,
        record_counterfactuals: bool = False,
        immediate_monitor_through_horizon: bool = True,
        journal: TradeLifecycleJournal | None = None,
        hist_root: Path | None = None,
        shadow_root: Path | None = None,
        registry_path: Path | None = None,
        crash_at: str | None = None,
    ):
        pol = policy if policy is not None else NullPolicy()
        super().__init__(
            state=state,
            risk=risk,
            policy=pol,
            record_counterfactuals=record_counterfactuals,
            immediate_monitor_through_horizon=immediate_monitor_through_horizon,
            use_phase56_stores=True,
        )
        hr = hist_root or HIST_DIR
        sr = shadow_root or SHADOW_DIR
        hr.mkdir(parents=True, exist_ok=True)
        sr.mkdir(parents=True, exist_ok=True)
        self.hist = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=hr)
        self.shadow = ExperienceStore("AGENT_SHADOW", root=sr)
        rp = registry_path or (STATE_DIR / "candle_registry.json")
        self.observer = MarketObserver(
            policy_version=str(getattr(pol, "version", "unknown")),
            registry=CandleRegistry(path=rp),
        )
        self.journal = journal or TradeLifecycleJournal(JOURNAL_DIR, crash_at=crash_at)
        if crash_at:
            self.journal.crash_at = crash_at
        self._txn_by_position: dict[str, str] = dict(self.state.data.get("txn_by_position") or {})
        # Wrap register_open to journal POSITION_OPEN
        _orig = self.risk.register_open

        def _register_open(position_id: str, rec: dict[str, Any]) -> None:
            _orig(position_id, rec)
            txn_id = self._txn_by_position.get(position_id) or uuid.uuid4().hex
            self._txn_by_position[position_id] = txn_id
            if not any(
                r.get("position_id") == position_id and r.get("stage") == "POSITION_OPEN"
                for r in self.journal.all()
            ):
                self.journal.commit(
                    stage="POSITION_OPEN",
                    txn_id=txn_id,
                    position_id=position_id,
                    experience_source="AGENT_SHADOW",
                    payload={
                        "side": rec.get("side"),
                        "entry_fill": rec.get("entry_fill"),
                        "entry_bid": rec.get("entry_bid"),
                        "entry_ask": rec.get("entry_ask"),
                        "entry_timestamp": rec.get("entry_timestamp"),
                        "stop_loss": rec.get("stop_loss"),
                        "take_profit": rec.get("take_profit"),
                        "decision_id": rec.get("decision_id"),
                        "observation_id": rec.get("observation_id"),
                        "market_state_id": rec.get("market_state_id"),
                        "atr_at_entry": rec.get("atr_at_entry"),
                    },
                )
            self.state.data["txn_by_position"] = dict(self._txn_by_position)

        self.risk.register_open = _register_open  # type: ignore[method-assign]

    def persist(self) -> None:
        self.state.data["txn_by_position"] = dict(self._txn_by_position)
        super().persist()

    def _resume_committed_exit(self, exit_rec: dict[str, Any], day: str) -> None:
        """Complete experience + closed_ids from durable EXIT_COMMITTED without re-exiting."""
        from phase57_1.rebuild import rebuild_experience_from_journal

        pid = exit_rec.get("position_id") or (exit_rec.get("payload") or {}).get("position_id")
        if pid and pid in (self.state.data.get("closed_position_ids") or []):
            rebuild_experience_from_journal(self.journal, shadow=self.shadow, source="AGENT_SHADOW")
            return
        rebuild_experience_from_journal(self.journal, shadow=self.shadow, source="AGENT_SHADOW")
        payload = exit_rec.get("payload") or {}
        net_r = float(payload.get("net_r") or 0)
        if pid:
            if pid in self.risk.open_positions:
                self.risk.register_close(pid, net_r, day)
            closed_ids = list(self.state.data.get("closed_position_ids") or [])
            if pid not in closed_ids:
                closed_ids.append(pid)
                self.state.data["closed_position_ids"] = closed_ids
                self.state.bump("closes")

    def recover_pending(self) -> dict[str, Any]:
        """After restart: rebuild missing experience from journal; sync closed_ids."""
        from phase57_1.rebuild import rebuild_experience_from_journal

        out = rebuild_experience_from_journal(self.journal, shadow=self.shadow, source="AGENT_SHADOW")
        day = str((self.state.data.get("cursor") or {}).get("day") or "")
        for r in self.journal.committed_exits():
            if (r.get("experience_source") or "AGENT_SHADOW") != "AGENT_SHADOW":
                continue
            pid = r.get("position_id") or (r.get("payload") or {}).get("position_id")
            if not pid:
                continue
            closed_ids = list(self.state.data.get("closed_position_ids") or [])
            if pid not in closed_ids:
                net_r = float((r.get("payload") or {}).get("net_r") or 0)
                if pid in self.risk.open_positions:
                    self.risk.register_close(pid, net_r, day)
                closed_ids.append(pid)
                self.state.data["closed_position_ids"] = closed_ids
        self.persist()
        return out

    def _finalize_close(
        self,
        closed: dict[str, Any],
        day: str,
        decision: dict[str, Any] | None,
        obs: dict[str, Any] | None,
    ) -> None:
        pid = closed["position_id"]
        if pid in (self.state.data.get("closed_position_ids") or []):
            return

        # Idempotent resume if EXIT already durably committed for this position
        prior = [
            r
            for r in self.journal.committed_exits()
            if r.get("position_id") == pid or (r.get("payload") or {}).get("position_id") == pid
        ]
        if prior:
            self._resume_committed_exit(prior[-1], day)
            return

        txn_id = self._txn_by_position.get(pid) or uuid.uuid4().hex
        self._txn_by_position[pid] = txn_id
        closed = dict(closed)
        closed["txn_id"] = txn_id

        # Map crash_at aliases used by adversarial suite
        j = self.journal
        if j.crash_at == "before_exit_detection":
            raise CrashInjected("before_exit_detection")

        exit_payload = build_exit_payload(closed, decision=decision, obs=obs)

        if j.crash_at == "after_exit_detection":
            j.commit(
                stage="EXIT_DETECTED",
                txn_id=txn_id,
                position_id=pid,
                experience_source="AGENT_SHADOW",
                payload={"exit_reason": closed.get("exit_reason"), "note": "detected_only"},
            )
            raise CrashInjected("after_exit_detection")

        if j.crash_at == "before_durable_exit_commit":
            raise CrashInjected("before_durable_exit_commit")

        # EXIT_DETECTED then durable EXIT_COMMITTED
        j.commit(
            stage="EXIT_DETECTED",
            txn_id=txn_id,
            position_id=pid,
            experience_source="AGENT_SHADOW",
            payload={"exit_reason": closed.get("exit_reason")},
        )

        if j.crash_at == "during_journal_write":
            j.crash_at = "during_journal_write"  # consumed inside commit
        j.commit(
            stage="EXIT_COMMITTED",
            txn_id=txn_id,
            position_id=pid,
            experience_source="AGENT_SHADOW",
            payload=exit_payload,
        )

        if j.crash_at == "after_durable_exit_commit":
            raise CrashInjected("after_durable_exit_commit")

        if j.crash_at == "before_outcome_derivation":
            raise CrashInjected("before_outcome_derivation")

        outcome = derive_outcome(exit_payload)
        if not outcome.get("ok"):
            # Incomplete evidence — quarantine via journal payload, do not fabricate
            j.commit(
                stage="OUTCOME_DERIVED",
                txn_id=txn_id,
                position_id=pid,
                experience_source="AGENT_SHADOW",
                payload={"ok": False, "error": outcome},
            )
            raise ValueError(f"incomplete_outcome:{outcome}")

        if j.crash_at == "during_outcome_persistence":
            raise CrashInjected("during_outcome_persistence")

        j.commit(
            stage="OUTCOME_DERIVED",
            txn_id=txn_id,
            position_id=pid,
            experience_source="AGENT_SHADOW",
            payload=outcome,
        )

        if j.crash_at == "after_outcome_before_experience":
            raise CrashInjected("after_outcome_before_experience")

        # Experience derived from journal evidence (deterministic id)
        rec = experience_from_exit(
            txn_id=txn_id,
            exit_payload=exit_payload,
            outcome=outcome,
            source="AGENT_SHADOW",
            horizon_bars=HORIZON_BARS,
        )
        # Idempotent append
        existing_ids = {r.get("experience_id") for r in self.shadow.all()}
        if rec["experience_id"] not in existing_ids:
            self.shadow.append(rec)
        self.shadow.flush()

        j.commit(
            stage="EXPERIENCE_COMMITTED",
            txn_id=txn_id,
            position_id=pid,
            experience_source="AGENT_SHADOW",
            payload={"experience_id": rec["experience_id"], "net_r": outcome.get("net_r")},
        )

        # Only after durable exit+experience path: update closed_ids / risk
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
        self.state.data["txn_by_position"] = dict(self._txn_by_position)


def make_durable_engine(
    *,
    work: Path,
    policy=None,
    risk: RiskManager | None = None,
    record_counterfactuals: bool = False,
    immediate_monitor_through_horizon: bool = True,
    crash_at: str | None = None,
) -> DurableLifecycleEngine:
    work.mkdir(parents=True, exist_ok=True)
    return DurableLifecycleEngine(
        state=AgentState(path=work / "agent_state.json"),
        risk=risk or RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        policy=policy,
        record_counterfactuals=record_counterfactuals,
        immediate_monitor_through_horizon=immediate_monitor_through_horizon,
        journal=TradeLifecycleJournal(work / "journal", crash_at=crash_at),
        hist_root=work / "HISTORICAL_HYPOTHETICAL",
        shadow_root=work / "AGENT_SHADOW",
        registry_path=work / "candle_registry.json",
        crash_at=crash_at,
    )
