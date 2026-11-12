"""Raw tick data quality checks for Dukascopy samples."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase33.constants import POINT_SIZE, RESEARCH_CUTOFF_UTC
from phase33.progress import write_json


def validate_ticks(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(ticks)
    if n == 0:
        report = {
            "n_ticks": 0,
            "pass": False,
            "reason": "no_ticks",
            "checks": {},
        }
        write_json("raw_data_quality.json", report)
        return report

    issues: list[dict[str, Any]] = []
    bids = [float(t["bid"]) for t in ticks]
    asks = [float(t["ask"]) for t in ticks]
    spreads = [float(t["spread"]) for t in ticks]
    epochs = [int(t["epoch_ms"]) for t in ticks]
    ts = [t["timestamp_utc"] for t in ticks]

    # Ordering
    unordered = sum(1 for i in range(1, n) if epochs[i] < epochs[i - 1])
    if unordered:
        issues.append({"code": "TIMESTAMP_OUT_OF_ORDER", "count": unordered})

    # Duplicates (same epoch_ms)
    dup_counts = Counter(epochs)
    n_dup_keys = sum(1 for _, c in dup_counts.items() if c > 1)
    n_dup_extra = sum(c - 1 for c in dup_counts.values() if c > 1)
    if n_dup_extra:
        issues.append({"code": "DUPLICATE_EPOCH_MS", "duplicate_keys": n_dup_keys, "extra_rows": n_dup_extra})

    # Invalid prices
    n_nonpos_bid = sum(1 for b in bids if b <= 0)
    n_nonpos_ask = sum(1 for a in asks if a <= 0)
    if n_nonpos_bid or n_nonpos_ask:
        issues.append({"code": "NONPOSITIVE_PRICE", "bid": n_nonpos_bid, "ask": n_nonpos_ask})

    # Bid > ask
    n_crossed = sum(1 for b, a in zip(bids, asks) if b > a)
    if n_crossed:
        issues.append({"code": "BID_GT_ASK", "count": n_crossed})

    # Zero / negative spread
    n_zero_spread = sum(1 for s in spreads if s == 0)
    n_neg_spread = sum(1 for s in spreads if s < 0)
    if n_neg_spread:
        issues.append({"code": "NEGATIVE_SPREAD", "count": n_neg_spread})
    if n_zero_spread:
        issues.append({"code": "ZERO_SPREAD", "count": n_zero_spread, "severity": True})

    # Abnormal spreads (absolute USD > $5 on XAUUSD is extreme for this sample)
    n_abnormal = sum(1 for s in spreads if s > 5.0)
    if n_abnormal:
        issues.append({"code": "ABNORMAL_SPREAD_GT_5USD", "count": n_abnormal, "severity": True})

    # Cutoff
    after_cutoff = sum(1 for t in ts if t > RESEARCH_CUTOFF_UTC)
    if after_cutoff:
        issues.append({"code": "AFTER_CUTOFF", "count": after_cutoff})

    # Precision: prices should be multiples of 0.001 given scale 1000 (point size project is 0.01)
    def _not_multiple(px: float, step: float) -> bool:
        return abs(round(px / step) * step - px) > 1e-9

    n_bad_prec = sum(1 for b, a in zip(bids, asks) if _not_multiple(b, 0.001) or _not_multiple(a, 0.001))
    if n_bad_prec:
        issues.append({"code": "PRECISION_ANOMALY", "count": n_bad_prec, "severity": True})

    # Weekend / closure: inferred from gaps between consecutive ticks > 1 hour during sample
    large_gaps = []
    for i in range(1, n):
        gap_ms = epochs[i] - epochs[i - 1]
        if gap_ms > 3_600_000:
            large_gaps.append({"from": ts[i - 1], "to": ts[i], "gap_hours": gap_ms / 3_600_000})

    hard_fail_codes = {
        "TIMESTAMP_OUT_OF_ORDER",
        "NONPOSITIVE_PRICE",
        "BID_GT_ASK",
        "NEGATIVE_SPREAD",
        "AFTER_CUTOFF",
    }
    hard_fails = [i for i in issues if i["code"] in hard_fail_codes]
    report = {
        "n_ticks": n,
        "pass": len(hard_fails) == 0,
        "point_size_project": POINT_SIZE,
        "native_price_quantum": 0.001,
        "checks": {
            "timestamp_ordering_violations": unordered,
            "duplicate_epoch_extra_rows": n_dup_extra,
            "nonpositive_bid": n_nonpos_bid,
            "nonpositive_ask": n_nonpos_ask,
            "bid_gt_ask": n_crossed,
            "zero_spread": n_zero_spread,
            "negative_spread": n_neg_spread,
            "abnormal_spread_gt_5usd": n_abnormal,
            "after_cutoff": after_cutoff,
            "precision_anomaly": n_bad_prec,
            "large_gaps_gt_1h": len(large_gaps),
        },
        "issues": issues,
        "large_gaps_sample": large_gaps[:20],
        "price_range": {
            "bid_min": min(bids),
            "bid_max": max(bids),
            "ask_min": min(asks),
            "ask_max": max(asks),
            "spread_min": min(spreads),
            "spread_max": max(spreads),
        },
        "raw_source_preserved": True,
        "fabricated_prices": False,
    }
    write_json("raw_data_quality.json", report)
    return report
