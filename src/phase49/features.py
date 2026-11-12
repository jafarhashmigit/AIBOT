"""Causal feature computation at decision bar — completed info only."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from phase49.atr import atr_at


def _c(m5: list[dict[str, Any]], i: int) -> float:
    return float(m5[i]["close"])


def compute_features(
    *,
    m5: list[dict[str, Any]],
    idx: int,
    h1: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]],
    prior_day_range: float | None,
) -> dict[str, float | None]:
    """Return feature_id → value (None if unavailable). No lookahead."""
    out: dict[str, float | None] = {k: None for k in _IDS}
    if idx < 48 or idx >= len(m5):
        return out

    atr = atr_at(m5, idx, 14)
    if atr is None or atr <= 0:
        return out

    day = str(m5[idx]["timestamp_utc"])[:10]
    # session extremes from completed bars today up to idx
    sess_idx = [i for i in range(idx + 1) if str(m5[i]["timestamp_utc"])[:10] == day]
    if not sess_idx:
        return out
    sess_high = max(float(m5[i]["high"]) for i in sess_idx)
    sess_low = min(float(m5[i]["low"]) for i in sess_idx)
    day_open = float(m5[sess_idx[0]]["open"])
    close = _c(m5, idx)
    rng = sess_high - sess_low

    out["A01_sess_range_pos"] = ((close - sess_low) / rng) if rng > 0 else 0.5
    out["A02_dist_sess_high_atr"] = (sess_high - close) / atr
    out["A03_dist_sess_low_atr"] = (close - sess_low) / atr
    # failed break: prior bar
    if idx >= 1:
        prev_high = float(m5[idx - 1]["high"])
        # use session high before prior bar
        prev_sess = [i for i in sess_idx if i < idx - 1]
        ref_high = max((float(m5[i]["high"]) for i in prev_sess), default=sess_high)
        out["A04_failed_break_up"] = 1.0 if (prev_high > ref_high and _c(m5, idx - 1) < ref_high) else 0.0
    above = sum(1 for i in sess_idx if _c(m5, i) > day_open)
    out["A05_time_above_open"] = above / len(sess_idx)

    # B structure
    rets = [_c(m5, i) - _c(m5, i - 1) for i in range(idx - 11, idx + 1)]
    traveled = sum(abs(r) for r in rets) + 1e-12
    out["B01_efficiency_12"] = abs(_c(m5, idx) - _c(m5, idx - 12)) / traveled
    out["B02_net_disp_atr_12"] = (_c(m5, idx) - _c(m5, idx - 12)) / atr
    consec = 0
    sign0 = 1 if _c(m5, idx) >= _c(m5, idx - 1) else -1
    for i in range(idx, max(idx - 8, 0), -1):
        s = 1 if _c(m5, i) >= _c(m5, i - 1) else -1
        if s == sign0:
            consec += sign0
        else:
            break
    out["B03_consec_dir"] = float(max(-8, min(8, consec)))
    net_recent = _c(m5, idx) - _c(m5, idx - 6)
    net_prior = _c(m5, idx - 6) - _c(m5, idx - 12)
    out["B04_impulse_retr_ratio"] = net_recent / (abs(net_prior) + 1e-12)
    out["B05_compression"] = (float(m5[idx]["high"]) - float(m5[idx]["low"])) / atr

    # C vol
    r1 = [(_c(m5, i) / _c(m5, i - 1)) - 1.0 for i in range(idx - 11, idx + 1)]
    r48 = [(_c(m5, i) / _c(m5, i - 1)) - 1.0 for i in range(idx - 47, idx + 1)]
    out["C01_rv_12"] = _std(r1)
    out["C02_rv_48"] = _std(r48)
    out["C03_vol_accel"] = out["C01_rv_12"] / (out["C02_rv_48"] + 1e-12)
    today_range = sess_high - sess_low
    out["C04_range_vs_prior"] = today_range / (prior_day_range + 1e-12) if prior_day_range else None
    ranges6 = []
    for j in range(idx - 23, idx + 1):
        window = [float(m5[i]["high"]) - float(m5[i]["low"]) for i in range(j - 5, j + 1)]
        ranges6.append(sum(window) / 6.0)
    out["C05_vol_of_vol"] = _std(ranges6)

    # D session
    ts = str(m5[idx]["timestamp_utc"])
    hour = int(ts[11:13]) + int(ts[14:16]) / 60.0
    out["D01_london_active"] = 1.0 if 7 <= hour < 16 else 0.0
    out["D02_ny_active"] = 1.0 if 12 <= hour < 21 else 0.0
    out["D03_overlap"] = 1.0 if 12 <= hour < 16 else 0.0
    out["D04_hours_since_london"] = max(0.0, min(16.0, hour - 7.0))
    dow = datetime.strptime(day, "%Y-%m-%d").weekday()
    out["D05_dow"] = float(dow) if dow < 5 else None

    # E execution from ticks in decision bar
    bar_t = str(m5[idx]["timestamp_utc"])
    bticks = ticks_by_bar.get(bar_t) or []
    if bticks:
        last = bticks[-1]
        spread = float(last["ask"]) - float(last["bid"])
        out["E01_spread_price"] = spread
        out["E02_spread_atr"] = spread / atr
        spreads = []
        for j in range(idx - 11, idx + 1):
            tj = ticks_by_bar.get(str(m5[j]["timestamp_utc"])) or []
            if tj:
                spreads.append(float(tj[-1]["ask"]) - float(tj[-1]["bid"]))
        med = sorted(spreads)[len(spreads) // 2] if spreads else spread
        out["E03_spread_delta"] = spread - med
        counts = []
        for j in range(idx - 11, idx + 1):
            counts.append(len(ticks_by_bar.get(str(m5[j]["timestamp_utc"])) or []))
        med_c = sorted(counts)[len(counts) // 2] if counts else 1
        out["E04_tick_intensity"] = len(bticks) / (med_c + 1e-12)
        ups = 0
        tot = 0
        prev_mid = None
        for t in bticks:
            mid = 0.5 * (float(t["bid"]) + float(t["ask"]))
            if prev_mid is not None:
                tot += 1
                if mid > prev_mid:
                    ups += 1
            prev_mid = mid
        out["E05_uptick_frac"] = (ups / tot) if tot else 0.5
    else:
        sp = m5[idx].get("spread")
        if sp is not None:
            spread = float(sp) * 0.01
            out["E01_spread_price"] = spread
            out["E02_spread_atr"] = spread / atr

    # F MTF — completed M15 = last 3 M5 closes ending at multiple of 15 min
    # Use bars idx-2,idx-1,idx only if idx bar minute is end of M15 (mm % 15 == 10? open times: 00,05,10 form M15 ending at 15)
    # Safer: last completed M15 ends at floor to 15-min boundary strictly before next incomplete.
    minute = int(ts[14:16])
    # completed M15: use close at idx if (minute+5) % 15 == 0 else walk back
    m15_end = idx
    while m15_end >= 2:
        mm = int(str(m5[m15_end]["timestamp_utc"])[14:16])
        if (mm + 5) % 15 == 0:
            break
        m15_end -= 1
    if m15_end >= 2 and (int(str(m5[m15_end]["timestamp_utc"])[14:16]) + 5) % 15 == 0:
        out["F01_m15_ret"] = (_c(m5, m15_end) / _c(m5, m15_end - 3)) - 1.0
    else:
        out["F01_m15_ret"] = (_c(m5, idx) / _c(m5, idx - 3)) - 1.0  # proxy last 15m completed path

    # H1 completed: last H1 bar with close_time <= decision bar timestamp
    decision_ts = str(m5[idx]["timestamp_utc"])
    h1_completed = []
    for b in h1:
        ot = str(b["timestamp_utc"])
        # H1 close = open + 1h
        try:
            close_h1 = ot[:11] + f"{(int(ot[11:13]) + 1) % 24:02d}" + ot[13:]
            # simpler: use open time + require open hour < decision hour same day or prior
        except Exception:
            continue
        # Use bar if its open time + 1h string <= decision (lexicographic works for same format)
        # Construct close timestamp
        dt = datetime.strptime(ot, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        close_dt = dt + timedelta(hours=1)
        dec = datetime.strptime(decision_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        # decision bar is open time; information available at bar close = +5m
        avail = dec + timedelta(minutes=5)
        if close_dt <= avail:
            h1_completed.append(b)
    if len(h1_completed) >= 2:
        last = h1_completed[-1]
        prev = h1_completed[-2]
        out["F02_h1_ret"] = (float(last["close"]) / float(prev["close"])) - 1.0
        hr = float(last["high"]) - float(last["low"])
        out["F03_h1_range_pos"] = (
            (float(last["close"]) - float(last["low"])) / hr if hr > 0 else 0.5
        )
        out["F05_h1_stability"] = 1.0 - abs(out["F02_h1_ret"]) / ((hr / float(last["close"])) + 1e-12)
    if out["F01_m15_ret"] is not None and out.get("F02_h1_ret") is not None:
        s1 = 1 if out["F01_m15_ret"] > 0 else (-1 if out["F01_m15_ret"] < 0 else 0)
        s2 = 1 if out["F02_h1_ret"] > 0 else (-1 if out["F02_h1_ret"] < 0 else 0)
        out["F04_mtf_agree"] = float(s1 * s2)

    return out


def _std(xs: list[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


_IDS = [
    "A01_sess_range_pos",
    "A02_dist_sess_high_atr",
    "A03_dist_sess_low_atr",
    "A04_failed_break_up",
    "A05_time_above_open",
    "B01_efficiency_12",
    "B02_net_disp_atr_12",
    "B03_consec_dir",
    "B04_impulse_retr_ratio",
    "B05_compression",
    "C01_rv_12",
    "C02_rv_48",
    "C03_vol_accel",
    "C04_range_vs_prior",
    "C05_vol_of_vol",
    "D01_london_active",
    "D02_ny_active",
    "D03_overlap",
    "D04_hours_since_london",
    "D05_dow",
    "E01_spread_price",
    "E02_spread_atr",
    "E03_spread_delta",
    "E04_tick_intensity",
    "E05_uptick_frac",
    "F01_m15_ret",
    "F02_h1_ret",
    "F03_h1_range_pos",
    "F04_mtf_agree",
    "F05_h1_stability",
]
