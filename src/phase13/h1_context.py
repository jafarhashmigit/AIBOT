"""Causal H1 EMA context for M5 decisions. Last fully closed H1 bar only."""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def compute_h1_ema20(h1_rows: list[dict]) -> list[dict]:
    """Return rows with ema20; ema undefined until 20 closed bars exist."""
    out = []
    closes = []
    for row in h1_rows:
        closes.append(row["close"])
        if len(closes) < 20:
            ema = None
        elif len(closes) == 20:
            ema = sum(closes) / 20.0
        else:
            prev = out[-1]["ema20"]
            alpha = 2.0 / 21.0
            ema = alpha * row["close"] + (1.0 - alpha) * prev
        out.append({
            "time": row["time"],
            "close": row["close"],
            "ema20": ema,
            "close_time": _fmt(_parse(row["time"]) + timedelta(hours=1)),
        })
    return out


def build_h1_lookup(h1_rows: list[dict]) -> list[dict]:
    return compute_h1_ema20(h1_rows)


def h1_context_at(lookup: list[dict], decision_time: str) -> dict | None:
    """Last H1 bar whose close_time <= decision_time and ema20 is defined."""
    chosen = None
    for row in lookup:
        if row["ema20"] is None:
            continue
        if row["close_time"] <= decision_time:
            chosen = row
        else:
            break
    if chosen is None:
        return None
    return {
        "h1_bar_time": chosen["time"],
        "h1_close": chosen["close"],
        "h1_ema20": chosen["ema20"],
        "h1_trend": "up" if chosen["close"] > chosen["ema20"] else "down",
    }
