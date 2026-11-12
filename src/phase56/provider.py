"""Market data provider interface — historical replay now; streaming later."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from phase54.archive_loader import list_archived_m5_days, load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase56.constants import ARCHIVE_ROOT, HORIZON_BARS


class MarketDataProvider(Protocol):
    def candles(self) -> Iterator[dict[str, Any]]:
        """Yield completed candle contexts: day, idx, m5, h1, ticks_by_bar, bar."""


class HistoricalReplayProvider:
    """Bounded historical archive provider (no live MT5)."""

    def __init__(
        self,
        *,
        archive_root=None,
        days: list[str] | None = None,
        start_idx: int = 48,
        stride: int = 1,
        max_candles: int | None = None,
    ):
        self.archive_root = archive_root or ARCHIVE_ROOT
        self.days = days or list_archived_m5_days(self.archive_root)
        self.start_idx = start_idx
        self.stride = stride
        self.max_candles = max_candles
        self.provenance = {
            "source": "historical_archive",
            "archive_root": str(self.archive_root),
            "days": list(self.days),
            "live_mt5": False,
            "streaming": False,
        }

    def candles(self) -> Iterator[dict[str, Any]]:
        n = 0
        for day in self.days:
            m5 = load_m5(self.archive_root, day)
            h1 = load_h1(self.archive_root, day)
            by = ticks_by_m5_bar(load_ticks(self.archive_root, day))
            last = len(m5) - 1
            idx = self.start_idx
            while idx <= last:
                if self.max_candles is not None and n >= self.max_candles:
                    return
                # Need room for entry+horizon when opening — still yield observation candles
                yield {
                    "day": day,
                    "idx": idx,
                    "m5": m5,
                    "h1": h1,
                    "ticks_by_bar": by,
                    "bar": m5[idx],
                    "provenance": self.provenance,
                }
                n += 1
                idx += self.stride
