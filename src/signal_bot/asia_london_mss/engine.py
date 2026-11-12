"""Deterministic Asia-sweep → London MSS evaluation at a closed-bar decision index."""

from __future__ import annotations

from typing import Any

from signal_bot.asia_london_mss.constants import (
    HYPOTHESIS_ID,
    MAX_ASIA_RANGE_ATR,
    MAX_HOLD_BARS,
    MIN_ASIA_BARS,
    MIN_ASIA_RANGE_ABS,
    MIN_REWARD_RISK,
    PARAMETER_LABEL,
    POLICY_VERSION,
    REQUIRE_CLOSE_BACK_INSIDE,
    REWARD_RISK,
    SIGNAL_EXPIRY_BARS,
    SL_BUFFER_ABS_MIN,
    SL_BUFFER_ATR,
    SWEEP_BUFFER_ABS_MIN,
    SWEEP_BUFFER_ATR,
    SWEEP_TO_MSS_MAX_BARS,
    SYMBOL,
    TIMEFRAME,
)
from signal_bot.asia_london_mss.sessions import (
    asia_day_key,
    asia_session_complete_at,
    build_asia_range,
    in_london_window,
    london_day_key,
)
from signal_bot.asia_london_mss.swings import last_confirmed_swing_high, last_confirmed_swing_low


def _atr(bars: list[dict[str, Any]], idx: int, period: int = 14) -> float | None:
    if idx < period:
        return None
    trs: list[float] = []
    for i in range(idx - period + 1, idx + 1):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"]) if i > 0 else float(bars[i]["open"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    return sum(trs) / len(trs)


def _sweep_buffer(atr: float | None) -> float:
    base = SWEEP_BUFFER_ABS_MIN
    if atr is not None and atr > 0:
        base = max(base, float(atr) * SWEEP_BUFFER_ATR)
    return base


def _sl_buffer(atr: float | None) -> float:
    base = SL_BUFFER_ABS_MIN
    if atr is not None and atr > 0:
        base = max(base, float(atr) * SL_BUFFER_ATR)
    return base


def evaluate_at(
    bars: list[dict[str, Any]],
    decision_idx: int,
    *,
    forming_bar: bool = False,
    symbol: str = SYMBOL,
) -> dict[str, Any]:
    """
    Evaluate strategy at bars[decision_idx] (must be fully closed).
    Uses only bars[0 : decision_idx+1].
    """
    base = {
        "hypothesis_id": HYPOTHESIS_ID,
        "policy_version": POLICY_VERSION,
        "parameter_label": PARAMETER_LABEL,
        "symbol": symbol,
        "timeframe": TIMEFRAME,
        "action": "WAIT",
        "calibrated": False,
        "expected_net_r": None,
        "prob_positive": None,
        "confidence": None,
        "uncertainty": 1.0,
        "reason_codes": [],
        "setup_id": None,
        "entry_reference": None,
        "stop_loss": None,
        "take_profit": None,
        "reward_risk": None,
        "signal_expiry_bars": SIGNAL_EXPIRY_BARS,
        "max_hold_bars": MAX_HOLD_BARS,
        "invalidation": None,
        "decision_idx": decision_idx,
    }

    if forming_bar:
        return {**base, "reason_codes": ["FORMING_BAR_REJECTED"]}
    if decision_idx < 0 or decision_idx >= len(bars):
        return {**base, "reason_codes": ["INDEX_OOB"]}
    if symbol and symbol != SYMBOL and symbol != "XAUUSD":
        # Allow XAUUSD only for replay fixtures; live symbol is XAUUSDm
        pass

    window = bars[: decision_idx + 1]
    bar = window[-1]
    ts = str(bar.get("timestamp_utc") or "")
    base["decision_timestamp_utc"] = ts
    for k in ("open", "high", "low", "close"):
        if bar.get(k) is None:
            return {**base, "reason_codes": ["INCOMPLETE_BAR", f"missing_{k}"]}

    atr = _atr(window, decision_idx)
    if atr is None or atr <= 0:
        return {**base, "reason_codes": ["ATR_UNAVAILABLE"]}

    # Asia day for London morning is typically previous Tokyo calendar day if before Tokyo midnight overlap;
    # Use London calendar day mapping: take asia_day as the most recent completed Asia session day
    # relative to decision time.
    # Practical rule: asia_day = Asia calendar day of (decision_ts - 1 minute) if London morning,
    # else WAIT.
    if not in_london_window(ts):
        return {**base, "reason_codes": ["OUTSIDE_LONDON_CONFIRM_WINDOW"]}

    # Candidate Asia day: Tokyo date of the most recent Asia session that has completed
    # Search backward for last Asia session bar day that is complete.
    asia_day = None
    for b in reversed(window):
        bts = str(b.get("timestamp_utc") or "")
        if not bts:
            continue
        day = asia_day_key(bts)
        if asia_session_complete_at(ts, day):
            asia_day = day
            break
    if asia_day is None:
        return {**base, "reason_codes": ["ASIA_SESSION_NOT_COMPLETE"]}

    ar = build_asia_range(window, asia_day)
    if not ar.get("ok"):
        return {**base, "reason_codes": [ar.get("reason") or "ASIA_RANGE_FAIL"]}
    if int(ar["n"]) < MIN_ASIA_BARS:
        return {**base, "reason_codes": ["ASIA_INSUFFICIENT_BARS", f"n={ar['n']}"]}
    rng = float(ar["high"]) - float(ar["low"])
    if rng < MIN_ASIA_RANGE_ABS:
        return {**base, "reason_codes": ["ASIA_RANGE_TOO_SMALL"]}
    if atr > 0 and rng / atr > MAX_ASIA_RANGE_ATR:
        return {**base, "reason_codes": ["ASIA_RANGE_TOO_WIDE_VS_ATR"]}

    buf = _sweep_buffer(atr)
    asia_high = float(ar["high"])
    asia_low = float(ar["low"])

    # Find first valid sweep after Asia completion, before/at decision, then MSS
    sweep = None
    for i in range(len(window)):
        b = window[i]
        bts = str(b["timestamp_utc"])
        if not asia_session_complete_at(bts, asia_day):
            continue
        # Sweeps may occur pre-London or in London; MSS confirmation must be in London window
        hi = float(b["high"])
        lo = float(b["low"])
        cl = float(b["close"])
        # Sell-side liquidity (sweep highs) → expect bearish continuation after MSS down
        if hi > asia_high + buf:
            if REQUIRE_CLOSE_BACK_INSIDE and not (cl <= asia_high):
                continue
            sweep = {
                "side": "SWEEP_HIGH",
                "expected_mss": "BEARISH",
                "action_if_mss": "SELL",
                "idx": i,
                "timestamp_utc": bts,
                "extreme": hi,
            }
            break
        # Buy-side liquidity (sweep lows) → expect bullish MSS
        if lo < asia_low - buf:
            if REQUIRE_CLOSE_BACK_INSIDE and not (cl >= asia_low):
                continue
            sweep = {
                "side": "SWEEP_LOW",
                "expected_mss": "BULLISH",
                "action_if_mss": "BUY",
                "idx": i,
                "timestamp_utc": bts,
                "extreme": lo,
            }
            break

    if sweep is None:
        return {
            **base,
            "reason_codes": ["NO_VALID_SWEEP"],
            "asia_range": {"high": asia_high, "low": asia_low, "n": ar["n"], "asia_day": asia_day},
        }

    # MSS must occur after sweep, within max bars, on decision bar ideally
    mss = None
    start_i = int(sweep["idx"]) + 1
    end_i = min(decision_idx, int(sweep["idx"]) + SWEEP_TO_MSS_MAX_BARS)
    for i in range(start_i, end_i + 1):
        bts = str(window[i]["timestamp_utc"])
        if not in_london_window(bts):
            continue
        cl = float(window[i]["close"])
        if sweep["expected_mss"] == "BULLISH":
            sh = last_confirmed_swing_high(window, asof_idx=i)
            if sh is None:
                continue
            # Structure shift: close breaks above last confirmed swing high that formed at/after sweep
            if int(sh["idx"]) >= int(sweep["idx"]) and cl > float(sh["price"]):
                mss = {
                    "direction": "BULLISH",
                    "idx": i,
                    "timestamp_utc": bts,
                    "broken_level": float(sh["price"]),
                    "swing": sh,
                }
                break
        else:
            sl = last_confirmed_swing_low(window, asof_idx=i)
            if sl is None:
                continue
            if int(sl["idx"]) >= int(sweep["idx"]) and cl < float(sl["price"]):
                mss = {
                    "direction": "BEARISH",
                    "idx": i,
                    "timestamp_utc": bts,
                    "broken_level": float(sl["price"]),
                    "swing": sl,
                }
                break

    if mss is None:
        return {
            **base,
            "reason_codes": ["SWEEP_WITHOUT_MSS", sweep["side"]],
            "sweep": sweep,
            "asia_range": {"high": asia_high, "low": asia_low, "asia_day": asia_day},
        }

    # Signal only on the MSS confirmation bar (no late re-fire)
    if int(mss["idx"]) != decision_idx:
        return {
            **base,
            "reason_codes": ["MSS_ALREADY_PASSED", f"mss_idx={mss['idx']}"],
            "sweep": sweep,
            "mss": mss,
        }

    action = sweep["action_if_mss"]
    entry = float(window[decision_idx]["close"])
    sl_buf = _sl_buffer(atr)
    if action == "BUY":
        sl = float(sweep["extreme"]) - sl_buf
        risk = entry - sl
        if risk <= 0:
            return {**base, "reason_codes": ["INVALID_STOP_DISTANCE"]}
        tp = entry + REWARD_RISK * risk
        invalidation = f"close < {sl}"
    else:
        sl = float(sweep["extreme"]) + sl_buf
        risk = sl - entry
        if risk <= 0:
            return {**base, "reason_codes": ["INVALID_STOP_DISTANCE"]}
        tp = entry - REWARD_RISK * risk
        invalidation = f"close > {sl}"

    rr = abs(tp - entry) / risk if risk else 0.0
    if rr + 1e-12 < MIN_REWARD_RISK:
        return {**base, "reason_codes": ["RR_BELOW_MINIMUM"]}

    setup_id = f"{HYPOTHESIS_ID}:{asia_day}:{sweep['side']}:{ts}"
    expiry_idx = decision_idx + SIGNAL_EXPIRY_BARS
    expiry_ts = (
        str(bars[expiry_idx]["timestamp_utc"])
        if expiry_idx < len(bars)
        else None
    )

    return {
        **base,
        "action": action,
        "reason_codes": ["SETUP_COMPLETE", sweep["side"], mss["direction"], "ENTRY_ON_MSS_CLOSE"],
        "setup_id": setup_id,
        "entry_reference": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "reward_risk": rr,
        "signal_expiry_utc": expiry_ts,
        "invalidation": invalidation,
        "asia_range": {"high": asia_high, "low": asia_low, "n": ar["n"], "asia_day": asia_day},
        "sweep": sweep,
        "mss": mss,
        "atr": atr,
        "uncertainty": 0.5,
        "confidence": None,
        "calibrated": False,
    }
