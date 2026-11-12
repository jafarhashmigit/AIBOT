"""Independent invariant checkers — do not trust engine self-reporting alone."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase55.independent import compare_to_engine, recompute_path
from phase54.decision import NullPolicy
from phase54.paper_exec import monitor_and_maybe_exit
from phase56.lifecycle import IntegratedLifecycleEngine
from phase57.constants import EXPECTED_NULL_POLICY


def check_null_policy_default(engine: IntegratedLifecycleEngine) -> dict[str, Any]:
    ok = isinstance(engine.policy, NullPolicy) and getattr(engine.policy, "version", None) == EXPECTED_NULL_POLICY
    return {"id": "null_policy_default", "ok": ok, "policy": type(engine.policy).__name__, "version": getattr(engine.policy, "version", None)}


def check_once_per_observation(processed_keys: list[str], accepted_events: list[dict]) -> dict[str, Any]:
    """Each accepted decision event should map to exactly one processed key."""
    keys = [e["key"] for e in accepted_events]
    c = Counter(keys)
    dups = [k for k, n in c.items() if n > 1]
    # processed_keys should contain each accepted key exactly once
    missing = [k for k in keys if k not in processed_keys]
    multi = [k for k in keys if processed_keys.count(k) > 1]
    ok = not dups and not missing and not multi
    return {
        "id": "once_per_accepted_observation",
        "ok": ok,
        "duplicate_accepts": dups,
        "missing_in_state": missing,
        "multi_in_state": multi,
        "n_accepted": len(keys),
    }


def check_no_duplicate_decisions(results: list[dict]) -> dict[str, Any]:
    """Same day:idx must not produce two non-skipped decisions."""
    seen = {}
    violations = []
    for r in results:
        if r.get("skipped") or r.get("rejected"):
            continue
        key = f"{r.get('day')}:{r.get('idx')}"
        if key in seen:
            violations.append(key)
        seen[key] = True
    return {"id": "no_duplicate_candle_decisions", "ok": len(violations) == 0, "violations": violations}


def check_sl_tp_before_horizon_trace(traces: list[list[dict]]) -> dict[str, Any]:
    """In traces with an EXIT, POSITION_MONITORING must appear before EXIT when SL/TP integrated."""
    bad = []
    for i, tr in enumerate(traces):
        stages = [t.get("stage") for t in tr]
        if "EXIT" in stages:
            if "POSITION_MONITORING" not in stages:
                bad.append({"trace_i": i, "stages": stages, "reason": "missing_monitoring"})
            elif stages.index("POSITION_MONITORING") > stages.index("EXIT"):
                bad.append({"trace_i": i, "stages": stages, "reason": "monitor_after_exit"})
    return {"id": "sl_tp_before_horizon_in_trace", "ok": len(bad) == 0, "violations": bad}


def check_buy_sell_prices(closed_positions: list[dict]) -> dict[str, Any]:
    bad = []
    for c in closed_positions:
        side = c.get("side")
        if side == "BUY":
            if c.get("entry_fill") != c.get("entry_ask"):
                bad.append({"pid": c.get("position_id"), "err": "BUY_entry_not_ask"})
            if c.get("exit_fill") != c.get("exit_bid"):
                bad.append({"pid": c.get("position_id"), "err": "BUY_exit_not_bid"})
        elif side == "SELL":
            if c.get("entry_fill") != c.get("entry_bid"):
                bad.append({"pid": c.get("position_id"), "err": "SELL_entry_not_bid"})
            if c.get("exit_fill") != c.get("exit_ask"):
                bad.append({"pid": c.get("position_id"), "err": "SELL_exit_not_ask"})
    return {"id": "buy_exit_bid_sell_exit_ask", "ok": len(bad) == 0, "violations": bad}


def check_sl_first_same_bar(m5, by, entry_idx: int) -> dict[str, Any]:
    """Independent recreation of SL-first priority (does not call engine process_bar)."""
    entry_ts = str(m5[entry_idx]["timestamp_utc"])
    entry_ask = 2000.05
    pos = {
        "position_id": "inv",
        "side": "BUY",
        "status": "OPEN",
        "entry_idx": entry_idx,
        "entry_fill": entry_ask,
        "entry_bid": 2000.0,
        "entry_ask": entry_ask,
        "stop_loss": entry_ask - 0.01,
        "take_profit": entry_ask + 0.01,
        "atr_at_entry": 1.0,
        "audit": [],
    }
    # First tick hits SL; second would hit TP
    by2 = dict(by)
    by2[entry_ts] = [
        {"epoch_ms": 1, "timestamp_utc": entry_ts, "bid": entry_ask - 0.02, "ask": entry_ask - 0.01},
        {"epoch_ms": 2, "timestamp_utc": entry_ts, "bid": entry_ask + 0.05, "ask": entry_ask + 0.06},
    ]
    closed = monitor_and_maybe_exit(pos, m5=m5, ticks_by_bar=by2, current_idx=entry_idx, horizon_bars=12)
    ok = closed is not None and closed.get("exit_reason") == "STOP_LOSS"
    return {"id": "sl_first_same_bar", "ok": ok, "exit_reason": None if closed is None else closed.get("exit_reason")}


def check_no_double_close(closed_ids: list[str]) -> dict[str, Any]:
    c = Counter(closed_ids)
    dups = [k for k, n in c.items() if n > 1]
    return {"id": "no_double_close", "ok": len(dups) == 0, "duplicates": dups}


def check_no_orphans(open_positions: dict, closed_ids: list[str]) -> dict[str, Any]:
    orphans = [pid for pid, p in open_positions.items() if p.get("status") == "CLOSED" or pid in closed_ids]
    # Also: positions marked OPEN but in closed_ids
    return {
        "id": "no_orphaned_opens_after_clean_run",
        "ok": len(orphans) == 0 and all(p.get("status") == "OPEN" for p in open_positions.values()),
        "orphans": orphans,
        "n_open": len(open_positions),
    }


def check_experience_separation(hist_path: str, shadow_path: str, hist_recs: list, shadow_recs: list) -> dict[str, Any]:
    from pathlib import Path

    hp = Path(hist_path).resolve()
    sp = Path(shadow_path).resolve()
    hp_s = str(hp).replace("\\", "/").lower()
    sp_s = str(sp).replace("\\", "/").lower()
    # Distinct files; must not write into Phase54/56 production experience trees
    distinct = hp != sp
    contam = any(m in hp_s for m in ("/data/phase54/", "/data/phase56/")) or any(
        m in sp_s for m in ("/data/phase54/", "/data/phase56/")
    )
    path_ok = distinct and not contam
    hist_src = all(r.get("source") == "HISTORICAL_HYPOTHETICAL" for r in hist_recs)
    sh_src = all(r.get("source") == "AGENT_SHADOW" for r in shadow_recs)
    hi = {r.get("experience_id") for r in hist_recs}
    si = {r.get("experience_id") for r in shadow_recs}
    overlap = hi & si
    return {
        "id": "experience_stores_separated",
        "ok": path_ok and hist_src and sh_src and len(overlap) == 0,
        "path_ok": path_ok,
        "contaminated_prior_phase_root": contam,
        "hist_n": len(hist_recs),
        "shadow_n": len(shadow_recs),
        "id_overlap": list(overlap)[:5],
    }


def check_independent_recompute(closed: dict, m5, by) -> dict[str, Any]:
    indep = recompute_path(
        side=closed["side"],
        m5=m5,
        ticks_by_bar=by,
        entry_idx=int(closed["entry_idx"]),
        horizon_bars=12,
        atr=closed.get("atr_at_entry"),
        stop_distance=abs(float(closed["entry_fill"]) - float(closed["stop_loss"])),
    )
    cmp_ = compare_to_engine(closed, indep)
    return {"id": "independent_recompute_match", "ok": bool(cmp_.get("ok")), "compare": cmp_}
