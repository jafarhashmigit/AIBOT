"""Displacement event extraction & path outcomes — fixed thresholds only."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from phase49.atr import atr_at
from phase58.data import load_m5_raw
from phase64_13.schedule import state_at_utc
from phase65.consumption import build_consumption_registry
from phase67.exploratory import consumed_days
from phase68.constants import (
    ATR_PERIOD,
    DISPLACEMENT_ATR_MULT,
    EVENT_STRIDE,
    EXCURSION_THRESHOLD_ATR,
    FLAT_ATR,
    LOOKBACK_RANGE_BARS,
    OUTCOME_HORIZONS,
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


def path_outcome(
    m5: list[dict[str, Any]],
    idx: int,
    horizon: int,
    direction: str,
    atr: float,
) -> dict[str, Any]:
    """Full path outcome using OHLC; direction-adjusted from event close."""
    entry = _close(m5[idx])
    end = idx + horizon
    if end >= len(m5):
        return {"ok": False, "censored": True, "reason": "boundary_censor"}
    # Path bars after decision
    fav_moves: list[float] = []
    adv_moves: list[float] = []
    close_moves: list[float] = []
    t_fav = None
    t_adv = None
    thr = EXCURSION_THRESHOLD_ATR * atr
    for k, j in enumerate(range(idx + 1, end + 1), start=1):
        hi = float(m5[j]["high"])
        lo = float(m5[j]["low"])
        c = _close(m5[j])
        if direction == "BUY":
            fav = hi - entry
            adv = lo - entry
            cm = c - entry
        else:
            fav = entry - lo
            adv = entry - hi
            cm = entry - c
        fav_moves.append(fav)
        adv_moves.append(adv)
        close_moves.append(cm)
        if t_fav is None and fav >= thr:
            t_fav = k
        if t_adv is None and adv <= -thr:
            t_adv = k

    mfe = max(fav_moves)
    mae = min(adv_moves)
    end_ret = close_moves[-1]
    continued = end_ret > FLAT_ATR * atr
    reversed_ = end_ret < -FLAT_ATR * atr
    flat = not continued and not reversed_

    # Path shape flags
    first_half = close_moves[: max(1, len(close_moves) // 2)]
    second_half_end = close_moves[-1]
    initially_cont = first_half[-1] > 0
    initially_rev = first_half[-1] < 0
    then_rev = initially_cont and second_half_end < 0
    then_cont = initially_rev and second_half_end > 0
    # Adverse before favourable: MAE occurs before MFE in bar index
    # Approximate: track running extrema
    run_mfe = -1e18
    run_mae = 1e18
    mae_before_mfe = False
    saw_mae_thr = False
    for fav, adv in zip(fav_moves, adv_moves):
        if adv < run_mae:
            run_mae = adv
            if run_mae <= -thr:
                saw_mae_thr = True
        if fav > run_mfe:
            run_mfe = fav
            if saw_mae_thr and run_mfe >= thr and fav == run_mfe:
                mae_before_mfe = True

    return {
        "ok": True,
        "censored": False,
        "horizon": horizon,
        "end_return": end_ret,
        "end_return_atr": end_ret / atr if atr else None,
        "mfe": mfe,
        "mae": mae,
        "mfe_atr": mfe / atr if atr else None,
        "mae_atr": mae / atr if atr else None,
        "continued": continued,
        "reversed": reversed_,
        "flat": flat,
        "time_to_fav_thr_bars": t_fav,
        "time_to_adv_thr_bars": t_adv,
        "path_close_moves": close_moves,
        "initially_continue_then_reverse": then_rev,
        "initially_reverse_then_continue": then_cont,
        "mae_before_meaningful_mfe": mae_before_mfe,
        "no_meaningful_move": flat,
    }


def extract_events() -> dict[str, Any]:
    holdout = set(build_consumption_registry()["phase58_holdout_sealed"])
    days = consumed_days()
    assert not set(days) & holdout

    events: list[dict[str, Any]] = []
    atr_pool: list[float] = []
    censored = 0
    max_h = max(OUTCOME_HORIZONS)

    for day in days:
        m5 = load_m5_raw(day)
        first = ATR_PERIOD + LOOKBACK_RANGE_BARS
        last = len(m5) - (1 + max_h)
        if last < first:
            continue
        for i in range(first, last + 1, EVENT_STRIDE):
            atr = atr_at(m5, i, ATR_PERIOD)
            if not atr or atr <= 0:
                continue
            atr_pool.append(float(atr))
            prev = _close(m5[i - 1])
            c = _close(m5[i])
            move = (c - prev) / atr
            if abs(move) < DISPLACEMENT_ATR_MULT:
                continue
            direction = "BUY" if move > 0 else "SELL"
            ts = str(m5[i]["timestamp_utc"])
            outcomes = {}
            for h in OUTCOME_HORIZONS:
                o = path_outcome(m5, i, h, direction, float(atr))
                if not o.get("ok"):
                    censored += 1
                outcomes[h] = o
            events.append(
                {
                    "day": day,
                    "idx": i,
                    "timestamp_utc": ts,
                    "direction": direction,
                    "displacement_atr": abs(move),
                    "atr": float(atr),
                    "session_state": _session(ts),
                    "session_label": "PHASE64_13_PROXY_ON_METAQUOTES_ARCHIVE_NOT_EXNESS_HISTORY",
                    "outcomes": outcomes,
                }
            )

    lo = _pct(atr_pool, VOL_LOW_PCT)
    hi = _pct(atr_pool, VOL_HIGH_PCT)
    for e in events:
        a = e["atr"]
        if lo is not None and a <= lo:
            e["vol_regime"] = "low"
        elif hi is not None and a >= hi:
            e["vol_regime"] = "high"
        else:
            e["vol_regime"] = "mid"

    return {
        "definition": f"abs(close[t]-close[t-1])/ATR14[t] >= {DISPLACEMENT_ATR_MULT}",
        "event_stride": EVENT_STRIDE,
        "horizons": list(OUTCOME_HORIZONS),
        "flat_atr_threshold": FLAT_ATR,
        "excursion_threshold_atr": EXCURSION_THRESHOLD_ATR,
        "vol_tercile_pct": {"low": VOL_LOW_PCT, "high": VOL_HIGH_PCT},
        "atr_low_threshold": lo,
        "atr_high_threshold": hi,
        "n_events": len(events),
        "n_independent_dates": len({e["day"] for e in events}),
        "dates": sorted({e["day"] for e in events}),
        "n_boundary_censored_outcomes": censored,
        "holdout_accessed": False,
        "independent_discovery": False,
        "events": events,
    }


def summarize_slice(events: list[dict[str, Any]], horizon: int = 12) -> dict[str, Any]:
    by_dir: dict[str, list] = defaultdict(list)
    days = set()
    for e in events:
        days.add(e["day"])
        o = e["outcomes"].get(horizon) or {}
        if not o.get("ok"):
            continue
        by_dir[e["direction"]].append(o)

    def pack(rows: list[dict]) -> dict[str, Any]:
        if not rows:
            return {"n": 0}
        return {
            "n": len(rows),
            "mean_end_return": _mean([r["end_return"] for r in rows]),
            "mean_end_return_atr": _mean([r["end_return_atr"] for r in rows if r.get("end_return_atr") is not None]),
            "mean_mfe": _mean([r["mfe"] for r in rows]),
            "mean_mae": _mean([r["mae"] for r in rows]),
            "mean_mfe_atr": _mean([r["mfe_atr"] for r in rows if r.get("mfe_atr") is not None]),
            "mean_mae_atr": _mean([r["mae_atr"] for r in rows if r.get("mae_atr") is not None]),
            "p_continuation": _mean([1.0 if r["continued"] else 0.0 for r in rows]),
            "p_reversal": _mean([1.0 if r["reversed"] else 0.0 for r in rows]),
            "p_flat": _mean([1.0 if r["flat"] else 0.0 for r in rows]),
            "median_time_to_fav": _pct([float(r["time_to_fav_thr_bars"]) for r in rows if r.get("time_to_fav_thr_bars")], 0.5),
            "median_time_to_adv": _pct([float(r["time_to_adv_thr_bars"]) for r in rows if r.get("time_to_adv_thr_bars")], 0.5),
        }

    return {
        "horizon": horizon,
        "n_events_ok": sum(len(v) for v in by_dir.values()),
        "n_dates": len(days),
        "BUY": pack(by_dir["BUY"]),
        "SELL": pack(by_dir["SELL"]),
        "ALL": pack(by_dir["BUY"] + by_dir["SELL"]),
    }


def build_displacement_report(bundle: dict[str, Any]) -> dict[str, Any]:
    events = bundle["events"]
    by_horizon = {h: summarize_slice(events, h) for h in OUTCOME_HORIZONS}
    by_vol = {}
    for reg in ("low", "mid", "high"):
        by_vol[reg] = summarize_slice([e for e in events if e.get("vol_regime") == reg], 12)
    by_sess = {}
    for s in sorted({e["session_state"] for e in events}):
        by_sess[s] = summarize_slice([e for e in events if e["session_state"] == s], 12)

    out = {
        "purpose": "EXPLORATORY_DISPLACEMENT_RESPONSE_NOT_INDEPENDENT_DISCOVERY",
        "meta": {k: v for k, v in bundle.items() if k != "events"},
        "by_horizon": by_horizon,
        "by_vol_regime_h12": by_vol,
        "by_session_h12": by_sess,
        "session_caveat": (
            "Phase64.13 session states applied to MetaQuotes-Demo archive timestamps are a PROXY, "
            "not genuine Exness historical session evidence."
        ),
        "buy_sell_separate": True,
        "thresholds_optimized": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
