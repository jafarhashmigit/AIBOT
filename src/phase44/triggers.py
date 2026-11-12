"""Frozen trigger detection for Phase44 hypotheses."""

from __future__ import annotations

from typing import Any


def detect_events(hid: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ev = []
    for r in rows:
        side = None
        if hid == "H44_1_PREV_DAY_LEVEL_REJECTION":
            if r.get("pierce_high"):
                side = -1
            elif r.get("pierce_low"):
                side = 1
        elif hid == "H44_2_DISPLACEMENT_CONTINUATION":
            if (r.get("bar_disp_atr") or 0) >= 1.8 and r.get("close_aligned") and r.get("disp_sign"):
                side = int(r["disp_sign"])
        elif hid == "H44_3_VOL_REGIME_TRANSITION":
            if r.get("transition_up") and r.get("mom_3") is not None and r.get("atr_14"):
                if abs(r["mom_3"]) / r["atr_14"] >= 0.35:
                    side = 1 if r["mom_3"] > 0 else -1
        elif hid == "H44_4_TREND_ACCELERATION":
            if (r.get("accel_bars") or 0) >= 4 and r.get("mom_3") is not None and r.get("atr_14"):
                if abs(r["mom_3"]) / r["atr_14"] >= 0.4:
                    side = 1 if r["mom_3"] > 0 else -1
        elif hid == "H44_5_TIGHT_SPREAD_PERSISTENCE":
            sm, p30 = r.get("spread_median_bar"), r.get("spread_p30_so_far")
            if (
                sm is not None
                and p30 is not None
                and sm <= p30
                and (r.get("n_ticks_bar") or 0) >= 20
                and r.get("mom_3") is not None
                and r.get("atr_14")
                and abs(r["mom_3"]) / r["atr_14"] >= 0.35
            ):
                side = 1 if r["mom_3"] > 0 else -1
        if side in (-1, 1):
            ev.append(
                {
                    "hypothesis_id": hid,
                    "time": r["time"],
                    "day": r["day"],
                    "side": side,
                    "atr": r.get("atr_14"),
                    "close": r.get("close"),
                }
            )
    return ev
