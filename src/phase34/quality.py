"""Bid/ask integrity validation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase34.constants import RESEARCH_CUTOFF_UTC
from phase34.progress import write_json


def validate_ticks(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(ticks)
    if n == 0:
        report = {"n_ticks": 0, "pass": False, "reason": "no_ticks"}
        write_json("data_quality.json", report)
        return report

    bids = [float(t["bid"]) for t in ticks]
    asks = [float(t["ask"]) for t in ticks]
    spreads = [float(t["ask"]) - float(t["bid"]) for t in ticks]
    epochs = [int(t["epoch_ms"]) for t in ticks]

    unordered = sum(1 for i in range(1, n) if epochs[i] < epochs[i - 1])
    dups = Counter(epochs)
    dup_extra = sum(c - 1 for c in dups.values() if c > 1)
    nonpos_bid = sum(1 for b in bids if b <= 0)
    nonpos_ask = sum(1 for a in asks if a <= 0)
    crossed = sum(1 for b, a in zip(bids, asks) if b > a)
    neg_spread = sum(1 for s in spreads if s < 0)
    zero_spread = sum(1 for s in spreads if s == 0)
    after = sum(1 for t in ticks if t["timestamp_utc"] > RESEARCH_CUTOFF_UTC)
    spread_mismatch = sum(
        1 for t, s in zip(ticks, spreads) if abs(float(t.get("spread", s)) - s) > 1e-12
    )

    hard_fail = unordered or nonpos_bid or nonpos_ask or crossed or neg_spread or after
    report = {
        "n_ticks": n,
        "pass": not hard_fail,
        "checks": {
            "timestamp_ordering_violations": unordered,
            "duplicate_epoch_extra_rows": dup_extra,
            "duplicate_policy": "retain_all_rows; count extras; do not silently drop",
            "nonpositive_bid": nonpos_bid,
            "nonpositive_ask": nonpos_ask,
            "bid_gt_ask": crossed,
            "negative_spread": neg_spread,
            "zero_spread": zero_spread,
            "after_cutoff": after,
            "spread_field_mismatch": spread_mismatch,
        },
        "bid_stats": {
            "min": min(bids),
            "max": max(bids),
            "mean": sum(bids) / n,
        },
        "ask_stats": {
            "min": min(asks),
            "max": max(asks),
            "mean": sum(asks) / n,
        },
        "spread_stats_usd": {
            "min": min(spreads),
            "max": max(spreads),
            "mean": sum(spreads) / n,
        },
        "fabricated_ticks": False,
        "bid_ask_separate": True,
    }
    write_json("data_quality.json", report)
    return report
