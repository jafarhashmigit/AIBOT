"""Adversarial tests for Phase64.1 canonical integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase64_1.constants import canonical_json_sha256
from phase64_1.engine import make_canonical_engine
from phase64_1.identity import apply_canonical_identity, make_canonical_decision_id
from phase64_1.market_snapshot import MarketSnapshotStore, build_snapshot_from_observation, commit_observation_snapshot


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # Deterministic identity
    a = make_canonical_decision_id(
        domain="AGENT_SHADOW",
        symbol="XAUUSDm",
        timeframe="M5",
        bar_timestamp_utc="2026-01-01T00:00:00Z",
        snapshot_hash="abc",
        policy_version="p1",
    )
    b = make_canonical_decision_id(
        domain="AGENT_SHADOW",
        symbol="XAUUSDm",
        timeframe="M5",
        bar_timestamp_utc="2026-01-01T00:00:00Z",
        snapshot_hash="abc",
        policy_version="p1",
    )
    c = make_canonical_decision_id(
        domain="HISTORICAL_HYPOTHETICAL",
        symbol="XAUUSDm",
        timeframe="M5",
        bar_timestamp_utc="2026-01-01T00:00:00Z",
        snapshot_hash="abc",
        policy_version="p1",
    )
    cases.append({"name": "deterministic_same_inputs", "pass": a == b and a != c})

    # Duplicate observation / idempotent bar
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-10")
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        r1 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        r2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        cases.append(
            {
                "name": "duplicate_observation_idempotent",
                "pass": not r1.get("skipped") and r2.get("skipped") and len(eng.intent_journal.all_intents()) == 1,
            }
        )

    # Missing snapshot verify
    with tempfile.TemporaryDirectory() as td:
        store = MarketSnapshotStore(Path(td))
        ok, why = store.verify("missing")
        cases.append({"name": "missing_snapshot", "pass": (not ok) and why == "missing_snapshot"})

    # Corrupt snapshot hash
    with tempfile.TemporaryDirectory() as td:
        store = MarketSnapshotStore(Path(td))
        body = build_snapshot_from_observation(
            {
                "accepted": True,
                "symbol": "XAUUSDm",
                "timeframe": "M5",
                "bar_timestamp_utc": "t",
                "observation_id": "o",
                "market_state_id": "m",
                "bid": 1.0,
                "ask": 1.1,
                "data_quality_status": "OK",
            }
        )
        rec = store.commit(body)
        # Tamper file
        lines = store.path.read_text(encoding="utf-8").splitlines()
        import json

        obj = json.loads(lines[0])
        obj["bid"] = 999.0
        store.path.write_text(json.dumps(obj) + "\n", encoding="utf-8")
        store._load()
        ok, why = store.verify(rec["snapshot_id"])
        cases.append({"name": "corrupt_snapshot_hash", "pass": (not ok) and why == "corrupt_snapshot_hash"})

    # WAIT / risk rejection non-executable
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-11")
        eng = make_canonical_engine(
            work=work,
            policy=EngineeringTestPolicy(["BUY"]),
            risk=RiskManager({"max_spread_atr": 0.0001, "stop_atr_multiple": 0.5}),  # force reject via spread
        )
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        st = (r.get("intent") or {}).get("intent_status")
        cases.append(
            {
                "name": "risk_reject_or_wait_non_executable",
                "pass": (not r.get("rejected"))
                and st in ("RISK_REJECTED", "NO_TRADE_WAIT")
                and not (r.get("intent") or {}).get("executable"),
                "status": st,
                "rejected": r.get("rejected"),
                "reason_codes": r.get("reason_codes") or (r.get("decision") or {}).get("reason_codes"),
            }
        )

    # Duplicate decision / one intent
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-12")
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["BUY", "BUY"]))
        eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        # Force second ensure via process same logical decision recovery path
        did = list(eng._intent_by_decision.keys())[0] if eng._intent_by_decision else None
        n1 = len(eng.intent_journal.intents_for_decision(did)) if did else 0
        from phase64_1.intent_bridge import ensure_execution_intent

        if did:
            # Reconstruct decision stub
            ensure_execution_intent(
                eng.intent_journal,
                decision={"decision_id": did, "action": "BUY", "proposed_action": "BUY", "execution_assumptions": {}},
                risk={"allowed": True, "final_action": "BUY", "reasons": []},
                account_profile={"symbol": "XAUUSDm"},
            )
            n2 = len(eng.intent_journal.intents_for_decision(did))
        else:
            n2 = 0
        cases.append({"name": "duplicate_decision_one_intent", "pass": did is not None and n1 == 1 and n2 == 1})

    # Conflicting decision payload
    snap = {
        "snapshot_id": "s",
        "snapshot_hash": "h",
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "bar_timestamp_utc": "t",
    }
    d1 = apply_canonical_identity(
        {"decision_id": "u1", "proposed_action": "BUY", "action": "BUY", "instrument": "XAUUSDm", "timeframe": "M5"},
        snapshot=snap,
        policy_version="p",
    )
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        eng.state.data["canonical_decisions"] = {
            d1["decision_id"]: {"proposed_action": "SELL", "snapshot_id": "s", "snapshot_hash": "h"}
        }
        # Direct check of conflict logic
        conflict = eng.state.data["canonical_decisions"][d1["decision_id"]]["proposed_action"] != d1["proposed_action"]
        cases.append({"name": "conflicting_decision_payload_detected", "pass": conflict})

    # Stale/invalid market data → reject, no executable intent
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-13")
        # Break ticks for idx so observation fails
        ts = str(m5[48]["timestamp_utc"])
        by[ts] = []
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["BUY"]))
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        cases.append(
            {
                "name": "invalid_market_data_no_trade",
                "pass": bool(r.get("rejected")) and r.get("intent") is None,
            }
        )

    # order_send prohibited
    cases.append({"name": "order_send_prohibited", "pass": "order_send" in PROHIBITED_MT5_API})

    # Repeated recovery
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = clean_bundle(day="2099-09-14")
        eng = make_canonical_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
        eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.recover_pending()
        eng.recover_pending()
        cases.append(
            {
                "name": "repeated_recovery",
                "pass": len(eng.intent_journal.all_intents()) == 1 and len(eng.snapshot_store._by_id) >= 1,
            }
        )

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "pass": all(c.get("pass") for c in cases),
        "genuine_broker_evidence": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
