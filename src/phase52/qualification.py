"""Phase52 verdict selection."""

from __future__ import annotations

from typing import Any

from phase52.constants import MIN_QUALIFIED_SCORE


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload["integrity_failure"])
    ranked = payload.get("ranked") or []
    if not ranked:
        return "INSUFFICIENT_DATA", "No instrument/timeframe combinations were scored."
    primary = payload.get("primary")
    if primary and primary.get("qualified"):
        return (
            "MARKET_REPRESENTATION_SELECTED",
            f"Primary={primary['symbol']}/{primary['timeframe']} score={primary['score']:.3f}",
        )
    # any qualified?
    quals = [r for r in ranked if r.get("qualified")]
    if not quals:
        best = ranked[0]
        if float(best.get("score") or 0) < 0.25:
            return "INSUFFICIENT_DATA", "All combinations scored too low / lack critical data."
        return (
            "NO_QUALIFIED_MARKET",
            f"Best={best['symbol']}/{best['timeframe']} score={best['score']:.3f} < min {MIN_QUALIFIED_SCORE} or bid/ask gate failed.",
        )
    return "MARKET_REPRESENTATION_SELECTED", "Qualified market found."
