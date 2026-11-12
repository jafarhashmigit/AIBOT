"""Paired BUY/SELL statistical corrections — no inflated independent n."""

from __future__ import annotations

import random
from typing import Any

from phase60.constants import BOOTSTRAP_N, BOOTSTRAP_SEED, canonical_json_sha256


def paired_summaries(events: list[dict[str, Any]]) -> dict[str, Any]:
    """events: [{event_id, day, buy_net_r, sell_net_r}, ...]"""
    n_events = len(events)
    buy = [float(e["buy_net_r"]) for e in events]
    sell = [float(e["sell_net_r"]) for e in events]
    diff = [b - s for b, s in zip(buy, sell)]  # within-event BUY minus SELL

    def _mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    # Incorrect inflation (Phase59-style BOTH concat) — report for audit only
    both_inflated = buy + sell

    # Event-level bootstrap of mean diff and mean buy
    rng = random.Random(BOOTSTRAP_SEED)
    boot_diff = []
    boot_buy = []
    boot_sell = []
    if n_events:
        for _ in range(BOOTSTRAP_N):
            sample = [events[rng.randrange(n_events)] for _ in range(n_events)]
            sb = [float(e["buy_net_r"]) for e in sample]
            ss = [float(e["sell_net_r"]) for e in sample]
            boot_buy.append(sum(sb) / len(sb))
            boot_sell.append(sum(ss) / len(ss))
            boot_diff.append(sum(b - s for b, s in zip(sb, ss)) / len(sb))

    def _ci(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"p025": None, "p975": None}
        s = sorted(xs)
        return {"p025": s[int(0.025 * (len(s) - 1))], "p975": s[int(0.975 * (len(s) - 1))]}

    # Day-clustered bootstrap
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_day.setdefault(str(e.get("day")), []).append(e)
    days = list(by_day.keys())
    boot_day_diff = []
    if days:
        for _ in range(BOOTSTRAP_N):
            sampled_days = [days[rng.randrange(len(days))] for _ in range(len(days))]
            sample = []
            for d in sampled_days:
                sample.extend(by_day[d])
            if not sample:
                continue
            sb = [float(e["buy_net_r"]) for e in sample]
            ss = [float(e["sell_net_r"]) for e in sample]
            boot_day_diff.append(sum(b - s for b, s in zip(sb, ss)) / len(sb))

    out = {
        "n_unique_events": n_events,
        "n_side_observations": n_events * 2,
        "incorrect_independent_n_if_both_concat": len(both_inflated),
        "correction": "Treat 47 paired events as n_events=47, not n=94 independent market events",
        "descriptive": {
            "buy_mean": _mean(buy),
            "sell_mean": _mean(sell),
            "within_event_buy_minus_sell_mean": _mean(diff),
            "both_concat_mean_inflated_method": _mean(both_inflated),
        },
        "inferential": {
            "method": "event_resample_bootstrap",
            "seed": BOOTSTRAP_SEED,
            "n_boot": BOOTSTRAP_N,
            "buy_mean_ci95": _ci(boot_buy),
            "sell_mean_ci95": _ci(boot_sell),
            "buy_minus_sell_mean_ci95": _ci(boot_diff),
            "day_clustered_buy_minus_sell_mean_ci95": _ci(boot_day_diff),
            "n_days_represented": len(days),
            "note": "CIs are descriptive uncertainty under exchangeability assumptions — not trading-edge proof",
        },
        "phase59_audit": {
            "reported_events": 47,
            "reported_both_n": 94,
            "issue": "BOTH concatenated BUY+SELL treated as n=94; effective independent market events remain 47",
            "phase58_conclusions_unchanged": True,
            "holdout_used": False,
        },
        "sample_limitations": [
            "Small event count; day clustering reduces effective df further",
            "Demo path fills; commission/slippage UNKNOWN",
            "Not evidence of alpha",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def events_from_phase59_stress_shape(n_events: int = 47, seed: int = BOOTSTRAP_SEED) -> list[dict[str, Any]]:
    """Rebuild paired placeholder from reported Phase59 means only when raw events unavailable.

    Prefer real event reconstruction via reconstruct_paired_from_days.
    """
    rng = random.Random(seed)
    # Cannot invent outcomes — return empty to force reconstruction path
    _ = (n_events, rng)
    return []
