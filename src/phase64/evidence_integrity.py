"""Execution evidence integrity rules — UNKNOWN costs must never become zero."""

from __future__ import annotations

from typing import Any

from phase64.constants import canonical_json_sha256


def _unknown(v: Any) -> bool:
    return v is None or v == "UNKNOWN"


def slippage(
    *,
    side: str,
    requested_price: float | None,
    actual_fill_price: float | None,
) -> dict[str, Any]:
    if requested_price is None or actual_fill_price is None:
        return {
            "slippage": "UNKNOWN",
            "direction": "UNKNOWN",
            "note": "Cannot compute slippage without requested and actual prices",
        }
    raw = float(actual_fill_price) - float(requested_price)
    # BUY: positive slippage = worse (paid more); SELL: positive = better (sold higher) — report signed vs adverse
    if side == "BUY":
        adverse = raw  # paid more than requested → adverse positive
        direction = "ADVERSE" if adverse > 0 else ("FAVORABLE" if adverse < 0 else "FLAT")
    elif side == "SELL":
        adverse = -raw  # sold lower than requested → adverse positive
        direction = "ADVERSE" if adverse > 0 else ("FAVORABLE" if adverse < 0 else "FLAT")
    else:
        return {"slippage": "UNKNOWN", "direction": "UNKNOWN", "note": "side must be BUY or SELL"}
    return {
        "slippage": raw,
        "adverse_signed": adverse,
        "direction": direction,
        "requested_price": requested_price,
        "actual_fill_price": actual_fill_price,
        "side": side,
    }


def audit_cost_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Ensure missing costs stay UNKNOWN — never coerced to 0."""
    fields = ["commission", "fee", "swap", "slippage", "latency_ms", "spread_at_decision", "spread_at_exec"]
    issues = []
    normalized: dict[str, Any] = {}
    for f in fields:
        v = row.get(f)
        if v == 0 and row.get(f"{f}_source") in (None, "MISSING", "UNKNOWN"):
            issues.append(f"{f}_zero_without_evidence")
            normalized[f] = "UNKNOWN"
        elif _unknown(v):
            normalized[f] = "UNKNOWN"
        else:
            normalized[f] = v
    return {
        "normalized": normalized,
        "issues": issues,
        "unknown_not_zero": len(issues) == 0,
        "rule": "Missing costs remain UNKNOWN, never zero",
    }


def audit_fill_versus_request(row: dict[str, Any]) -> dict[str, Any]:
    side = str(row.get("side") or "")
    slip = slippage(
        side=side,
        requested_price=row.get("requested_price"),
        actual_fill_price=row.get("actual_fill_price"),
    )
    bid_d = row.get("bid_at_decision")
    ask_d = row.get("ask_at_decision")
    bid_e = row.get("bid_at_exec")
    ask_e = row.get("ask_at_exec")
    spread_decision = None
    spread_exec = None
    if bid_d is not None and ask_d is not None:
        spread_decision = float(ask_d) - float(bid_d)
    if bid_e is not None and ask_e is not None:
        spread_exec = float(ask_e) - float(bid_e)

    contradictory = []
    if row.get("actual_fill_price") is not None and row.get("rejection_or_execution_status") == "REJECTED":
        contradictory.append("fill_present_on_rejected_order")
    if row.get("record_kind") == "ORDER" and row.get("actual_fill_price") is not None:
        contradictory.append("order_record_must_not_be_treated_as_fill")

    costs = audit_cost_fields(
        {
            "commission": row.get("commission"),
            "fee": row.get("fee"),
            "swap": row.get("swap"),
            "slippage": slip.get("slippage") if slip.get("slippage") != "UNKNOWN" else None,
            "latency_ms": row.get("latency_ms"),
            "spread_at_decision": spread_decision,
            "spread_at_exec": spread_exec,
            "commission_source": row.get("commission_source"),
            "fee_source": row.get("fee_source"),
            "swap_source": row.get("swap_source"),
            "slippage_source": row.get("slippage_source"),
            "latency_ms_source": row.get("latency_ms_source"),
        }
    )

    out = {
        "slippage": slip,
        "spread_at_decision": spread_decision if spread_decision is not None else "UNKNOWN",
        "spread_at_exec": spread_exec if spread_exec is not None else "UNKNOWN",
        "latency_ms": row.get("latency_ms") if row.get("latency_ms") is not None else "UNKNOWN",
        "costs": costs,
        "contradictions": contradictory,
        "pass": len(contradictory) == 0 and costs["unknown_not_zero"],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def audit_evidence_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results = [audit_fill_versus_request(r) for r in rows]
    out = {
        "n_rows": len(rows),
        "n_pass": sum(1 for r in results if r.get("pass")),
        "n_fail": sum(1 for r in results if not r.get("pass")),
        "results": results,
        "batch_pass": all(r.get("pass") for r in results) if results else True,
        "genuine_broker_evidence_claimed": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
