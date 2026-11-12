"""Conservative SL/TP gap-through execution adapter — does not modify Phase54/56/57.1."""

from __future__ import annotations

from typing import Any

from phase60.constants import canonical_json_sha256
from phase60.slippage import executable_side, fill_from_quote


def detect_stop_trigger(tick: dict[str, Any], *, side: str, stop_loss: float) -> bool:
    """Trigger uses the monitoring side; missing opposite quote does not block trigger detection."""
    try:
        if side == "BUY":
            if tick.get("bid") is None:
                return False
            return float(tick["bid"]) <= float(stop_loss)
        if tick.get("ask") is None:
            return False
        return float(tick["ask"]) >= float(stop_loss)
    except Exception:
        return False


def detect_tp_touch(tick: dict[str, Any], *, side: str, take_profit: float) -> bool:
    try:
        if side == "BUY":
            if tick.get("bid") is None:
                return False
            return float(tick["bid"]) >= float(take_profit)
        if tick.get("ask") is None:
            return False
        return float(tick["ask"]) <= float(take_profit)
    except Exception:
        return False


def simulate_stop_exit(
    ticks: list[dict[str, Any]],
    *,
    side: str,
    stop_loss: float,
) -> dict[str, Any]:
    """First valid executable quote at/after trigger — not assumed equal to stop price."""
    trigger_i = None
    for i, t in enumerate(ticks):
        if detect_stop_trigger(t, side=side, stop_loss=stop_loss):
            trigger_i = i
            break
    if trigger_i is None:
        return {
            "triggered": False,
            "fill_price": None,
            "status": "NO_TRIGGER",
            "label": "HISTORICAL_QUOTE_BASED_SIMULATION",
        }
    # Prefer trigger tick if valid executable; else next valid
    fill_tick = None
    fill_i = None
    for j in range(trigger_i, len(ticks)):
        t = ticks[j]
        if t.get("bid") is None or t.get("ask") is None:
            continue
        try:
            if float(t["ask"]) < float(t["bid"]):
                continue
        except Exception:
            continue
        px = fill_from_quote(t, action=side, leg="EXIT")
        if px is None:
            continue
        fill_tick = t
        fill_i = j
        break
    if fill_tick is None:
        return {
            "triggered": True,
            "trigger_index": trigger_i,
            "fill_price": None,
            "status": "UNOBSERVABLE_EXECUTION_INTERVAL",
            "gap_through": None,
            "label": "HISTORICAL_QUOTE_BASED_SIMULATION",
            "broker_fill_behavior": "UNKNOWN",
        }
    fill = fill_from_quote(fill_tick, action=side, leg="EXIT")
    gap = abs(float(fill) - float(stop_loss)) if fill is not None else None
    at_stop = fill is not None and abs(float(fill) - float(stop_loss)) < 1e-12
    return {
        "triggered": True,
        "trigger_index": trigger_i,
        "fill_index": fill_i,
        "intended_sl": float(stop_loss),
        "fill_price": fill,
        "gap_through_amount": gap,
        "assumed_fill_at_stop_price": False,
        "filled_exactly_at_stop": at_stop,
        "executable_side": executable_side(action=side, leg="EXIT"),
        "status": "SIMULATED",
        "label": "HISTORICAL_QUOTE_BASED_SIMULATION",
        "broker_confirmed_fill": False,
        "broker_fill_behavior": "UNKNOWN",
        "unobservable_if_no_next_quote": False,
    }


def simulate_tp_exit(
    ticks: list[dict[str, Any]],
    *,
    side: str,
    take_profit: float,
    conservative_require_executable: bool = True,
) -> dict[str, Any]:
    """TP: distinguish touch from executable fill; conservative assumption documented."""
    touch_i = None
    for i, t in enumerate(ticks):
        if detect_tp_touch(t, side=side, take_profit=take_profit):
            touch_i = i
            break
    if touch_i is None:
        return {
            "touched": False,
            "filled": False,
            "status": "NO_TOUCH",
            "assumption": "CONSERVATIVE_TOUCH_NOT_EQUAL_LIMIT_FILL_WITHOUT_RULES",
        }
    if not conservative_require_executable:
        fill = fill_from_quote(ticks[touch_i], action=side, leg="EXIT")
        return {
            "touched": True,
            "filled": fill is not None,
            "fill_price": fill,
            "status": "TOUCH_AS_FILL_ASSUMED",
            "assumption": "LABELED_NON_CONSERVATIVE",
            "broker_confirmed_fill": False,
        }
    # Conservative: require executable quote at TP level on correct side (same as touch tick validity)
    fill = fill_from_quote(ticks[touch_i], action=side, leg="EXIT")
    # For limit TP, without broker rules we DO NOT assert guaranteed fill solely from touch;
    # we record touch and mark fill as SIMULATED_IF_EXECUTABLE_QUOTE_PRESENT with uncertainty.
    return {
        "touched": True,
        "touch_index": touch_i,
        "fill_price": fill,
        "filled_simulated": fill is not None,
        "status": "TOUCH_OBSERVED_FILL_UNCERTAIN",
        "assumption": (
            "Without broker-specific limit rules, Phase60 records TP touch and simulates "
            "exit at executable quote only as HISTORICAL_QUOTE_BASED_SIMULATION with uncertainty preserved"
        ),
        "broker_limit_rules": "UNKNOWN",
        "broker_confirmed_fill": False,
        "label": "HISTORICAL_QUOTE_BASED_SIMULATION",
    }


def same_bar_sl_before_tp(ticks: list[dict[str, Any]], *, side: str, sl: float, tp: float) -> dict[str, Any]:
    """Phase56 frozen priority: evaluate SL before TP within tick loop."""
    for i, t in enumerate(ticks):
        if detect_stop_trigger(t, side=side, stop_loss=sl):
            sim = simulate_stop_exit(ticks[i:], side=side, stop_loss=sl)
            return {"exit_reason": "STOP_LOSS", "tick_index": i, "simulation": sim, "policy": "SL_BEFORE_TP"}
        if detect_tp_touch(t, side=side, take_profit=tp):
            sim = simulate_tp_exit(ticks[i:], side=side, take_profit=tp)
            return {"exit_reason": "TAKE_PROFIT", "tick_index": i, "simulation": sim, "policy": "SL_BEFORE_TP"}
    return {"exit_reason": None, "policy": "SL_BEFORE_TP"}


def audit_phase56_behavior() -> dict[str, Any]:
    out = {
        "phase54_paper_exec": {
            "stop_fill": "Uses triggering tick executable side price (bid/ask), not forced to SL level",
            "gap_through_implicit": True,
            "broker_confirmed": False,
        },
        "phase56_lifecycle": {
            "monitors_sl_tp_before_horizon": True,
            "same_bar_priority": "SL evaluated before TP in tick loop",
            "adapter_only_in_phase60": True,
        },
        "phase60_changes_to_prior_phases": False,
        "broker_specific_fill_behavior": "UNKNOWN",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def build_sl_tp_cases() -> dict[str, Any]:
    """Synthetic deterministic cases — labeled fixtures, not historical evidence."""
    cases = []

    # Gap-through BUY stop: bid jumps from 100 to 98 with SL=99
    ticks = [
        {"timestamp_utc": "2025-01-01 00:00:01", "bid": 100.0, "ask": 100.2},
        {"timestamp_utc": "2025-01-01 00:00:02", "bid": 98.0, "ask": 98.2},
    ]
    sim = simulate_stop_exit(ticks, side="BUY", stop_loss=99.0)
    cases.append(
        {
            "name": "buy_stop_gap_through",
            "expect_gap_through": True,
            "expect_fill_at_sl": False,
            "result": sim,
            "pass": sim.get("fill_price") == 98.0 and (sim.get("gap_through_amount") or 0) >= 1.0,
        }
    )

    # Missing next quote after conceptual trigger on invalid tick
    ticks2 = [
        {"timestamp_utc": "2025-01-01 00:00:01", "bid": 100.0, "ask": 100.2},
        {"timestamp_utc": "2025-01-01 00:00:02", "bid": 98.0, "ask": None},
    ]
    sim2 = simulate_stop_exit(ticks2, side="BUY", stop_loss=99.0)
    cases.append(
        {
            "name": "unobservable_after_trigger",
            "result": sim2,
            "pass": sim2.get("status") == "UNOBSERVABLE_EXECUTION_INTERVAL",
        }
    )

    # TP touch without asserting broker limit fill certainty
    ticks3 = [
        {"timestamp_utc": "2025-01-01 00:00:01", "bid": 100.0, "ask": 100.2},
        {"timestamp_utc": "2025-01-01 00:00:02", "bid": 101.0, "ask": 101.2},
    ]
    sim3 = simulate_tp_exit(ticks3, side="BUY", take_profit=100.9)
    cases.append(
        {
            "name": "tp_touch_uncertainty_preserved",
            "result": sim3,
            "pass": sim3.get("status") == "TOUCH_OBSERVED_FILL_UNCERTAIN" and sim3.get("broker_limit_rules") == "UNKNOWN",
        }
    )

    # Same-bar SL before TP
    ticks4 = [
        {"timestamp_utc": "2025-01-01 00:00:01", "bid": 99.0, "ask": 99.2},  # hits SL for BUY entry~100
    ]
    sb = same_bar_sl_before_tp(ticks4, side="BUY", sl=99.5, tp=99.0)
    cases.append(
        {
            "name": "same_bar_sl_before_tp",
            "result": sb,
            "pass": sb.get("exit_reason") == "STOP_LOSS",
        }
    )

    # Crossed quote skipped
    ticks5 = [
        {"timestamp_utc": "2025-01-01 00:00:01", "bid": 100.0, "ask": 99.5},  # crossed — not trigger valid
        {"timestamp_utc": "2025-01-01 00:00:02", "bid": 98.0, "ask": 98.2},
    ]
    sim5 = simulate_stop_exit(ticks5, side="BUY", stop_loss=99.0)
    cases.append(
        {
            "name": "skip_crossed_then_fill",
            "result": sim5,
            "pass": sim5.get("fill_price") == 98.0,
        }
    )

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "fixture_label": "SYNTHETIC_NOT_HISTORICAL_EVIDENCE",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
