"""Deterministic synthetic M5 candles and events for Phase 19 validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from phase18.barrier import BUY, SELL, market_arrays_from_bars, simulate_trade_horizon
from phase18.constants import ATR_PERIOD, HORIZONS, SL_ATR_MULTIPLE, TP_ATR_MULTIPLE
from phase18.outcomes import atr_at_signal
from phase19.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    SOURCE_SYNTHETIC,
    STRATEGY_ID,
    SYMBOL,
    TIMEFRAME,
)

UTC = timezone.utc
ScenarioKind = Literal["BUY_PASS", "BUY_FAIL", "SELL_PASS", "SELL_FAIL", "TIMEOUT"]

# Fixed synthetic timeline (UTC). Signal bar open is always index 20.
SIGNAL_OPEN = "2026-11-09 12:00:00"
BASE_PRICE = 2650.0
HISTORY_BARS = 40  # enough for ATR(14) + 12-bar horizon + margin


def _bar(open_utc: str, o: float, h: float, l: float, c: float, spread: float = 20.0) -> dict[str, Any]:
    close_dt = datetime.strptime(open_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) + timedelta(minutes=5)
    return {
        "bar_open_timestamp_utc": open_utc,
        "bar_close_timestamp_utc": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "spread": float(spread),
        "tick_volume": 100,
        "data_source": SOURCE_SYNTHETIC,
        "source_timezone": "UTC",
        "conversion": "already_utc",
        "source_stamp": open_utc,
    }


def build_flat_history(
    *,
    n: int = HISTORY_BARS,
    start: str = "2026-11-09 10:20:00",
    base: float = BASE_PRICE,
) -> list[dict[str, Any]]:
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    bars: list[dict[str, Any]] = []
    px = base
    for i in range(n):
        ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        # mild oscillation so ATR is positive and stable
        delta = 0.35 if i % 2 == 0 else -0.25
        o = px
        c = px + delta
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        bars.append(_bar(ts, o, h, l, c))
        px = c
    return bars


def signal_index(bars: list[dict[str, Any]], signal_open: str = SIGNAL_OPEN) -> int:
    opens = [b["bar_open_timestamp_utc"] for b in bars]
    return opens.index(signal_open)


def apply_scenario_path(
    bars: list[dict[str, Any]],
    *,
    signal_idx: int,
    atr: float,
    kind: ScenarioKind,
    horizon_bars: int = 12,
) -> list[dict[str, Any]]:
    """Mutate post-signal bars for a deterministic TP/SL/TIMEOUT path."""
    out = [dict(b) for b in bars]
    entry = signal_idx + 1
    # Anchor entry open near signal close for stable fills
    entry_open = float(out[signal_idx]["close"])
    out[entry]["open"] = entry_open

    tp_dist = TP_ATR_MULTIPLE * atr
    sl_dist = SL_ATR_MULTIPLE * atr

    # Default: keep path quiet for TIMEOUT; override per kind
    for k in range(entry, min(entry + horizon_bars, len(out))):
        out[k]["open"] = entry_open if k == entry else float(out[k - 1]["close"])
        out[k]["high"] = out[k]["open"] + 0.05
        out[k]["low"] = out[k]["open"] - 0.05
        out[k]["close"] = out[k]["open"]

    if kind == "BUY_PASS":
        # BUY: lift high through TP on first horizon bar; keep low above SL
        out[entry]["low"] = entry_open - min(0.05, sl_dist * 0.1)
        out[entry]["high"] = entry_open + tp_dist + atr
        out[entry]["close"] = entry_open + tp_dist * 0.5
    elif kind == "BUY_FAIL":
        out[entry]["high"] = entry_open + min(0.05, tp_dist * 0.1)
        out[entry]["low"] = entry_open - sl_dist - atr
        out[entry]["close"] = entry_open - sl_dist * 0.5
    elif kind == "SELL_PASS":
        # SELL TP is below entry; push low through TP; keep high below SL
        out[entry]["high"] = entry_open + min(0.05, sl_dist * 0.1)
        out[entry]["low"] = entry_open - tp_dist - atr
        out[entry]["close"] = entry_open - tp_dist * 0.5
    elif kind == "SELL_FAIL":
        out[entry]["low"] = entry_open - min(0.05, tp_dist * 0.1)
        out[entry]["high"] = entry_open + sl_dist + atr
        out[entry]["close"] = entry_open + sl_dist * 0.5
    elif kind == "TIMEOUT":
        pass  # already quiet path
    else:
        raise ValueError(f"unknown scenario kind: {kind}")
    return out


def scenario_side(kind: ScenarioKind) -> str:
    if kind.startswith("BUY"):
        return "BUY"
    if kind.startswith("SELL"):
        return "SELL"
    return "BUY"  # TIMEOUT tested on BUY by default


def make_decision(
    *,
    kind: ScenarioKind,
    bars: list[dict[str, Any]],
    signal_idx: int,
    atr: float,
) -> dict[str, Any]:
    side = scenario_side(kind)
    bar = bars[signal_idx]
    decision_id = f"p19_synth_{kind.lower()}_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}"
    return {
        "decision_id": decision_id,
        "observation_id": f"p19_obs_{kind.lower()}_{bar['bar_open_timestamp_utc'].replace(' ', 'T')}",
        "source_type": SOURCE_SYNTHETIC,
        "decision_timestamp_utc": bar["bar_close_timestamp_utc"],
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "model_id": "no_model",
        "model_status": CHAMPION_STATUS,
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
        "experimental_action": side if kind != "TIMEOUT" else "BUY",
        "raw_action": side if kind != "TIMEOUT" else "BUY",
        "risk_gate_result": "ALLOW",
        "final_action": "WAIT",
        "decision_reason": f"phase19 synthetic {kind}",
        "feature_snapshot_json": "{}",
        "selected_horizon": "NOT ESTABLISHED",
        "outcome_status": "pending_multi_horizon",
        "signal_bar_open_utc": bar["bar_open_timestamp_utc"],
        "atr": f"{atr:.8f}",
        "tp_level": "",
        "sl_level": "",
        "is_paper_trade": False,
        "is_paper_execution": False,
        "strategy": STRATEGY_ID,
        "synthetic": True,
        "synthetic_namespace": SOURCE_SYNTHETIC,
        "scenario_kind": kind,
        "note": "PHASE19_SYNTHETIC_TEST; not live; production WAIT",
    }


def make_observation(decision: dict[str, Any], bar: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": decision["observation_id"],
        "source_type": SOURCE_SYNTHETIC,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
        "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
        "observation_created_at_utc": bar["bar_close_timestamp_utc"],
        "open": bar["open"],
        "high": bar["high"],
        "low": bar["low"],
        "close": bar["close"],
        "tick_volume": bar.get("tick_volume", 100),
        "spread": bar.get("spread", 20.0),
        "data_source": SOURCE_SYNTHETIC,
        "data_quality_status": "ok",
        "gap_status": "continuous",
        "model_status": CHAMPION_STATUS,
        "decision_id": decision["decision_id"],
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
        "synthetic": True,
        "synthetic_namespace": SOURCE_SYNTHETIC,
    }


def build_scenario(kind: ScenarioKind, *, horizon_bars: int = 12) -> dict[str, Any]:
    """Return a fully deterministic scenario package."""
    base = build_flat_history()
    # Ensure SIGNAL_OPEN exists in series
    idx = signal_index(base)
    atr = atr_at_signal(base, idx, period=ATR_PERIOD)
    path = apply_scenario_path(base, signal_idx=idx, atr=atr, kind=kind, horizon_bars=horizon_bars)
    # Recompute ATR on (pre-mutation history is identical through signal)
    atr2 = atr_at_signal(path, idx, period=ATR_PERIOD)
    decision = make_decision(kind=kind, bars=path, signal_idx=idx, atr=atr2)
    observation = make_observation(decision, path[idx])
    side_int = BUY if decision["experimental_action"] == "BUY" else SELL
    m = market_arrays_from_bars(path)
    # Reference trade at H12 for expected realized R under this path shape
    ref = simulate_trade_horizon(m, side_int, idx, atr2, horizon_bars=horizon_bars)
    return {
        "kind": kind,
        "bars": path,
        "signal_idx": idx,
        "atr": atr2,
        "decision": decision,
        "observation": observation,
        "reference_trade": ref,
        "horizons": dict(HORIZONS),
    }


def expected_status_for_kind(kind: ScenarioKind) -> str:
    if kind.endswith("PASS"):
        return "PASS"
    if kind.endswith("FAIL"):
        return "FAIL"
    return "TIMEOUT"
