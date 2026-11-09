"""Independent per-horizon pending outcome evaluation."""

from __future__ import annotations

from typing import Any

from phase18.barrier import (
    market_arrays_from_bars,
    side_to_int,
    simulate_trade_horizon,
    wilder_atr,
)
from phase18.constants import (
    ATR_PERIOD,
    BAR_MINUTES,
    HORIZONS,
    OUTCOME_FAIL,
    OUTCOME_N_A_WAIT,
    OUTCOME_PASS,
    OUTCOME_PENDING,
    OUTCOME_TIMEOUT,
    SL_ATR_MULTIPLE,
    TP_ATR_MULTIPLE,
)
from phase18.horizons import expected_outcome_check_utc, horizon_label, parse_utc


def outcome_event_id(decision_id: str, horizon_id: str) -> str:
    return f"{decision_id}__{horizon_id}"


def create_pending_outcomes(
    decision: dict[str, Any],
    *,
    atr: float | None = None,
    tp_level: float | None = None,
    sl_level: float | None = None,
) -> list[dict[str, Any]]:
    """Create independent PENDING records for every horizon. WAIT → none."""
    action = str(decision.get("experimental_action", "WAIT")).upper()
    if action not in {"BUY", "SELL"}:
        return []
    decision_id = decision["decision_id"]
    close_ts = decision["decision_timestamp_utc"]
    rows: list[dict[str, Any]] = []
    for hid, bars in HORIZONS.items():
        rows.append(
            {
                "outcome_event_id": outcome_event_id(decision_id, hid),
                "decision_id": decision_id,
                "horizon_id": hid,
                "horizon_label": horizon_label(hid),
                "horizon_bars": bars,
                "side": action,
                "symbol": decision.get("symbol", "XAUUSD"),
                "decision_timestamp_utc": close_ts,
                "expected_check_utc": expected_outcome_check_utc(close_ts, hid),
                "status": OUTCOME_PENDING,
                "exit_reason": "",
                "realized_r": "",
                "net_pnl": "",
                "costs": "",
                "atr": "" if atr is None else f"{atr:.8f}",
                "tp_level": "" if tp_level is None else f"{tp_level:.8f}",
                "sl_level": "" if sl_level is None else f"{sl_level:.8f}",
                "entry_fill": "",
                "exit_fill": "",
                "exit_timestamp_utc": "",
                "outcome_timestamp_utc": "",
                "discord_notified": "0",
                "experience_recorded": "0",
                "note": "independent multi-horizon pending; not guaranteed TP/SL timing",
            }
        )
    return rows


def map_exit_to_state(exit_reason: str) -> str:
    reason = str(exit_reason).upper()
    if reason == "TP":
        return OUTCOME_PASS
    if reason == "SL":
        return OUTCOME_FAIL
    if reason == "TIME":
        return OUTCOME_TIMEOUT
    return OUTCOME_PENDING


def window_ready(
    signal_bar_open_utc: str,
    subsequent_or_full_bars: list[dict[str, Any]],
    horizon_bars: int,
) -> tuple[bool, int, int]:
    """Return (ready, signal_pos, needed_last_pos) within full ascending bar list."""
    opens = [b["bar_open_timestamp_utc"] for b in subsequent_or_full_bars]
    try:
        signal_pos = opens.index(signal_bar_open_utc)
    except ValueError:
        # Allow matching by close timestamp if open not found
        closes = [b.get("bar_close_timestamp_utc") for b in subsequent_or_full_bars]
        if signal_bar_open_utc in closes:
            signal_pos = closes.index(signal_bar_open_utc)
        else:
            return False, -1, -1
    entry_pos = signal_pos + 1
    last_pos = entry_pos + horizon_bars - 1
    if last_pos >= len(subsequent_or_full_bars):
        return False, signal_pos, last_pos
    # Contiguous M5 check for entry
    try:
        sig = parse_utc(subsequent_or_full_bars[signal_pos]["bar_open_timestamp_utc"])
        ent = parse_utc(subsequent_or_full_bars[entry_pos]["bar_open_timestamp_utc"])
        if (ent - sig).total_seconds() != BAR_MINUTES * 60:
            return False, signal_pos, last_pos
    except Exception:
        return False, signal_pos, last_pos
    return True, signal_pos, last_pos


def evaluate_horizon_outcome(
    pending: dict[str, Any],
    *,
    bars: list[dict[str, Any]],
    signal_bar_open_utc: str,
    atr: float,
    as_of_utc: str,
) -> dict[str, Any]:
    """Evaluate one pending horizon using available M5 bars. Idempotent finalize."""
    if pending.get("status") and pending["status"] != OUTCOME_PENDING:
        return dict(pending)
    if str(pending.get("side", "")).upper() not in {"BUY", "SELL"}:
        out = dict(pending)
        out["status"] = OUTCOME_N_A_WAIT
        return out

    horizon_bars = int(pending["horizon_bars"])
    ready, signal_pos, _ = window_ready(signal_bar_open_utc, bars, horizon_bars)
    if not ready:
        out = dict(pending)
        out["status"] = OUTCOME_PENDING
        return out

    # Eligibility also requires as_of past expected check (candle availability primary)
    expected = pending.get("expected_check_utc") or expected_outcome_check_utc(
        pending["decision_timestamp_utc"], pending["horizon_id"]
    )
    if parse_utc(as_of_utc) < parse_utc(expected):
        # Still allow if bars already present (candle-based), but prefer bar readiness
        pass

    m = market_arrays_from_bars(bars)
    trade = simulate_trade_horizon(
        m,
        side_to_int(pending["side"]),
        signal_pos,
        float(atr),
        horizon_bars=horizon_bars,
    )
    state = map_exit_to_state(trade["exit_reason"])
    exit_ts = str(trade["exit_time"]).replace("T", " ")[:19]
    out = dict(pending)
    out.update(
        {
            "status": state,
            "exit_reason": trade["exit_reason"],
            "realized_r": f"{trade['net_pnl_r']:.8f}",
            "net_pnl": f"{trade['net_pnl']:.8f}",
            "costs": f"{trade['costs']:.8f}",
            "atr": f"{trade['atr']:.8f}",
            "tp_level": f"{trade['tp_level']:.8f}",
            "sl_level": f"{trade['sl_level']:.8f}",
            "entry_fill": f"{trade['entry_fill']:.8f}",
            "exit_fill": f"{trade['exit_fill']:.8f}",
            "exit_timestamp_utc": exit_ts,
            "outcome_timestamp_utc": as_of_utc,
            "note": (
                f"cost-aware triple-barrier H={horizon_bars}; "
                f"TP={TP_ATR_MULTIPLE}xATR SL={SL_ATR_MULTIPLE}xATR; "
                f"same-candle SL before TP"
            ),
        }
    )
    return out


def atr_at_signal(bars: list[dict[str, Any]], signal_pos: int, period: int = ATR_PERIOD) -> float:
    end = signal_pos + 1
    start = end - (period + 1)
    if start < 0:
        raise ValueError("not enough history for ATR at signal")
    window = bars[start:end]
    highs = [float(b["high"]) for b in window]
    lows = [float(b["low"]) for b in window]
    closes = [float(b["close"]) for b in window]
    return wilder_atr(highs, lows, closes, period=period)
