"""Causal Phase42 features — deterministic, no look-ahead, missing stays missing."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from phase35.features import _ema_series, _wilder_atr, build_h1_series, h1_trend_at


def _pctile(vals: list[float], p: float) -> float | None:
    import math

    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def build_feature_rows(
    bars: list[dict[str, Any]],
    h1_bars: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """One feature row per completed M5 bar. All inputs causal at bar close."""
    if not bars:
        return []
    opens = [float(b["open"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    times = [b["timestamp_utc"] for b in bars]
    atr = _wilder_atr(highs, lows, closes, 14)
    ema9 = _ema_series(closes, 9)
    ema20 = _ema_series(closes, 20)

    h1_rows = [{"time": b["timestamp_utc"], "close": float(b["close"])} for b in sorted(h1_bars, key=lambda x: int(x["time_epoch"]))]
    h1_series = build_h1_series(h1_rows)

    # Asia session high/low accumulating within day (UTC 00–07)
    asia_hi: float | None = None
    asia_lo: float | None = None
    asia_mid: float | None = None
    day = times[0][:10] if times else ""

    rows: list[dict[str, Any]] = []
    compress_run = 0
    up_run = down_run = 0

    for i, t in enumerate(times):
        a = atr[i]
        c, o, h, l = closes[i], opens[i], highs[i], lows[i]
        hour = int(t[11:13])
        sess_asia = int(0 <= hour < 7)
        sess_london = int(7 <= hour < 12)
        sess_ny = int(12 <= hour < 21)

        # Asia range — only update during Asia; freeze afterward for the day
        if t[:10] != day:
            day = t[:10]
            asia_hi = asia_lo = asia_mid = None
        if sess_asia:
            asia_hi = h if asia_hi is None else max(asia_hi, h)
            asia_lo = l if asia_lo is None else min(asia_lo, l)
            if asia_hi is not None and asia_lo is not None:
                asia_mid = 0.5 * (asia_hi + asia_lo)

        atr_pct = (a / c) if a and c else None
        bar_range = h - l
        body = abs(c - o)
        upper_wick = h - max(c, o)
        lower_wick = min(c, o) - l
        disp = c - o
        disp_atr = (disp / a) if a else None
        bar_disp_atr = (abs(disp) / a) if a else None

        # wick reject strength relative to ATR
        wick_up = (upper_wick / a) if a else None
        wick_dn = (lower_wick / a) if a else None

        # efficiency over 20 bars: net move / path
        efficiency_20 = None
        if i >= 19 and a:
            path = sum(abs(closes[j] - closes[j - 1]) for j in range(i - 18, i + 1))
            net = abs(closes[i] - closes[i - 19])
            efficiency_20 = (net / path) if path > 0 else None

        efficiency_12 = None
        if i >= 11:
            path = sum(abs(closes[j] - closes[j - 1]) for j in range(i - 10, i + 1))
            net = abs(closes[i] - closes[i - 11])
            efficiency_12 = (net / path) if path > 0 else None

        # compression: bar_range < 0.7 ATR
        if a and bar_range < 0.7 * a:
            compress_run += 1
        else:
            compress_run = 0

        # directional runs on closes
        if i > 0:
            if closes[i] > closes[i - 1]:
                up_run += 1
                down_run = 0
            elif closes[i] < closes[i - 1]:
                down_run += 1
                up_run = 0
            else:
                up_run = down_run = 0

        # rolling ATR pct distribution for regime (causal window 48)
        vol_regime = None
        rolling_p30 = rolling_p70 = None
        if atr_pct is not None and i >= 47:
            window = []
            for j in range(i - 47, i + 1):
                aj = atr[j]
                if aj and closes[j]:
                    window.append(aj / closes[j])
            rolling_p30 = _pctile(window, 30)
            rolling_p70 = _pctile(window, 70)
            if rolling_p70 is not None and atr_pct >= rolling_p70:
                vol_regime = "high"
            elif rolling_p30 is not None and atr_pct <= rolling_p30:
                vol_regime = "low"
            else:
                vol_regime = "mid"

        # range 20
        range_high_20 = max(highs[i - 19 : i + 1]) if i >= 19 else None
        range_low_20 = min(lows[i - 19 : i + 1]) if i >= 19 else None
        range_width_atr = ((range_high_20 - range_low_20) / a) if (range_high_20 is not None and a) else None

        # session high/low so far today (UTC day)
        day_mask = [j for j in range(0, i + 1) if times[j][:10] == t[:10]]
        session_high = max(highs[j] for j in day_mask) if day_mask else None
        session_low = min(lows[j] for j in day_mask) if day_mask else None

        # prior bars for sweep: use previous completed hour extremes approx via last 12 bars excl current
        sweep_high = sweep_low = False
        reject_close = False
        if i >= 12 and a and session_high is not None and session_low is not None:
            prior_hi = max(highs[i - 12 : i])
            prior_lo = min(lows[i - 12 : i])
            if h > prior_hi and c < prior_hi - 0.25 * a:
                sweep_high = True
                reject_close = True
            if l < prior_lo and c > prior_lo + 0.25 * a:
                sweep_low = True
                reject_close = True

        mom_3 = (closes[i] - closes[i - 3]) if i >= 3 else None
        mom_6 = (closes[i] - closes[i - 6]) if i >= 6 else None
        m5_mom_6_atr = (mom_6 / a) if (mom_6 is not None and a) else None

        e9, e20 = ema9[i], ema20[i]
        ema_9_20_spread = ((e9 - e20) / e20) if (e9 is not None and e20) else None

        h1_ctx = h1_trend_at(h1_series, t)
        h1_trend = (h1_ctx or {}).get("h1_trend")

        disagree = None
        if h1_trend in ("up", "down") and m5_mom_6_atr is not None:
            m5_sign = 1 if m5_mom_6_atr > 0 else (-1 if m5_mom_6_atr < 0 else 0)
            h1_sign = 1 if h1_trend == "up" else -1
            disagree = int(m5_sign != 0 and m5_sign != h1_sign)

        dist_asia_mid_atr = None
        if asia_mid is not None and a:
            dist_asia_mid_atr = (c - asia_mid) / a

        # tick imbalance on THIS bar's ticks (completed bar — available at close)
        tick_imbalance = None
        spread_med = None
        n_ticks = 0
        if ticks_by_bar is not None:
            tks = ticks_by_bar.get(t) or []
            n_ticks = len(tks)
            if n_ticks >= 2:
                up_hits = down_hits = 0
                spreads = []
                prev_mid = None
                for tk in sorted(tks, key=lambda x: x["epoch_ms"]):
                    mid = 0.5 * (tk["bid"] + tk["ask"])
                    spreads.append(tk["ask"] - tk["bid"])
                    if prev_mid is not None:
                        if mid > prev_mid:
                            up_hits += 1
                        elif mid < prev_mid:
                            down_hits += 1
                    prev_mid = mid
                tot = up_hits + down_hits
                tick_imbalance = ((up_hits - down_hits) / tot) if tot else None
                spread_med = _pctile(spreads, 50)

        efficiency_delta = None
        if i >= 1 and rows and rows[-1].get("efficiency_20") is not None and efficiency_20 is not None:
            efficiency_delta = efficiency_20 - float(rows[-1]["efficiency_20"])

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
                "disp_atr": disp_atr,
                "bar_disp_atr": bar_disp_atr,
                "disp_sign": (1 if disp > 0 else (-1 if disp < 0 else 0)),
                "wick_up_atr": wick_up,
                "wick_dn_atr": wick_dn,
                "wick_reject_strength": max(wick_up or 0, wick_dn or 0) if a else None,
                "wick_reject_side": (
                    1 if (wick_up or 0) >= (wick_dn or 0) and (wick_up or 0) > 0 else (-1 if (wick_dn or 0) > 0 else 0)
                ),
                "compress_bars": compress_run,
                "up_run": up_run,
                "down_run": down_run,
                "run_bars": max(up_run, down_run),
                "run_sign": (1 if up_run >= down_run and up_run > 0 else (-1 if down_run > 0 else 0)),
                "efficiency_12": efficiency_12,
                "efficiency_20": efficiency_20,
                "efficiency_delta": efficiency_delta,
                "range_high_20": range_high_20,
                "range_low_20": range_low_20,
                "range_width_atr": range_width_atr,
                "session_high": session_high,
                "session_low": session_low,
                "sweep_high": sweep_high,
                "sweep_low": sweep_low,
                "reject_close": reject_close,
                "mom_3": mom_3,
                "mom_6": mom_6,
                "m5_mom_6_atr": m5_mom_6_atr,
                "ema_9_20_spread": ema_9_20_spread,
                "h1_trend": h1_trend,
                "disagree_flag": disagree,
                "asia_mid": asia_mid,
                "dist_asia_mid_atr": dist_asia_mid_atr,
                "session_asia": sess_asia,
                "session_london": sess_london,
                "session_ny": sess_ny,
                "vol_regime": vol_regime,
                "rolling_p30_atr_pct": rolling_p30,
                "rolling_p70_atr_pct": rolling_p70,
                "tick_imbalance": tick_imbalance,
                "spread_median_bar": spread_med,
                "n_ticks_bar": n_ticks,
                "body": body,
                "bar_range": bar_range,
            }
        )
    return rows


def feature_dictionary() -> dict[str, str]:
    return {
        "compress_bars": "Consecutive M5 bars with range < 0.7*ATR14",
        "bar_disp_atr": "|close-open|/ATR14",
        "wick_reject_strength": "max(upper,lower wick)/ATR14",
        "efficiency_20": "|net move|/path length over 20 bars",
        "range_width_atr": "(high20-low20)/ATR",
        "sweep_high/low": "Pierce prior 12-bar extreme then close back inside by 0.25 ATR",
        "disagree_flag": "Completed H1 trend vs M5 mom6 sign disagreement",
        "tick_imbalance": "(up_mid_moves - down_mid_moves)/total within bar ticks",
        "dist_asia_mid_atr": "(close - Asia UTC mid)/ATR after Asia forms",
        "vol_regime": "atr_pct vs causal 48-bar p30/p70",
        "note": "All causal at bar close; incomplete H1 excluded via close_time<=decision",
    }
