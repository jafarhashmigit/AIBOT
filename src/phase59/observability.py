"""Market regime observability — where evidence is strong/weak/unavailable."""

from __future__ import annotations

from typing import Any

from phase49.atr import atr_at
from phase54.constants import SYMBOL
from phase59.constants import ATR_PERIOD, canonical_json_sha256
from phase59.inventory import load_jsonl, resolve_root_for_day


def _regime_label(atr_now: float, atr_med: float, ret_abs: float) -> str:
    if atr_med <= 0:
        return "UNKNOWN"
    if atr_now > 1.5 * atr_med and ret_abs > atr_now:
        return "HIGH_VOL_TRENDISH"
    if atr_now > 1.5 * atr_med:
        return "HIGH_VOL"
    if atr_now < 0.7 * atr_med and ret_abs < 0.3 * atr_now:
        return "LOW_VOL_RANGEISH"
    if ret_abs > atr_now:
        return "TRENDISH"
    return "RANGEISH"


def build_observability(days: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    atrs: list[float] = []
    session_hours = set()
    gaps_total = 0
    for day in days:
        root = resolve_root_for_day(day)
        if root is None:
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        day_atrs = []
        for i in range(ATR_PERIOD + 1, len(m5)):
            a = atr_at(m5, i, ATR_PERIOD)
            if a:
                day_atrs.append(a)
                atrs.append(a)
        med = sorted(day_atrs)[len(day_atrs) // 2] if day_atrs else 0.0
        for i in range(ATR_PERIOD + 2, len(m5)):
            a = atr_at(m5, i, ATR_PERIOD)
            if not a:
                continue
            c0 = float(m5[i - 1]["close"])
            c1 = float(m5[i]["close"])
            lab = _regime_label(a, med, abs(c1 - c0))
            counts[lab] = counts.get(lab, 0) + 1
            session_hours.add(int(str(m5[i]["timestamp_utc"])[11:13]))
        # gaps
        from datetime import datetime

        for a, b in zip(m5, m5[1:]):
            try:
                da = datetime.strptime(str(a["timestamp_utc"])[:19], "%Y-%m-%d %H:%M:%S")
                db = datetime.strptime(str(b["timestamp_utc"])[:19], "%Y-%m-%d %H:%M:%S")
                if (db - da).total_seconds() > 360:
                    gaps_total += 1
            except Exception:
                pass

    total = sum(counts.values()) or 1
    frac = {k: v / total for k, v in counts.items()}
    # Coverage strength heuristics
    strength = {}
    for k, f in frac.items():
        if f >= 0.15:
            strength[k] = "STRONG"
        elif f >= 0.05:
            strength[k] = "WEAK"
        else:
            strength[k] = "SPARSE"

    missing = []
    if not any(h < 7 for h in session_hours):
        missing.append("ASIA_HOURS_UNDERREPRESENTED")
    if gaps_total < 5:
        missing.append("LIMITED_INTRADAY_GAP_SAMPLE")
    missing.append("MAJOR_DISRUPTION_EVENTS_NOT_LABELED")
    missing.append("LIVE_BROKER_REGIMES_UNOBSERVED")

    out = {
        "n_days": len(days),
        "regime_counts": counts,
        "regime_fractions": frac,
        "evidence_strength": strength,
        "hours_utc_observed": sorted(session_hours),
        "intraday_gaps_gt_6m": gaps_total,
        "underrepresented_or_missing": missing,
        "atr_summary": {
            "n": len(atrs),
            "mean": (sum(atrs) / len(atrs)) if atrs else None,
            "median": sorted(atrs)[len(atrs) // 2] if atrs else None,
        },
        "caveat": "Regime labels are heuristic research proxies on demo archives — not complete market coverage claims",
    }
    out["observability_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "observability_sha256"})
    return out
