"""Independent recomputation of core metrics from saved trade records."""

from __future__ import annotations

from typing import Any

from phase35.metrics import summarize_trades


def recompute_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_trades(trades)


def compare_summaries(primary: dict[str, Any], independent: dict[str, Any], *, tol: float = 1e-9) -> dict[str, Any]:
    keys = ["n_resolved", "n_unresolved", "mean_r", "net_r_sum", "max_drawdown_r"]
    mismatches = []
    for k in keys:
        a, b = primary.get(k), independent.get(k)
        if a is None and b is None:
            continue
        if a is None or b is None:
            mismatches.append({"key": k, "primary": a, "independent": b})
            continue
        if isinstance(a, float) or isinstance(b, float):
            if abs(float(a) - float(b)) > tol:
                mismatches.append({"key": k, "primary": a, "independent": b})
        elif a != b:
            mismatches.append({"key": k, "primary": a, "independent": b})
    return {"ok": len(mismatches) == 0, "mismatches": mismatches, "tolerance": tol}
