"""Reconstruct paired BUY/SELL events on non-holdout days — adapters only."""

from __future__ import annotations

import json
from typing import Any

from phase49.outcomes import build_outcome
from phase54.archive_loader import ticks_by_m5_bar
from phase60.adapters import holdout_days, root_for_day, tick_paths
from phase60.constants import SYMBOL
from phase59.inventory import load_jsonl


def _load_ticks(day: str) -> list[dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    for p in tick_paths(day):
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ticks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return ticks


def reconstruct_paired(
    days: list[str],
    *,
    stride: int = 36,
    max_per_day: int = 4,
) -> list[dict[str, Any]]:
    holdout = set(holdout_days())
    rows: list[dict[str, Any]] = []
    for day in days:
        if day in holdout:
            continue
        root = root_for_day(day)
        if root is None:
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        ticks = _load_ticks(day)
        by = ticks_by_m5_bar(ticks)
        first, last = 48, len(m5) - 13
        if last < first:
            continue
        n = 0
        idx = first
        while idx <= last and n < max_per_day:
            buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            if buy.get("data_quality_status") == "OK" and sell.get("data_quality_status") == "OK":
                event_id = f"{day}:{idx}"
                rows.append(
                    {
                        "event_id": event_id,
                        "day": day,
                        "idx": idx,
                        "buy_net_r": float(buy["net_r"]),
                        "sell_net_r": float(sell["net_r"]),
                        "buy_gross_r": float(buy.get("gross_r") or buy["net_r"]),
                        "sell_gross_r": float(sell.get("gross_r") or sell["net_r"]),
                        "buy_entry_ask": buy.get("entry_ask"),
                        "buy_entry_bid": buy.get("entry_bid"),
                        "sell_entry_ask": sell.get("entry_ask"),
                        "sell_entry_bid": sell.get("entry_bid"),
                        "commission": None,
                        "slippage_actual": None,
                        "holdout": False,
                    }
                )
                n += 1
            idx += stride
    return rows
