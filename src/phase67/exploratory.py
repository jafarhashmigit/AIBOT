"""Exploratory market-behaviour research on PREVIOUSLY_CONSUMED archive only.

NOT independent discovery / validation / confirmation.
Fixed thresholds — not optimized for historical profit.
No sealed holdout access.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from phase49.atr import atr_at
from phase58.data import load_m5_raw
from phase64_13.schedule import state_at_utc
from phase65.consumption import build_consumption_registry
from phase67.constants import (
    ATR_PERIOD,
    BREAKOUT_ATR_MULT,
    DISPLACEMENT_ATR_MULT,
    EVENT_STRIDE,
    LOOKBACK_RANGE_BARS,
    OUTCOME_HORIZONS,
    REENTRY_BARS,
    VOL_HIGH_PCT,
    VOL_LOW_PCT,
    canonical_json_sha256,
)


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace(" ", "T"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _session(ts: str) -> str:
    try:
        return state_at_utc(_parse_ts(ts), honor_holidays=True)["state"]
    except Exception:
        return "UNKNOWN"


def _mid(bar: dict[str, Any]) -> float:
    return (float(bar["high"]) + float(bar["low"])) / 2.0


def _close(bar: dict[str, Any]) -> float:
    return float(bar["close"])


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(p * (len(s) - 1))))
    return s[i]


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def consumed_days() -> list[str]:
    cons = build_consumption_registry()
    splits_disc = set(cons.get("phase65_discovery") or [])
    splits_val = set(cons.get("phase65_validation") or [])
    # All previously consumed from status + phase65 lists; exclude holdout
    hold = set(cons.get("phase58_holdout_sealed") or [])
    days = []
    for d, st in (cons.get("status_by_day") or {}).items():
        if d in hold:
            continue
        if d in splits_disc or d in splits_val:
            days.append(d)
            continue
        if st in (
            "PHASE58_DISCOVERY_CONSUMED",
            "PHASE58_VALIDATION_CONSUMED",
            "PHASE49_DISCOVERY_CONSUMED",
        ):
            days.append(d)
    # Also include phase65 days explicitly
    days = sorted(set(days) | splits_disc | splits_val)
    return [d for d in days if d not in hold]


def _path_excursion(m5: list[dict], idx: int, horizon: int, direction: str) -> dict[str, Any]:
    """MFE/MAE using mid path; exploratory — not broker fill simulation with costs."""
    entry = _close(m5[idx])
    end = min(len(m5) - 1, idx + horizon)
    path = [_close(m5[j]) for j in range(idx + 1, end + 1)]
    if not path:
        return {"ok": False}
    if direction == "BUY":
        rets = [(p - entry) for p in path]
    else:
        rets = [(entry - p) for p in path]
    return {
        "ok": True,
        "end_move": rets[-1],
        "mfe": max(rets),
        "mae": min(rets),
        "continued": rets[-1] > 0,
        "reversed": rets[-1] < 0,
    }


def analyze_day(day: str) -> dict[str, Any]:
    m5 = load_m5_raw(day)
    events = {
        "failed_breakout": [],
        "vol_continuation": [],
        "mean_reversion": [],
    }
    atrs = []
    for i in range(ATR_PERIOD + LOOKBACK_RANGE_BARS, len(m5) - max(OUTCOME_HORIZONS) - 1, EVENT_STRIDE):
        atr = atr_at(m5, i, ATR_PERIOD)
        if not atr or atr <= 0:
            continue
        atrs.append(atr)
        sess = _session(str(m5[i]["timestamp_utc"]))
        # Prior range
        window = m5[i - LOOKBACK_RANGE_BARS : i]
        hi = max(float(b["high"]) for b in window)
        lo = min(float(b["low"]) for b in window)
        c = _close(m5[i])
        # A. Failed breakout: close beyond range by BREAKOUT_ATR_MULT*atr, then re-enter within REENTRY_BARS
        for direction, level, broke in (("BUY", hi, c > hi + BREAKOUT_ATR_MULT * atr), ("SELL", lo, c < lo - BREAKOUT_ATR_MULT * atr)):
            if not broke:
                continue
            reentered = False
            reentry_k = None
            for k in range(1, REENTRY_BARS + 1):
                if i + k >= len(m5):
                    break
                ck = _close(m5[i + k])
                if direction == "BUY" and ck <= hi:
                    reentered = True
                    reentry_k = k
                    break
                if direction == "SELL" and ck >= lo:
                    reentered = True
                    reentry_k = k
                    break
            if not reentered:
                continue
            disp = abs(c - level) / atr
            outcomes = {h: _path_excursion(m5, i + (reentry_k or 0), h, direction) for h in OUTCOME_HORIZONS}
            events["failed_breakout"].append(
                {
                    "day": day,
                    "idx": i,
                    "direction": direction,
                    "session": sess,
                    "displacement_atr": disp,
                    "reentry_bars": reentry_k,
                    "atr": atr,
                    "outcomes": outcomes,
                }
            )

        # B/C displacement events
        if i >= 1:
            prev = _close(m5[i - 1])
            move = (c - prev) / atr
            if abs(move) >= DISPLACEMENT_ATR_MULT:
                direction = "BUY" if move > 0 else "SELL"
                outcomes = {h: _path_excursion(m5, i, h, direction) for h in OUTCOME_HORIZONS}
                # also opposite for mean-reversion framing
                rev_dir = "SELL" if direction == "BUY" else "BUY"
                rev_out = {h: _path_excursion(m5, i, h, rev_dir) for h in OUTCOME_HORIZONS}
                row = {
                    "day": day,
                    "idx": i,
                    "direction": direction,
                    "session": sess,
                    "displacement_atr": abs(move),
                    "atr": atr,
                    "continuation_outcomes": outcomes,
                    "reversion_outcomes": rev_out,
                }
                events["vol_continuation"].append(row)
                events["mean_reversion"].append(row)

    return {"day": day, "n_bars": len(m5), "events": events, "atr_sample": atrs}


def _summarize_direction_outcomes(rows: list[dict], key: str = "outcomes") -> dict[str, Any]:
    by_dir: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    by_sess: dict[str, int] = defaultdict(int)
    days = set()
    for r in rows:
        days.add(r["day"])
        by_sess[r.get("session") or "UNKNOWN"] += 1
        outs = r.get(key) or r.get("continuation_outcomes") or {}
        for h, o in outs.items():
            if not o.get("ok"):
                continue
            by_dir[r["direction"]][f"h{h}_end"].append(float(o["end_move"]))
            by_dir[r["direction"]][f"h{h}_mfe"].append(float(o["mfe"]))
            by_dir[r["direction"]][f"h{h}_mae"].append(float(o["mae"]))
            by_dir[r["direction"]][f"h{h}_cont"].append(1.0 if o["continued"] else 0.0)
    summary = {}
    for d, metrics in by_dir.items():
        summary[d] = {m: {"n": len(vs), "mean": _mean(vs)} for m, vs in metrics.items()}
    return {
        "n_events": len(rows),
        "n_independent_dates": len(days),
        "events_per_date": (len(rows) / len(days)) if days else None,
        "by_session_counts": dict(by_sess),
        "by_direction": summary,
        "label": "DESCRIPTIVE_ONLY_NOT_PREDICTIVE_CONFIRMATION",
    }


def run_exploratory_analysis() -> dict[str, Any]:
    days = consumed_days()
    assert not set(days) & set(build_consumption_registry()["phase58_holdout_sealed"]), "holdout_leak"

    all_fb, all_vc, all_mr = [], [], []
    atr_all: list[float] = []
    day_meta = []
    for d in days:
        a = analyze_day(d)
        day_meta.append({"day": d, "n_bars": a["n_bars"], "n_fb": len(a["events"]["failed_breakout"]),
                         "n_disp": len(a["events"]["vol_continuation"])})
        all_fb.extend(a["events"]["failed_breakout"])
        all_vc.extend(a["events"]["vol_continuation"])
        all_mr.extend(a["events"]["mean_reversion"])
        atr_all.extend(a["atr_sample"])

    # Volatility regime split for continuation (fixed terciles from sample — descriptive)
    hi_thr = _pct(atr_all, VOL_HIGH_PCT)
    lo_thr = _pct(atr_all, VOL_LOW_PCT)
    vc_low = [r for r in all_vc if lo_thr is not None and r["atr"] <= lo_thr]
    vc_high = [r for r in all_vc if hi_thr is not None and r["atr"] >= hi_thr]
    vc_mid = [r for r in all_vc if r not in vc_low and r not in vc_high]

    # Session-dependent failed breakout
    fb_by_sess = defaultdict(list)
    for r in all_fb:
        fb_by_sess[r["session"]].append(r)

    # Directional asymmetry on displacement continuation h12
    def cont_rate(rows: list[dict], direction: str, h: int = 12) -> dict[str, Any]:
        xs = []
        for r in rows:
            if r["direction"] != direction:
                continue
            o = (r.get("continuation_outcomes") or {}).get(h) or {}
            if o.get("ok"):
                xs.append(1.0 if o["continued"] else 0.0)
        return {"n": len(xs), "continuation_rate": _mean(xs)}

    out = {
        "purpose": "EXPLORATORY_ON_PREVIOUSLY_CONSUMED_ARCHIVE",
        "independent_discovery": False,
        "validation": False,
        "confirmation": False,
        "holdout_accessed": False,
        "thresholds_optimized_for_profit": False,
        "fixed_thresholds": {
            "LOOKBACK_RANGE_BARS": LOOKBACK_RANGE_BARS,
            "BREAKOUT_ATR_MULT": BREAKOUT_ATR_MULT,
            "REENTRY_BARS": REENTRY_BARS,
            "DISPLACEMENT_ATR_MULT": DISPLACEMENT_ATR_MULT,
            "OUTCOME_HORIZONS": list(OUTCOME_HORIZONS),
            "EVENT_STRIDE": EVENT_STRIDE,
            "ATR_PERIOD": ATR_PERIOD,
        },
        "days_analyzed": days,
        "n_independent_dates": len(days),
        "definitions": {
            "failed_breakout": (
                f"Close beyond prior {LOOKBACK_RANGE_BARS}-bar range by {BREAKOUT_ATR_MULT}*ATR, "
                f"then re-enter range within {REENTRY_BARS} bars; outcomes from re-entry bar."
            ),
            "vol_continuation": (
                f"|close_ret|/ATR >= {DISPLACEMENT_ATR_MULT}; continuation = same-direction end move > 0."
            ),
            "mean_reversion": "Same displacement events; reversion = opposite-direction path outcomes.",
            "session": "Phase64.13 state_at_utc on bar timestamp (Exness schedule proxy on MetaQuotes archive).",
        },
        "failed_breakout": {
            **_summarize_direction_outcomes(all_fb, "outcomes"),
            "by_session": {s: _summarize_direction_outcomes(rs, "outcomes") for s, rs in fb_by_sess.items()},
        },
        "volatility_conditioned_continuation": {
            "low_vol": _summarize_direction_outcomes(vc_low, "continuation_outcomes"),
            "mid_vol": _summarize_direction_outcomes(vc_mid, "continuation_outcomes"),
            "high_vol": _summarize_direction_outcomes(vc_high, "continuation_outcomes"),
            "atr_low_threshold": lo_thr,
            "atr_high_threshold": hi_thr,
        },
        "mean_reversion_after_displacement": {
            "reversion_path": _summarize_direction_outcomes(all_mr, "reversion_outcomes"),
            "continuation_path": _summarize_direction_outcomes(all_mr, "continuation_outcomes"),
        },
        "directional_asymmetry_h12": {
            "BUY_continuation": cont_rate(all_vc, "BUY", 12),
            "SELL_continuation": cont_rate(all_vc, "SELL", 12),
            "BUY_failed_breakout_n": sum(1 for r in all_fb if r["direction"] == "BUY"),
            "SELL_failed_breakout_n": sum(1 for r in all_fb if r["direction"] == "SELL"),
        },
        "cost_note": "Commission/slippage/swap UNKNOWN — not zeroed; path moves are descriptive mid/close deltas only.",
        "inconclusive_notes": [
            "Overlap reduced via EVENT_STRIDE but residual date dependence remains; report date counts.",
            "Exness session schedule on MetaQuotes timestamps is a proxy limitation.",
            "No claim of predictive edge or Champion eligibility.",
        ],
        "day_meta": day_meta,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k not in ("sha256", "day_meta")})
    return out
