"""Frozen trigger logic — maps feature rows → hypothesis events with predicted side."""

from __future__ import annotations

from typing import Any


def _event(hid: str, row: dict, side: int | None, meta: dict | None = None) -> dict[str, Any]:
    return {
        "hypothesis_id": hid,
        "time": row["time"],
        "day": row["day"],
        "side": side,  # +1 BUY, -1 SELL, None = unsigned
        "atr": row.get("atr_14"),
        "close": row.get("close"),
        "meta": meta or {},
    }


def detect_events(hid: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return events at bar close; entry conceptually next bar open (decision eval)."""
    ev: list[dict[str, Any]] = []
    if hid == "H42_A_VOL_COMPRESS_EXPAND":
        for r in rows:
            if r.get("compress_bars", 0) >= 6 and r.get("atr_14_pct") is not None and r.get("rolling_p30_atr_pct") is not None:
                if r["atr_14_pct"] < r["rolling_p30_atr_pct"]:
                    ev.append(_event(hid, r, None, {"compress_bars": r["compress_bars"]}))
    elif hid == "H42_B_TREND_EXHAUST_WICK":
        for r in rows:
            if r.get("run_bars", 0) >= 5 and (r.get("wick_reject_strength") or 0) >= 1.2:
                run_s = r.get("run_sign") or 0
                wick_s = r.get("wick_reject_side") or 0
                # opposing wick: upper wick after up-run → fade short
                if run_s > 0 and (r.get("wick_up_atr") or 0) >= 1.2:
                    ev.append(_event(hid, r, -1))
                elif run_s < 0 and (r.get("wick_dn_atr") or 0) >= 1.2:
                    ev.append(_event(hid, r, 1))
    elif hid == "H42_C_SESSION_SWEEP_REJECT":
        for r in rows:
            if r.get("sweep_high") and r.get("reject_close"):
                ev.append(_event(hid, r, -1))
            elif r.get("sweep_low") and r.get("reject_close"):
                ev.append(_event(hid, r, 1))
    elif hid == "H42_D_RANGE_TO_TREND_BREAK":
        for r in rows:
            if r.get("range_width_atr") is None or r.get("range_width_atr") > 1.5:
                continue
            a = r.get("atr_14")
            rh, rl, c = r.get("range_high_20"), r.get("range_low_20"), r.get("close")
            if a and rh is not None and rl is not None and c is not None:
                if c >= rh + 0.5 * a:
                    ev.append(_event(hid, r, 1))
                elif c <= rl - 0.5 * a:
                    ev.append(_event(hid, r, -1))
    elif hid == "H42_E_TREND_TO_RANGE_SLOWDOWN":
        for i, r in enumerate(rows):
            if i < 1:
                continue
            prev = rows[i - 1]
            if (prev.get("efficiency_20") or 0) >= 0.35 and (r.get("efficiency_delta") or 0) < 0:
                if r.get("disp_atr") is not None and abs(r["disp_atr"]) < 0.8:
                    ev.append(_event(hid, r, None))
    elif hid == "H42_F_MTF_MOMENTUM_DISAGREE":
        for r in rows:
            if r.get("disagree_flag") != 1:
                continue
            if r.get("m5_mom_6_atr") is None or abs(r["m5_mom_6_atr"]) < 0.3:
                continue
            if r.get("h1_trend") == "up":
                ev.append(_event(hid, r, 1))
            elif r.get("h1_trend") == "down":
                ev.append(_event(hid, r, -1))
    elif hid == "H42_G_TICK_IMBALANCE":
        # need spread p70 per day — compute casually from rows with spreads
        spreads = [r["spread_median_bar"] for r in rows if r.get("spread_median_bar") is not None]
        p70 = None
        if spreads:
            s = sorted(spreads)
            p70 = s[int(0.7 * (len(s) - 1))]
        for r in rows:
            if (r.get("n_ticks_bar") or 0) < 30:
                continue
            imb = r.get("tick_imbalance")
            if imb is None or abs(imb) < 0.25:
                continue
            if p70 is not None and r.get("spread_median_bar") is not None and r["spread_median_bar"] > p70:
                continue
            ev.append(_event(hid, r, 1 if imb > 0 else -1, {"imbalance": imb}))
    elif hid == "H42_H_SESSION_NY_DRIFT":
        for r in rows:
            if not r.get("session_ny"):
                continue
            d = r.get("dist_asia_mid_atr")
            if d is None or abs(d) < 1.0:
                continue
            # toward asia mid: if above mid, sell
            ev.append(_event(hid, r, -1 if d > 0 else 1, {"dist": d}))
    elif hid == "H42_I_VOL_COND_DIRECTION":
        for r in rows:
            if r.get("vol_regime") != "high":
                continue
            m = r.get("mom_3")
            a = r.get("atr_14")
            if m is None or not a or abs(m) / a < 0.4:
                continue
            ev.append(_event(hid, r, 1 if m > 0 else -1))
    elif hid == "H42_J_DISPLACEMENT_RETRACE":
        for r in rows:
            if (r.get("bar_disp_atr") or 0) >= 1.5:
                # against displacement
                ev.append(_event(hid, r, -int(r.get("disp_sign") or 0) or None))
    return [e for e in ev if e.get("side") is not None or hid in ("H42_A_VOL_COMPRESS_EXPAND", "H42_E_TREND_TO_RANGE_SLOWDOWN")]
