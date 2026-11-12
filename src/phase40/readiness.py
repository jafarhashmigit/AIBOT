"""Phase39 candidate DATA readiness only — no BUY/SELL signals, no P&L."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase40.alignment import _ticks_by_bar, align_day
from phase40.constants import HORIZON_BARS, RAW_H1, RAW_M5, SYMBOL, TARGET_DATES
from phase40.storage import h1_done, load_jsonl, m5_done

UTC = timezone.utc


def _ema20_ready_before(h1_bars: list[dict], decision_time: str) -> bool:
    """True if ≥20 completed H1 bars with close_time <= decision_time."""
    completed = [b for b in h1_bars if b.get("close_time_utc", "") <= decision_time]
    return len(completed) >= 20


def assess_readiness() -> dict[str, Any]:
    """Count potential evaluation slots with data prerequisites (not strategy signals)."""
    out = {"H13_C": {"dates": []}, "mean_reversion": {"dates": []}}

    for day in TARGET_DATES:
        m5 = load_jsonl(RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl") if m5_done(day) else []
        h1 = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl") if h1_done(day) else []
        ticks_by_bar = _ticks_by_bar(day)
        times = [b["timestamp_utc"] for b in m5]
        align = align_day(day)

        h13_ok = h13_fail = 0
        mr_ok = mr_fail = 0
        for i, t in enumerate(times):
            if i + HORIZON_BARS >= len(times):
                continue
            # feature history: need index>=48 for vol_ratio on MR; >=20 for ema on H13
            mr_feat_ok = i >= 48  # atr/rsi/vol history proxy
            h13_feat_ok = i >= 20
            horizon = times[i + 1 : i + 1 + HORIZON_BARS]
            path_ok = all(bt in ticks_by_bar and ticks_by_bar[bt] for bt in horizon)
            h1_ok = _ema20_ready_before(h1, t)

            if h13_feat_ok and h1_ok and path_ok:
                h13_ok += 1
            else:
                h13_fail += 1
            if mr_feat_ok and path_ok:
                mr_ok += 1
            else:
                mr_fail += 1

        out["H13_C"]["dates"].append(
            {
                "day": day,
                "eligible_decision_slots": h13_ok,
                "ineligible_slots": h13_fail,
                "h1_warmup_sufficient_30": align["h1_warmup_sufficient_30"],
                "ema20_ready": align["ema20_warmup_ready"],
                "tick_session_status": align["tick_session"].get("status"),
            }
        )
        out["mean_reversion"]["dates"].append(
            {
                "day": day,
                "eligible_decision_slots": mr_ok,
                "ineligible_slots": mr_fail,
                "tick_session_status": align["tick_session"].get("status"),
            }
        )

    def summarize(key: str) -> dict[str, Any]:
        rows = out[key]["dates"]
        return {
            "total_eligible_slots": sum(r["eligible_decision_slots"] for r in rows),
            "dates_with_any_eligible": sum(1 for r in rows if r["eligible_decision_slots"] > 0),
            "dates": rows,
            "note": "Slots are data-prerequisite opportunities, NOT generated trading signals",
        }

    return {
        "H13_C": summarize("H13_C"),
        "mean_reversion": summarize("mean_reversion"),
        "caveat": "Eligibility ≠ edge. No BUY/SELL generated in Phase40.",
    }
