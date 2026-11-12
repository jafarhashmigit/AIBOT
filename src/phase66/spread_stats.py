"""Spread statistics from broker-observed / fixture quote records."""

from __future__ import annotations

from typing import Any

from phase66.constants import canonical_json_sha256


def compute_spread_stats(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    spreads = []
    by_session: dict[str, list[float]] = {}
    for q in quotes:
        if q.get("kind") != "QUOTE_SNAPSHOT":
            continue
        if q.get("validation_status") != "OK":
            continue
        sp = q.get("spread")
        if sp is None:
            continue
        spreads.append(float(sp))
        sess = str(q.get("session_state") or "UNKNOWN")
        by_session.setdefault(sess, []).append(float(sp))

    def pct(xs: list[float], p: float) -> float | None:
        if not xs:
            return None
        s = sorted(xs)
        i = min(len(s) - 1, max(0, int(p * (len(s) - 1))))
        return s[i]

    out = {
        "n_observations": len(spreads),
        "mean": (sum(spreads) / len(spreads)) if spreads else None,
        "median": pct(spreads, 0.5),
        "p90": pct(spreads, 0.9),
        "p95": pct(spreads, 0.95),
        "p99": pct(spreads, 0.99),
        "maximum": max(spreads) if spreads else None,
        "by_session_mean": {k: (sum(v) / len(v) if v else None) for k, v in by_session.items()},
        "missing_pct": None,
        "stale_pct": None,
        "fixed_assumed_spread_used": False,
        "establishes_commission": False,
        "establishes_slippage": False,
        "establishes_swap": False,
        "note": "Spread evidence alone does not complete execution economics",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
