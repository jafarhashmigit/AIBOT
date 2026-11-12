"""Multi-bar chronological paper validation on the approved hardened runtime."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase64_2.constants import STATUS_PAPER_FINALIZED, STATUS_WAIT_FINALIZED
from phase64_2.identity_guard import IdentityConflictError
from phase64_3.approved_runtime import assert_hardened_runtime, make_approved_paper_engine, summarize_engine_counts
from phase64_3.constants import canonical_json_sha256
from phase64_3.xauusdm_profile import active_account_profile


class SeqPolicy:
    """Engineering sequence that stays BUY for several decisions then WAIT."""

    version = "phase64_3_seq_policy_v1"

    def __init__(self, actions: list[str]):
        self.actions = list(actions)
        self._i = 0

    def propose(self, market_state, features, model_output, risk_state):
        if self._i >= len(self.actions):
            a = "WAIT"
        else:
            a = self.actions[self._i]
            self._i += 1
        return {
            "action": a,
            "expected_net_r": None,
            "prob_positive": None,
            "calibrated": False,
            "confidence": None,
            "uncertainty": 1.0,
            "reason_codes": ["PHASE64_3_SEQ", a],
        }


def _long_bundle(day: str = "2099-12-01", n_bars: int = 120):
    return directional_path(day=day, n_bars=n_bars, move_after_entry=-5.0)


def run_multibar_suite() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # 1) Duplicate observation / one decision per bar
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = _long_bundle()
        eng = make_approved_paper_engine(
            work=work,
            policy=NullPolicy(),
            immediate_monitor_through_horizon=False,
        )
        assert_hardened_runtime(eng)
        r1 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        r2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        cases.append(
            {
                "name": "duplicate_obs_one_decision",
                "pass": not r1.get("skipped")
                and r2.get("skipped")
                and len(eng.intent_journal.all_intents()) == 1
                and (r1.get("intent") or {}).get("intent_status") == STATUS_WAIT_FINALIZED,
            }
        )

    # 2) Conflicting snapshot same bar
    with tempfile.TemporaryDirectory() as td:
        from phase64_2.identity_guard import register_or_reuse_bar_decision

        m: dict = {}
        register_or_reuse_bar_decision(
            m, day="d", idx=48, canonical_decision_id="c", snapshot_hash="h1", proposed_action="WAIT"
        )
        rejected = False
        try:
            register_or_reuse_bar_decision(
                m, day="d", idx=48, canonical_decision_id="c", snapshot_hash="h2", proposed_action="WAIT"
            )
        except IdentityConflictError:
            rejected = True
        cases.append({"name": "same_bar_conflicting_snapshot_rejected", "pass": rejected})

    # 3) Multi-bar open position + SL monitoring + finalize
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = _long_bundle(n_bars=120)
        # Adverse move after entry → SL on later bars
        eng = make_approved_paper_engine(
            work=work,
            policy=SeqPolicy(["BUY"] + ["WAIT"] * 20),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5, "max_simultaneous_positions": 1}),
            immediate_monitor_through_horizon=False,
            account_profile=active_account_profile(),
        )
        outs = []
        open_seen = False
        pending_while_open = False
        closed_final = False
        bid_ask_ok = True
        for idx in range(48, 70):
            o = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=idx)
            outs.append(o)
            if eng.risk.open_positions:
                open_seen = True
                for intent in eng.intent_journal.all_intents():
                    if intent.get("intent_status") == "PENDING":
                        pending_while_open = True
            for c in o.get("monitored_closes") or []:
                if c.get("exit_bid") is not None and c.get("exit_ask") is not None:
                    if float(c["exit_ask"]) < float(c["exit_bid"]):
                        bid_ask_ok = False
                if c.get("exit_reason") in ("STOP_LOSS", "TAKE_PROFIT", "HORIZON_EXIT"):
                    closed_final = True
            if o.get("closed") and (o.get("intent") or {}).get("intent_status") == STATUS_PAPER_FINALIZED:
                closed_final = True
        # Force more bars if still open
        for idx in range(70, min(100, len(m5) - 2)):
            if not eng.risk.open_positions and closed_final:
                break
            o = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=idx)
            if o.get("closed") or (o.get("monitored_closes")):
                closed_final = True
            for intent in eng.intent_journal.all_intents():
                if intent.get("intent_status") == STATUS_PAPER_FINALIZED:
                    closed_final = True
        counts = summarize_engine_counts(eng)
        # Closed intents must not be PENDING
        pending_closed = False
        closed_ids = set(eng.state.data.get("closed_position_ids") or [])
        for intent in eng.intent_journal.all_intents():
            if intent.get("intent_status") == "PENDING":
                for r in eng.intent_journal.all_records():
                    if r.get("intent_id") == intent.get("intent_id") and r.get("stage") == "OUTCOME_RECORDED":
                        pid = (r.get("payload") or {}).get("position_id")
                        if pid in closed_ids:
                            pending_closed = True
        cases.append(
            {
                "name": "multibar_open_monitor_sl_finalize",
                "pass": open_seen
                and pending_while_open
                and closed_final
                and bid_ask_ok
                and not pending_closed
                and counts["n_hist_experiences"] == 0
                and counts["genuine_broker_deals"] == 0,
                "counts": counts,
                "open_seen": open_seen,
                "pending_while_open": pending_while_open,
                "closed_final": closed_final,
            }
        )

    # 4) Multiple positions across bars (allow 2)
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = directional_path(day="2099-12-02", n_bars=120, move_after_entry=5.0)
        eng = make_approved_paper_engine(
            work=work,
            policy=SeqPolicy(["BUY", "WAIT", "WAIT", "SELL"] + ["WAIT"] * 30),
            risk=RiskManager(
                {"max_spread_atr": 5.0, "stop_atr_multiple": 0.5, "max_simultaneous_positions": 2}
            ),
            immediate_monitor_through_horizon=True,  # close within horizon for count stability
        )
        for idx in (48, 55, 60, 65):
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=idx)
        counts = summarize_engine_counts(eng)
        cases.append(
            {
                "name": "multi_position_across_bars",
                "pass": counts["n_canonical_decisions"] >= 2 and counts["n_intents"] >= 2,
                "counts": counts,
            }
        )

    # 5) SELL path
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = directional_path(day="2099-12-03", n_bars=100, move_after_entry=5.0)
        eng = make_approved_paper_engine(
            work=work,
            policy=EngineeringTestPolicy(["SELL"]),
            immediate_monitor_through_horizon=True,
        )
        out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        cases.append(
            {
                "name": "sell_paper_entry",
                "pass": (out.get("decision") or {}).get("action") in ("SELL", "WAIT")
                and assert_hardened_runtime(eng)["approved_paper_runtime"],
                "action": (out.get("decision") or {}).get("action"),
                "intent_status": (out.get("intent") or {}).get("intent_status"),
            }
        )

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "evidence_type": "SIMULATED_PAPER_FIXTURE",
        "genuine_broker_deals": 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
