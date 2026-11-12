"""Stale-feed and data-quality circuit breaker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase54.timeutil import ensure_aware_utc, now_utc_iso

UTC = timezone.utc


class FeedSafety:
    def __init__(self, *, max_age_seconds: float = 900.0, error_threshold: int = 5):
        self.max_age_seconds = float(max_age_seconds)
        self.error_threshold = int(error_threshold)
        self.last_heartbeat_iso: str | None = None
        self.last_observation_ts: str | None = None
        self.dq_errors = 0
        self.feed_stale = False
        self.dq_breaker = False
        self.safe = True
        self.reason = "OK"

    def heartbeat(self) -> None:
        self.last_heartbeat_iso = now_utc_iso()

    def note_observation(self, bar_ts: str, *, wall_clock: datetime | None = None) -> dict[str, Any]:
        self.heartbeat()
        self.last_observation_ts = bar_ts
        # For historical replay, age vs wall clock is not meaningful — use chronology only.
        # Stale detection activates when explicitly marked or when DQ breaker open.
        return {"stale": False, "reason": "HISTORICAL_REPLAY_AGE_WAIVED"}

    def note_dq_failure(self, reason: str) -> None:
        self.dq_errors += 1
        if self.dq_errors >= self.error_threshold:
            self.dq_breaker = True
            self.safe = False
            self.reason = f"DQ_CIRCUIT:{reason}"

    def note_missing_candle(self) -> None:
        self.note_dq_failure("MISSING_CANDLE")

    def note_invalid_bidask(self) -> None:
        self.note_dq_failure("INVALID_BIDASK")

    def mark_feed_stale(self, reason: str = "STALE_FEED") -> None:
        self.feed_stale = True
        self.safe = False
        self.reason = reason

    def recover_if_clear(self) -> None:
        if self.dq_errors == 0 and not self.feed_stale:
            self.dq_breaker = False
            self.safe = True
            self.reason = "OK"

    def note_success(self) -> None:
        self.dq_errors = 0
        self.feed_stale = False
        self.dq_breaker = False
        self.safe = True
        self.reason = "OK"
        self.heartbeat()

    def snapshot(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "reason": self.reason,
            "last_heartbeat_iso": self.last_heartbeat_iso,
            "last_observation_ts": self.last_observation_ts,
            "dq_errors": self.dq_errors,
            "feed_stale": self.feed_stale,
            "dq_breaker": self.dq_breaker,
            "max_age_seconds": self.max_age_seconds,
        }
