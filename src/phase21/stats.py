"""Distribution helpers for Phase 21 research."""

from __future__ import annotations

import math
from typing import Iterable


def percentile_sorted(values: list[float], q: float) -> float:
    """Linear-interpolation percentile on a pre-sorted or unsorted list."""
    if not values:
        return float("nan")
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    pos = (q / 100.0) * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def summarize_numeric(values: Iterable[float]) -> dict[str, float]:
    xs = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not xs:
        return {
            "n": 0,
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
            "median": float("nan"),
            "std": float("nan"),
            "q1": float("nan"),
            "q5": float("nan"),
            "q10": float("nan"),
            "q25": float("nan"),
            "q50": float("nan"),
            "q75": float("nan"),
            "q90": float("nan"),
            "q95": float("nan"),
            "q99": float("nan"),
        }
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    return {
        "n": len(xs),
        "min": min(xs),
        "max": max(xs),
        "mean": mean,
        "median": percentile_sorted(xs, 50),
        "std": math.sqrt(var),
        "q1": percentile_sorted(xs, 1),
        "q5": percentile_sorted(xs, 5),
        "q10": percentile_sorted(xs, 10),
        "q25": percentile_sorted(xs, 25),
        "q50": percentile_sorted(xs, 50),
        "q75": percentile_sorted(xs, 75),
        "q90": percentile_sorted(xs, 90),
        "q95": percentile_sorted(xs, 95),
        "q99": percentile_sorted(xs, 99),
    }
