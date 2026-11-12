"""Slippage methodology — separate actual vs historical quote proxy."""

from __future__ import annotations

from typing import Any

from phase60.constants import BOOTSTRAP_SEED, canonical_json_sha256


def executable_side(*, action: str, leg: str) -> str:
    """Return BID or ASK for entry/exit legs."""
    a = action.upper()
    l = leg.upper()
    if l == "ENTRY":
        return "ASK" if a == "BUY" else "BID"
    if l == "EXIT":
        return "BID" if a == "BUY" else "ASK"
    raise ValueError(f"unknown leg:{leg}")


def fill_from_quote(tick: dict[str, Any], *, action: str, leg: str) -> float | None:
    side = executable_side(action=action, leg=leg)
    key = "ask" if side == "ASK" else "bid"
    if tick.get(key) is None:
        return None
    try:
        return float(tick[key])
    except Exception:
        return None


def measure_slippage(
    *,
    intended_price: float | None,
    fill_price: float | None,
    action: str,
    leg: str,
) -> dict[str, Any]:
    """Signed slippage vs intended: adverse positive for losses vs intent."""
    if intended_price is None or fill_price is None:
        return {"slippage": None, "status": "UNKNOWN", "reason": "missing_price"}
    side = executable_side(action=action, leg=leg)
    raw = float(fill_price) - float(intended_price)
    # BUY entry (ASK): higher fill is adverse; SELL entry (BID): lower fill adverse
    if action.upper() == "BUY" and leg.upper() == "ENTRY":
        adverse = raw
    elif action.upper() == "SELL" and leg.upper() == "ENTRY":
        adverse = -raw
    elif action.upper() == "BUY" and leg.upper() == "EXIT":
        adverse = -raw  # lower exit bid is adverse
    else:  # SELL EXIT at ASK
        adverse = raw  # higher exit ask to cover is adverse for short? For short exit buy-back higher is adverse
        # SELL exit buys back at ASK: higher ASK is adverse → adverse = raw
    return {
        "intended_price": float(intended_price),
        "fill_price": float(fill_price),
        "executable_side": side,
        "raw_delta": raw,
        "adverse_signed": adverse,
        "status": "COMPUTED",
    }


def build_execution_price_semantics() -> dict[str, Any]:
    out = {
        "BUY_entry": "ASK",
        "SELL_entry": "BID",
        "BUY_exit": "BID",
        "SELL_exit": "ASK",
        "decision_price_label": "INTENDED_OR_SIGNAL_PRICE — must be explicitly defined per study",
        "simulated_fill_label": "HISTORICAL_QUOTE_BASED_SIMULATION — not broker-confirmed",
        "actual_broker_fill_label": "Only when genuine historical execution records exist",
        "never": [
            "Never label historical quote movement alone as measured broker slippage",
            "Never invent missing ticks",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def build_slippage_methodology() -> dict[str, Any]:
    out = {
        "fields": [
            "decision_intended_price",
            "decision_timestamp",
            "order_submission_timestamp_if_available",
            "first_executable_quote_after_decision",
            "simulated_fill_price",
            "actual_broker_fill_price",
            "measured_slippage_vs_benchmark",
        ],
        "actual_slippage_status": "UNKNOWN",
        "actual_slippage_reason": "No genuine broker order/fill records in archives for target venue",
        "proxy_name": "HISTORICAL_QUOTE_FIRST_EXECUTABLE_AFTER_DECISION",
        "proxy_definition": (
            "If decision timestamp maps to an M5 bar, intended = mid or signal price as labeled; "
            "simulated fill = first valid executable-side quote on the next bar (entry path). "
            "Delta is PROXY only."
        ),
        "latency_assumption": "LABELED_UNKNOWN — no measured order latency; proxy uses next-bar first tick",
        "missing_quotes": "If first executable quote unavailable → observation excluded, not zeroed",
        "stale_quotes": "Recorded when inter-tick gap > 5 minutes prior to fill tick",
        "invalid_timestamps": "Excluded from proxy sample",
        "seed_for_analyses": BOOTSTRAP_SEED,
        "limitations": [
            "Proxy ≠ live execution cost",
            "Demo tick path ≠ broker matching engine",
            "Commission remains independent UNKNOWN",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def analyze_slippage_proxy(events: list[dict[str, Any]]) -> dict[str, Any]:
    """events: {action, intended, fill, day, event_id} using quote simulation fields only."""
    rows = []
    for e in events:
        m = measure_slippage(
            intended_price=e.get("intended"),
            fill_price=e.get("fill"),
            action=str(e.get("action")),
            leg=str(e.get("leg") or "ENTRY"),
        )
        rows.append({**e, **m, "is_proxy": True, "is_actual_broker_slippage": False})

    adverse = [r["adverse_signed"] for r in rows if r.get("status") == "COMPUTED"]
    fav = sum(1 for x in adverse if x < 0)
    adv = sum(1 for x in adverse if x > 0)
    zero = sum(1 for x in adverse if x == 0)
    out = {
        "proxy_name": "HISTORICAL_QUOTE_FIRST_EXECUTABLE_AFTER_DECISION",
        "n_observations": len(rows),
        "n_computed": len(adverse),
        "n_unknown": sum(1 for r in rows if r.get("status") == "UNKNOWN"),
        "mean_adverse_proxy": (sum(adverse) / len(adverse)) if adverse else None,
        "n_adverse": adv,
        "n_favorable": fav,
        "n_zero": zero,
        "actual_slippage_status": "UNKNOWN",
        "proxy_vs_actual_separated": True,
        "live_execution_cost_claim": False,
        "sample_rows": rows[:20],
        "limitations": [
            "Descriptive proxy on demo quotes only",
            "Not interchangeable with broker slippage",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
