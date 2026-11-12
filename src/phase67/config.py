"""Validated operational config for supervised READ_ONLY collector."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CollectorConfig:
    interval_sec: float = 30.0
    m5_lookback: int = 50
    max_retries: int = 5
    backoff_initial_sec: float = 2.0
    backoff_max_sec: float = 60.0
    stale_data_threshold_sec: float = 300.0
    shutdown_timeout_sec: float = 30.0
    max_cycles: int | None = None
    duration_sec: float | None = None

    def validate(self) -> None:
        if self.interval_sec < 5.0:
            raise ValueError("interval_sec must be >= 5 (no tight unbounded loop)")
        if self.interval_sec > 3600.0:
            raise ValueError("interval_sec must be <= 3600")
        if self.m5_lookback < 1 or self.m5_lookback > 500:
            raise ValueError("m5_lookback must be in [1, 500]")
        if self.max_retries < 0 or self.max_retries > 50:
            raise ValueError("max_retries must be in [0, 50]")
        if self.backoff_initial_sec <= 0 or self.backoff_max_sec < self.backoff_initial_sec:
            raise ValueError("invalid backoff bounds")
        if self.stale_data_threshold_sec < 30:
            raise ValueError("stale_data_threshold_sec must be >= 30")
        if self.shutdown_timeout_sec < 1:
            raise ValueError("shutdown_timeout_sec must be >= 1")
        if self.duration_sec is not None and self.duration_sec <= 0:
            raise ValueError("duration_sec must be > 0 when set")
        if self.max_cycles is not None and self.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1 when set")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_config(**kwargs: Any) -> CollectorConfig:
    cfg = CollectorConfig(**{k: v for k, v in kwargs.items() if v is not None and k in CollectorConfig.__dataclass_fields__})
    cfg.validate()
    return cfg
