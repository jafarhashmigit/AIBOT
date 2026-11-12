"""WAIT economics on discovery/validation only — no holdout optimization."""

from __future__ import annotations

from typing import Any

from phase49.outcomes import build_outcome
from phase54.archive_loader import ticks_by_m5_bar
from phase54.constants import SYMBOL
from phase59.constants import canonical_json_sha256
from phase59.inventory import load_jsonl, resolve_root_for_day
from phase59.stress import _load_ticks_stream


def analyze_wait(days: list[str], *, stride: int = 24) -> dict[str, Any]:
    """
    Counterfactual: at each event, compare WAIT(0) vs trading BUY/SELL.
    Measures costs avoided (abs adverse R) and opportunities missed (positive R left on table).
    Does NOT fit a WAIT filter; descriptive only.
    """
    missed_buy = []
    missed_sell = []
    avoided_buy_loss = []
    avoided_sell_loss = []
    spread_atr_when_both_negative = []
    n = 0
    for day in days:
        root = resolve_root_for_day(day)
        if root is None:
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        ticks = _load_ticks_stream(root, day)
        by = ticks_by_m5_bar(ticks)
        first, last = 48, len(m5) - 13
        idx = first
        prev_exit = -10**9
        while idx <= last:
            if idx + 1 <= prev_exit:
                idx += 1
                continue
            buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            if buy.get("data_quality_status") != "OK" or sell.get("data_quality_status") != "OK":
                idx += stride
                continue
            br, sr = float(buy["net_r"]), float(sell["net_r"])
            n += 1
            if br > 0:
                missed_buy.append(br)
            else:
                avoided_buy_loss.append(abs(br))
            if sr > 0:
                missed_sell.append(sr)
            else:
                avoided_sell_loss.append(abs(sr))
            if br < 0 and sr < 0:
                atr = float(buy.get("risk_amount") or 0)
                sp = float(buy.get("entry_spread") or (float(buy["entry_ask"]) - float(buy["entry_bid"])))
                if atr > 0:
                    spread_atr_when_both_negative.append(sp / atr)
            prev_exit = idx + 12
            idx += stride

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    out = {
        "n_events": n,
        "wait_net_r": 0.0,
        "missed_buy_opportunity_mean_R": mean(missed_buy),
        "missed_sell_opportunity_mean_R": mean(missed_sell),
        "n_missed_buy": len(missed_buy),
        "n_missed_sell": len(missed_sell),
        "avoided_buy_loss_mean_R": mean(avoided_buy_loss),
        "avoided_sell_loss_mean_R": mean(avoided_sell_loss),
        "n_avoided_buy_loss": len(avoided_buy_loss),
        "n_avoided_sell_loss": len(avoided_sell_loss),
        "both_sides_negative_frac": (
            sum(1 for _ in spread_atr_when_both_negative) / n if n else None
        ),
        "spread_atr_when_both_negative_mean": mean(spread_atr_when_both_negative),
        "interpretation": (
            "WAIT avoids losses when a forced side is negative and forgoes gains when positive. "
            "This is descriptive economics — not a claim that WAIT creates alpha."
        ),
        "holdout_used": False,
        "filter_optimized": False,
    }
    # fix both_sides frac
    # recount properly
    both_neg = 0
    # recompute from collected length of spread_atr list which only appends on both neg
    both_neg = len(spread_atr_when_both_negative)
    out["both_sides_negative_frac"] = (both_neg / n) if n else None
    out["wait_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "wait_sha256"})
    return out
