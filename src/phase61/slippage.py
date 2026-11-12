"""Actual vs proxy slippage — Exness fills only when genuine records exist."""

from __future__ import annotations

from typing import Any

from phase61.constants import canonical_json_sha256


def signed_entry_slippage(*, side: str, decision_bid: float, decision_ask: float, fill: float) -> dict[str, Any]:
    side = side.upper()
    if side == "BUY":
        bench = float(decision_ask)
        signed = float(fill) - bench  # adverse positive
        return {"benchmark": "decision_ASK", "benchmark_price": bench, "signed": signed, "adverse": max(signed, 0.0)}
    if side == "SELL":
        bench = float(decision_bid)
        signed = bench - float(fill)  # adverse positive when fill below bid
        return {"benchmark": "decision_BID", "benchmark_price": bench, "signed": signed, "adverse": max(signed, 0.0)}
    raise ValueError(f"bad_side:{side}")


def signed_exit_slippage(*, position_side: str, decision_bid: float, decision_ask: float, fill: float) -> dict[str, Any]:
    """BUY position exits via SELL fill vs decision BID; SELL position exits via BUY fill vs decision ASK."""
    ps = position_side.upper()
    if ps == "BUY":
        bench = float(decision_bid)
        signed = bench - float(fill)  # lower sell fill adverse
        return {"benchmark": "decision_BID", "benchmark_price": bench, "signed": signed, "adverse": max(signed, 0.0)}
    if ps == "SELL":
        bench = float(decision_ask)
        signed = float(fill) - bench  # higher buy-back adverse
        return {"benchmark": "decision_ASK", "benchmark_price": bench, "signed": signed, "adverse": max(signed, 0.0)}
    raise ValueError(f"bad_side:{ps}")


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(p * (len(s) - 1))))]


def summarize(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p90": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "median": _pct(values, 0.5),
        "p90": _pct(values, 0.90),
        "p95": _pct(values, 0.95),
        "p99": _pct(values, 0.99),
        "max": max(values),
    }


def build_slippage_study(records: list[dict[str, Any]]) -> dict[str, Any]:
    actual_signed: list[float] = []
    actual_adverse: list[float] = []
    proxy_signed: list[float] = []
    missing = 0
    n_actual_fills = 0

    for r in records:
        cat = r.get("evidence_category")
        if cat in ("EXNESS_DEMO_EXECUTION", "EXNESS_LIVE_EXECUTION"):
            fill = r.get("actual_broker_fill_price")
            bid, ask = r.get("bid_at_decision"), r.get("ask_at_decision")
            side = r.get("side")
            if fill is None or bid is None or ask is None or side not in ("BUY", "SELL"):
                missing += 1
                continue
            m = signed_entry_slippage(side=side, decision_bid=float(bid), decision_ask=float(ask), fill=float(fill))
            actual_signed.append(m["signed"])
            actual_adverse.append(m["adverse"])
            n_actual_fills += 1
        elif cat in ("HISTORICAL_QUOTE_PROXY", "SIMULATED_PAPER"):
            fill = r.get("simulated_fill_price")
            bid, ask = r.get("bid_at_decision"), r.get("ask_at_decision")
            side = r.get("side")
            if fill is None or bid is None or ask is None or side not in ("BUY", "SELL"):
                missing += 1
                continue
            m = signed_entry_slippage(side=side, decision_bid=float(bid), decision_ask=float(ask), fill=float(fill))
            proxy_signed.append(m["signed"])

    actual_status = "MEASURED" if n_actual_fills > 0 else "UNKNOWN"
    out = {
        "actual_slippage_status": actual_status,
        "actual_fill_n": n_actual_fills,
        "actual_signed": summarize(actual_signed),
        "actual_adverse_only": summarize(actual_adverse),
        "proxy_label": "HISTORICAL_QUOTE_OR_SIMULATED_PAPER — not actual broker slippage",
        "proxy_signed": summarize(proxy_signed),
        "missing_record_rate": (missing / len(records)) if records else None,
        "session_breakdown": {},
        "volatility_spread_context": "UNAVAILABLE_WITHOUT_LINKED_MARKET_CONTEXT",
        "volume_context": "UNAVAILABLE",
        "timestamp_alignment": "Requires genuine decision and fill timestamps",
        "live_cost_calibration_from_proxy_alone": False,
        "statistical_confidence_claim": False if n_actual_fills < 200 else "ASSESS_SEPARATELY",
        "limitations": [
            "No Exness fill records in Phase61 store at build time",
            "Proxy must not be labeled actual broker slippage",
            "Inadequate samples must not claim stable live economics",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
