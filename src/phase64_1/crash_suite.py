"""Crash/recovery matrix for Phase64.1 canonical lifecycle — paper fixtures only."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase57_1.journal import CrashInjected as DurableCrash
from phase64_1.constants import canonical_json_sha256
from phase64_1.engine import make_canonical_engine
from phase64_1.market_snapshot import CrashInjected


def _run_until_crash(work: Path, crash_at: str, *, action: str = "BUY") -> dict[str, Any]:
    day, m5, h1, by = clean_bundle(day="2099-09-01", move_after_entry=-5.0)
    eng = make_canonical_engine(
        work=work,
        policy=EngineeringTestPolicy([action]),
        risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
        crash_at=crash_at,
        account_profile={"broker": "Exness", "environment": "DEMO", "platform": "MT5", "symbol": "XAUUSDm", "digits": 3},
    )
    raised = None
    result = None
    try:
        # idx>=48 required for observer lookback; leave room for entry+horizon
        result = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    except (CrashInjected, DurableCrash) as exc:
        raised = str(exc)
    return {
        "raised": raised,
        "result": result,
        "day": day,
        "m5": m5,
        "h1": h1,
        "by": by,
        "idx": 48,
    }


def _recover_and_replay(work: Path, bundle: dict[str, Any], *, action: str = "BUY") -> dict[str, Any]:
    eng = make_canonical_engine(
        work=work,
        policy=EngineeringTestPolicy([action]),
        risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
        crash_at=None,
        account_profile={"broker": "Exness", "environment": "DEMO", "platform": "MT5", "symbol": "XAUUSDm", "digits": 3},
    )
    recovery = eng.recover_pending()
    # Replay same bar — must be idempotent if already marked, or complete if partial
    out1 = eng.process_bar(
        day=bundle["day"], m5=bundle["m5"], h1=bundle["h1"], ticks_by_bar=bundle["by"], idx=bundle["idx"]
    )
    out2 = eng.process_bar(
        day=bundle["day"], m5=bundle["m5"], h1=bundle["h1"], ticks_by_bar=bundle["by"], idx=bundle["idx"]
    )
    intents = eng.intent_journal.all_intents()
    snaps = len(eng.snapshot_store._by_id)
    opens = len(eng.risk.open_positions)
    closed = list(eng.state.data.get("closed_position_ids") or [])
    return {
        "recovery": recovery,
        "replay": out1,
        "second_pass": out2,
        "n_intents": len(intents),
        "n_snapshots": snaps,
        "n_open": opens,
        "n_closed": len(closed),
        "second_skipped": bool(out2.get("skipped")),
    }


def case(crash_at: str, *, action: str = "BUY") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        first = _run_until_crash(work, crash_at, action=action)
        recovered = _recover_and_replay(work, first, action=action)
        # No duplicate intents for same decision
        eng = make_canonical_engine(
            work=work,
            policy=EngineeringTestPolicy(["WAIT"]),
            account_profile={"symbol": "XAUUSDm"},
        )
        by_decision: dict[str, int] = {}
        for intent in eng.intent_journal.all_intents():
            did = intent.get("decision_id")
            if did:
                by_decision[did] = by_decision.get(did, 0) + 1
        dup_intents = {k: v for k, v in by_decision.items() if v > 1}
        ok = first["raised"] is not None and recovered["second_skipped"] and len(dup_intents) == 0
        # after_snapshot: may complete on replay with 1 intent
        if crash_at == "after_snapshot_persistence":
            ok = first["raised"] is not None and recovered["n_snapshots"] >= 1 and recovered["second_skipped"]
        return {
            "case": crash_at,
            "crash_raised": first["raised"],
            "n_intents": recovered["n_intents"],
            "n_snapshots": recovered["n_snapshots"],
            "n_open": recovered["n_open"],
            "n_closed": recovered["n_closed"],
            "second_pass_idempotent": recovered["second_skipped"],
            "duplicate_intents": dup_intents,
            "pass": ok and len(dup_intents) == 0,
            "genuine_broker_evidence": False,
        }


def run_crash_matrix() -> dict[str, Any]:
    points = [
        "after_snapshot_persistence",
        "after_decision_persistence",
        "after_risk_approval",
        "before_intent_persistence",
        "after_intent_before_paper_entry",
        "after_paper_entry",
        "after_exit_commit_before_outcome",
    ]
    cases = [case(p) for p in points]
    # WAIT path (no paper entry)
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-02")
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        wait_case = {
            "case": "wait_non_executable_intent",
            "intent_status": (r.get("intent") or {}).get("intent_status"),
            "executable": (r.get("intent") or {}).get("executable"),
            "pass": (r.get("intent") or {}).get("intent_status") == "NO_TRADE_WAIT"
            and not (r.get("intent") or {}).get("executable"),
            "genuine_broker_evidence": False,
        }
        cases.append(wait_case)

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "broker_order_send": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
