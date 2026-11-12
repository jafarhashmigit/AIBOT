"""Causal Phase44 features for the five primary hypotheses."""

from __future__ import annotations

import math
from typing import Any

from phase35.features import _wilder_atr


def _pctile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = int(math.floor(k)), int(math.ceil(k))
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def build_feature_rows(
    bars: list[dict[str, Any]],
    h1_bars: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]] | None,
    *,
    prev_day_bars: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not bars:
        return []
    opens = [float(b["open"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    times = [b["timestamp_utc"] for b in bars]
    atr = _wilder_atr(highs, lows, closes, 14)

    prev_hi = prev_lo = None
    if prev_day_bars:
        prev_hi = max(float(b["high"]) for b in prev_day_bars)
        prev_lo = min(float(b["low"]) for b in prev_day_bars)

    rows: list[dict[str, Any]] = []
    accel_bars = 0
    vol_was_low = False
    for i, t in enumerate(times):
        a = atr[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        disp = c - o
        disp_atr = (abs(disp) / a) if a else None
        disp_sign = 1 if disp > 0 else (-1 if disp < 0 else 0)
        # close location in bar: 1 near high, -1 near low
        br = h - l
        close_loc = None
        if br > 0:
            close_loc = (c - l) / br  # 0..1
        close_aligned = False
        if close_loc is not None:
            close_aligned = (disp_sign > 0 and close_loc >= 0.75) or (disp_sign < 0 and close_loc <= 0.25)

        mom_3 = (c - closes[i - 3]) if i >= 3 else None
        mom_3_lag3 = (closes[i - 3] - closes[i - 6]) if i >= 6 else None
        if mom_3 is not None and mom_3_lag3 is not None and a:
            if abs(mom_3) > abs(mom_3_lag3) and (mom_3 * mom_3_lag3) > 0:
                accel_bars += 1
            else:
                accel_bars = 0
        else:
            accel_bars = 0

        atr_pct = (a / c) if a and c else None
        vol_p40 = vol_p60 = None
        transition_up = False
        if atr_pct is not None and i >= 47:
            window = []
            for j in range(i - 47, i + 1):
                aj = atr[j]
                if aj and closes[j]:
                    window.append(aj / closes[j])
            vol_p40 = _pctile(window, 40)
            vol_p60 = _pctile(window, 60)
            # look back up to 3 bars for crossing from below p40 to above p60
            if vol_p40 is not None and vol_p60 is not None and atr_pct >= vol_p60:
                for k in range(1, 4):
                    if i - k < 0:
                        break
                    ap = atr[i - k]
                    if ap and closes[i - k]:
                        prev_pct = ap / closes[i - k]
                        if prev_pct <= vol_p40:
                            transition_up = True
                            break

        # prev day pierce/reject
        pierce_high = pierce_low = False
        if prev_hi is not None and prev_lo is not None and a:
            if h > prev_hi and c <= prev_hi - 0.3 * a:
                pierce_high = True
            if l < prev_lo and c >= prev_lo + 0.3 * a:
                pierce_low = True

        # tick spread
        tick_imbalance = None
        spread_med = None
        n_ticks = 0
        if ticks_by_bar is not None:
            tks = ticks_by_bar.get(t) or []
            n_ticks = len(tks)
            if n_ticks >= 2:
                spreads = [tk["ask"] - tk["bid"] for tk in tks]
                spread_med = _pctile(spreads, 50)

        # causal spread p30 so far today
        spread_p30 = None
        day_spreads = [r["spread_median_bar"] for r in rows if r["day"] == t[:10] and r.get("spread_median_bar") is not None]
        if spread_med is not None:
            day_spreads = day_spreads + [spread_med]
            spread_p30 = _pctile(day_spreads, 30)

        rows.append(
            {
                "time": t,
                "day": t[:10],
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "atr_14": a,
                "atr_14_pct": atr_pct,
                "bar_disp_atr": disp_atr,
                "disp_sign": disp_sign,
                "close_location": close_loc,
                "close_aligned": close_aligned,
                "mom_3": mom_3,
                "mom_3_lag3": mom_3_lag3,
                "accel_bars": accel_bars,
                "vol_p40": vol_p40,
                "vol_p60": vol_p60,
                "transition_up": transition_up,
                "prev_day_high": prev_hi,
                "prev_day_low": prev_lo,
                "pierce_high": pierce_high,
                "pierce_low": pierce_low,
                "spread_median_bar": spread_med,
                "spread_p30_so_far": spread_p30,
                "n_ticks_bar": n_ticks,
                "tick_imbalance": tick_imbalance,
            }
        )
    return rows
