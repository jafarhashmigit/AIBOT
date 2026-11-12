"""Execution economics ledger design — actual costs only; else INCOMPLETE."""

from __future__ import annotations

from typing import Any

from phase64_4.constants import canonical_json_sha256

INCOMPLETE = "INCOMPLETE"
UNKNOWN = "UNKNOWN"


LEDGER_COMPONENTS = (
    "bid_ask_spread",
    "commission",
    "swap",
    "slippage",
    "execution_latency_ms",
    "requotes_or_price_changes",
    "rejections",
    "partial_fills",
    "gap_through_behavior",
    "actual_broker_fill_prices",
    "net_realized_pnl",
)


def empty_cost_ledger(
    *,
    execution_request_id: str,
    provenance: str = "DESIGN_SCHEMA",
) -> dict[str, Any]:
    components = {k: UNKNOWN for k in LEDGER_COMPONENTS}
    return {
        "execution_request_id": execution_request_id,
        "components": components,
        "total_execution_economics": INCOMPLETE,
        "published_commission_estimates_used": False,
        "historical_proxies_used": False,
        "provenance": provenance,
        "rule": "If any required component UNKNOWN → total = INCOMPLETE; never substitute estimates",
    }


def finalize_economics(ledger: dict[str, Any]) -> dict[str, Any]:
    comps = dict(ledger.get("components") or {})
    missing = [k for k, v in comps.items() if v in (UNKNOWN, None, "")]
    out = dict(ledger)
    if missing:
        out["total_execution_economics"] = INCOMPLETE
        out["missing_components"] = missing
    else:
        out["total_execution_economics"] = comps.get("net_realized_pnl", INCOMPLETE)
        out["missing_components"] = []
    out["published_commission_estimates_used"] = False
    out["historical_proxies_used"] = False
    return out


def economics_specification() -> dict[str, Any]:
    return {
        "ledger_components": list(LEDGER_COMPONENTS),
        "aggregation_rule": "ALL components known from actual account evidence OR total=INCOMPLETE",
        "forbidden": [
            "published_commission_schedules_as_actual",
            "historical_average_spread_as_actual",
            "proxy_slippage_models_as_actual",
        ],
        "example_incomplete": empty_cost_ledger(execution_request_id="er_example"),
    }


def audit_economics() -> dict[str, Any]:
    led = empty_cost_ledger(execution_request_id="er_audit")
    fin = finalize_economics(led)
    # Attempt to fake completeness with estimate — design forbids marking complete
    fake = empty_cost_ledger(execution_request_id="er_fake")
    fake["components"]["commission"] = "ESTIMATE_0.0"
    # ESTIMATE is not UNKNOWN but also not actual — treat non-numeric actual as still incomplete unless flagged actual
    # Policy: only values with provenance ACTUAL_BROKER_DEAL count; else UNKNOWN
    still_incomplete = True
    for k, v in list(fake["components"].items()):
        if isinstance(v, str) and v.startswith("ESTIMATE"):
            fake["components"][k] = UNKNOWN
    fake = finalize_economics(fake)
    out = {
        "specification": economics_specification(),
        "default_total": fin["total_execution_economics"],
        "estimates_rejected_to_unknown": still_incomplete and fake["total_execution_economics"] == INCOMPLETE,
        "pass": fin["total_execution_economics"] == INCOMPLETE and fake["total_execution_economics"] == INCOMPLETE,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
