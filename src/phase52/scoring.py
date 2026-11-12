"""Transparent weighted research-suitability scores — not profitability."""

from __future__ import annotations

from typing import Any

from phase52.constants import MIN_QUALIFIED_SCORE, WEIGHTS


def score_combination(
    *,
    rates: dict[str, Any],
    ticks: dict[str, Any] | None,
    archive: dict[str, Any] | None,
    symbol_meta: dict[str, Any],
) -> dict[str, Any]:
    """
    Score components in [0,1], then weighted sum.
    Missing critical data applies explicit penalties.
    """
    components: dict[str, float] = {}
    notes: list[str] = []

    # 1) Historical coverage
    n_bars = int(rates.get("n_bars") or 0)
    if not rates.get("ok") or n_bars == 0:
        components["historical_coverage"] = 0.0
        notes.append("no_rate_coverage")
    else:
        # expect roughly ~50 weekdays * bars/day; soft scale
        expected = {"M5": 50 * 200, "M15": 50 * 70, "H1": 50 * 20}.get(rates.get("timeframe") or "M5", 5000)
        components["historical_coverage"] = min(1.0, n_bars / expected)
        if rates.get("n_gap_events", 0) > 50:
            components["historical_coverage"] *= 0.85
            notes.append("many_gaps_penalty")

    # 2) Bid/ask availability
    # Research suitability requires more than a 3-hour demo tick sample.
    if archive and archive.get("combined_unique_m5_days", 0) > 0 and rates.get("symbol") == "XAUUSD":
        tick_days = 0
        for src in (archive.get("sources") or {}).values():
            tick_days = max(tick_days, int(src.get("days_with_ge20_tick_hours") or 0))
        components["bid_ask_availability"] = min(1.0, 0.45 + 0.55 * min(1.0, tick_days / 20))
        notes.append("xauusd_verified_archive_ticks")
    elif ticks and ticks.get("bid_ask_available"):
        # Bounded sample only — cap (no multi-day archive)
        frac = ticks.get("hours_ok", 0) / max(len(ticks.get("sample_hours") or [1]), 1)
        components["bid_ask_availability"] = min(0.40, 0.25 + 0.15 * frac)
        notes.append("tick_sample_only_no_multi_day_archive")
    else:
        components["bid_ask_availability"] = 0.10
        notes.append("no_verified_bid_ask_sample")

    # 3) Spread quality — prefer finite stable spreads; unknown → penalty
    med = None
    p95 = None
    if ticks and ticks.get("spread_median") is not None:
        med = float(ticks["spread_median"])
        p95 = float(ticks.get("spread_p95") or med)
    elif archive and rates.get("symbol") == "XAUUSD":
        # use archive sample from any source with spreads
        for src in (archive.get("sources") or {}).values():
            if src.get("sample_spread_median") is not None:
                med = float(src["sample_spread_median"])
                p95 = float(src.get("sample_spread_p95") or med)
                break
    if med is None:
        # fallback to rate spread points if present (not price units — weak)
        if rates.get("m5_spread_points_median") is not None:
            components["spread_quality"] = 0.35
            notes.append("only_ohlc_spread_points_proxy")
        else:
            components["spread_quality"] = 0.1
            notes.append("spread_unknown")
    else:
        # relative stability: lower p95/median better; still not a profitability claim
        ratio = (p95 / med) if med > 0 else 99.0
        stability = max(0.0, min(1.0, 2.0 - ratio))  # ratio 1→1.0, ratio 2→0
        # presence score
        components["spread_quality"] = 0.55 * 1.0 + 0.45 * stability
        notes.append(f"spread_median={med:.6g}, p95={p95:.6g}, p95/med={ratio:.3g}")

    # 4) Session completeness — unique hours coverage
    nh = int(rates.get("n_unique_hours") or 0)
    components["session_completeness"] = min(1.0, nh / 20.0) if n_bars else 0.0
    if nh < 10:
        notes.append("narrow_session_hour_coverage")

    # 5) Data integrity — gaps, crossed quotes, reloadability of archives
    integ = 1.0
    if rates.get("n_gap_events", 0) > 100:
        integ *= 0.7
        notes.append("integrity_gap_penalty")
    if ticks and int(ticks.get("crossed_quotes") or 0) > 0:
        integ *= 0.85
        notes.append("crossed_quotes_penalty")
    if not rates.get("ok"):
        integ = 0.0
    if archive and rates.get("symbol") == "XAUUSD" and archive.get("combined_unique_m5_days", 0) >= 30:
        integ = min(1.0, integ + 0.1)
        notes.append("archive_reload_integrity_boost")
    components["data_integrity"] = max(0.0, min(1.0, integ))

    # 6) Usable sample size for future independent research
    if archive and rates.get("symbol") == "XAUUSD":
        components["usable_sample_size"] = min(1.0, archive.get("combined_unique_m5_days", 0) / 40.0)
        notes.append("archive_days_drive_sample_size")
    else:
        # Probe-window OHLC alone is not enough to stand up a new research corpus
        components["usable_sample_size"] = min(0.30, n_bars / 20000.0)
        notes.append("no_local_archive_sample_cap")

    # Instrument not available
    if not symbol_meta.get("available", True):
        for k in components:
            components[k] = 0.0
        notes.append("symbol_unavailable")

    total = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    # Gate: need meaningful bid/ask research substrate, not a thin tick probe alone
    has_research_substrate = components.get("bid_ask_availability", 0) >= 0.45 and components.get(
        "usable_sample_size", 0
    ) >= 0.50
    return {
        "components": components,
        "weights": WEIGHTS,
        "score": total,
        "qualified": total >= MIN_QUALIFIED_SCORE and has_research_substrate,
        "notes": notes,
        "min_qualified_score": MIN_QUALIFIED_SCORE,
        "has_research_substrate": has_research_substrate,
    }


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: float(r.get("score") or 0), reverse=True)
