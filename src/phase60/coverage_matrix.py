"""Market coverage matrix — heuristic regimes separate from verified disruption labels."""

from __future__ import annotations

from typing import Any

from phase60.adapters import holdout_days, m5_bars, stream_tick_scan
from phase60.constants import canonical_json_sha256
from phase60.sessions import session_label_utc_ts


def _atr14(closes: list[float], highs: list[float], lows: list[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if i < 14:
            continue
        trs = []
        for j in range(i - 13, i + 1):
            tr = highs[j] - lows[j]
            if j > 0:
                tr = max(tr, abs(highs[j] - closes[j - 1]), abs(lows[j] - closes[j - 1]))
            trs.append(tr)
        out[i] = sum(trs) / 14.0
    return out


def build_market_coverage_matrix(research_days: list[str]) -> dict[str, Any]:
    holdout = set(holdout_days())
    days = [d for d in research_days if d not in holdout]
    session_counts = {"ASIA": 0, "LONDON": 0, "NY": 0, "OFF_HOURS": 0, "UNKNOWN": 0}
    regime_counts = {
        "RANGEISH": 0,
        "TRENDISH": 0,
        "HIGH_VOL": 0,
        "LOW_VOL": 0,
        "ABNORMAL_SPREAD": 0,
        "QUOTE_GAP_ILLIQUIDITY": 0,
    }
    atr_vals: list[float] = []
    spread_atr: list[float] = []
    n_bars = 0
    days_with_ticks = 0
    gap_flags = 0

    for day in days:
        m5 = m5_bars(day)
        if not m5:
            continue
        scan = stream_tick_scan(day)
        if int(scan.get("ticks_n") or 0) > 0:
            days_with_ticks += 1
        spreads = scan.get("spreads") or {}
        closes = [float(b["close"]) for b in m5]
        highs = [float(b["high"]) for b in m5]
        lows = [float(b["low"]) for b in m5]
        atrs = _atr14(closes, highs, lows)
        # gap between bars
        for a, b in zip(m5, m5[1:]):
            try:
                from datetime import datetime

                da = datetime.strptime(str(a["timestamp_utc"])[:19], "%Y-%m-%d %H:%M:%S")
                db = datetime.strptime(str(b["timestamp_utc"])[:19], "%Y-%m-%d %H:%M:%S")
                if (db - da).total_seconds() / 60.0 > 5.5:
                    gap_flags += 1
                    regime_counts["QUOTE_GAP_ILLIQUIDITY"] += 1
            except Exception:
                pass

        for i, b in enumerate(m5):
            n_bars += 1
            lab = session_label_utc_ts(str(b.get("timestamp_utc")))
            session_counts[lab] = session_counts.get(lab, 0) + 1
            atr = atrs[i]
            if atr is None or atr <= 0:
                continue
            atr_vals.append(atr)
            sp = spreads.get(str(b.get("timestamp_utc")))
            if sp is not None:
                ratio = float(sp) / atr
                spread_atr.append(ratio)
                if ratio > 0.15:
                    regime_counts["ABNORMAL_SPREAD"] += 1
            # heuristic range/trend via short move / atr
            if i >= 6:
                move = abs(closes[i] - closes[i - 6])
                if move / atr < 0.8:
                    regime_counts["RANGEISH"] += 1
                else:
                    regime_counts["TRENDISH"] += 1
            med_proxy = 3.5
            if atr >= med_proxy * 1.5:
                regime_counts["HIGH_VOL"] += 1
            elif atr <= med_proxy * 0.6:
                regime_counts["LOW_VOL"] += 1

    def _strength(n: int) -> str:
        if n >= 5000:
            return "STRONG"
        if n >= 1000:
            return "MODERATE"
        if n >= 200:
            return "WEAK"
        return "SPARSE"

    categories = {}
    for name, n in {**session_counts, **regime_counts}.items():
        categories[name] = {
            "event_or_bar_count": n,
            "representation": _strength(n),
            "sufficient_for_research": _strength(n) in ("STRONG", "MODERATE"),
            "label_type": "HEURISTIC" if name not in ("ASIA", "LONDON", "NY", "OFF_HOURS") else "SESSION_HEURISTIC_PKT",
            "independently_verified_event_label": False,
        }

    out = {
        "research_days_n": len(days),
        "holdout_excluded": True,
        "days_with_ticks": days_with_ticks,
        "n_bars_scanned": n_bars,
        "m5_gaps_gt_5m_count": gap_flags,
        "session_counts": session_counts,
        "heuristic_regime_counts": regime_counts,
        "categories": categories,
        "spread_over_atr_n": len(spread_atr),
        "atr_n": len(atr_vals),
        "major_disruption_labels": {
            "available": False,
            "count": 0,
            "note": "No independently verifiable news/disruption calendar ingested; not inferred from volatility alone",
        },
        "missing_or_weak": [
            k for k, v in categories.items() if v["representation"] in ("WEAK", "SPARSE")
        ]
        + ["MAJOR_DISRUPTION_EVENTS_UNLABELED", "LIVE_BROKER_REGIMES_UNOBSERVED"],
        "heuristic_vs_verified_separated": True,
        "filter_optimization_performed": False,
        "new_predictive_indicators_introduced": False,
        "caveat": "Heuristic regime labels ≠ verified market-event taxonomy",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
