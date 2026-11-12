"""Execution & data-quality adversarial cases — independent of engine happy-path tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.observer import validate_bar
from phase54.paper_exec import PaperExecutionError, open_paper_position
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.candle_registry import CandleRegistry
from phase57.adapter import make_engine
from phase57.fixtures import clean_bundle, conflicting_duplicate_bar, malformed_price_bundle


def run_execution_integrity(work_dir) -> dict[str, Any]:
    cases = {}
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Missing / malformed prices
    day, m5, h1, by = malformed_price_bundle()
    bad_bar = m5[30]
    cases["zero_negative_ohlc"] = {
        "errors": validate_bar(bad_bar),
        "ok": len(validate_bar(bad_bar)) > 0,
    }

    # Invalid bid/ask crossed
    crossed = [{"epoch_ms": 1, "timestamp_utc": "t", "bid": 10.0, "ask": 9.0}]
    try:
        open_paper_position(
            decision={"decision_id": "x", "action": "BUY", "observation_id": "o"},
            market_state={"atr": 1.0, "symbol": "XAUUSD", "timeframe": "M5", "market_state_id": "m"},
            entry_bar_ts="t",
            ticks_by_bar={"t": crossed},
            sizing={"units": 1, "stop_distance": 1.0},
            m5=[],
            entry_idx=0,
        )
        cases["crossed_market"] = {"ok": False, "error": "did_not_raise"}
    except PaperExecutionError as exc:
        cases["crossed_market"] = {"ok": True, "error": str(exc)}

    # Invalid SL
    try:
        open_paper_position(
            decision={"decision_id": "x", "action": "BUY", "observation_id": "o"},
            market_state={"atr": 1.0, "symbol": "XAUUSD", "timeframe": "M5", "market_state_id": "m"},
            entry_bar_ts="t",
            ticks_by_bar={"t": [{"epoch_ms": 1, "timestamp_utc": "t", "bid": 1.0, "ask": 1.1}]},
            sizing={"units": 1, "stop_distance": 0},
            m5=[],
            entry_idx=0,
        )
        cases["invalid_stop"] = {"ok": False}
    except PaperExecutionError:
        cases["invalid_stop"] = {"ok": True}

    # Conflicting duplicate hash
    reg = CandleRegistry(path=work_dir / "dup.json")
    day2, m52, h12, by2 = clean_bundle(day="2099-07-10")
    bar = m52[48]
    reg.commit(bar, policy_version="v")
    conf = conflicting_duplicate_bar(bar)
    g = reg.evaluate(conf, policy_version="v")
    cases["conflicting_hash"] = {"ok": g.get("reason") == "CONFLICTING_DUPLICATE_HASH", "gate": g}

    # Out-of-order candle
    reg2 = CandleRegistry(path=work_dir / "oo.json")
    reg2.commit(m52[50], policy_version="v")
    g2 = reg2.evaluate(m52[48], policy_version="v")
    cases["out_of_order"] = {"ok": g2.get("reason") == "NON_CHRONOLOGICAL_OR_REPLAYED", "gate": g2}

    # Risk boundaries block entry
    eng = make_engine(
        state_path=work_dir / "risk.json",
        registry_path=work_dir / "risk_c.json",
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "max_daily_loss_r": 0.1}),
        hist_root=work_dir / "risk_h",
        shadow_root=work_dir / "risk_sh",
    )
    eng.risk.daily_realized_r["2099-06-03"] = -1.0
    day3, m53, h13, by3 = clean_bundle()
    # Align day key
    d = str(m53[48]["timestamp_utc"])[:10]
    eng.risk.daily_realized_r[d] = -1.0
    r = eng.process_bar(day=day3, m5=m53, h1=h13, ticks_by_bar=by3, idx=48)
    cases["daily_loss_blocks_entry"] = {
        "ok": (r.get("decision") or {}).get("action") == "WAIT",
        "reasons": (r.get("decision") or {}).get("reason_codes"),
    }

    # Feed unsafe blocks entry
    eng2 = make_engine(
        state_path=work_dir / "feed.json",
        registry_path=work_dir / "feed_c.json",
        policy=EngineeringTestPolicy(["BUY"]),
        hist_root=work_dir / "feed_h",
        shadow_root=work_dir / "feed_sh",
    )
    eng2.feed_safety.mark_feed_stale("TEST")
    r2 = eng2.process_bar(day=day3, m5=m53, h1=h13, ticks_by_bar=by3, idx=60)
    cases["stale_blocks_entry"] = {
        "ok": r2.get("rejected") is True and "FEED_UNSAFE" in (r2.get("reason_codes") or []),
        "reason_codes": r2.get("reason_codes"),
    }

    # Spread / sizing evidence (not realism claims)
    day4, m54, h14, by4 = clean_bundle(day="2099-07-11", move_after_entry=-5.0)
    eng3 = make_engine(
        state_path=work_dir / "spr.json",
        registry_path=work_dir / "spr_c.json",
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        immediate_monitor_through_horizon=True,
        hist_root=work_dir / "spr_h",
        shadow_root=work_dir / "spr_sh",
    )
    r3 = eng3.process_bar(day=day4, m5=m54, h1=h14, ticks_by_bar=by4, idx=48)
    closed = r3.get("closed")
    cases["spread_recorded_once"] = {
        "ok": closed is not None and closed.get("entry_spread") is not None and closed.get("commission") is None,
        "entry_spread": None if closed is None else closed.get("entry_spread"),
        "exit_reason": None if closed is None else closed.get("exit_reason"),
    }

    ok = all(c.get("ok") for c in cases.values())
    return {"ok": ok, "cases": cases}
