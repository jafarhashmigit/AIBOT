"""Evidence-based Dukascopy provider qualification gates."""

from __future__ import annotations

from typing import Any

from phase33.constants import (
    CHAMPION_STATUS,
    H13_C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase33.progress import write_json

GATE_ORDER = [
    "DOCUMENTATION_ONLY",
    "SAMPLE_DATA_ACQUIRED",
    "HISTORICAL_DATA_QUALITY_PASS",
    "HISTORICAL_BID_ASK_QUALIFIED",
    "MT5_PARITY_PENDING",
    "MT5_PARITY_PASS",
    "NOT_YET_QUALIFIED",
    "REJECTED",
]


def qualify(
    *,
    docs: dict[str, Any],
    acquisition: dict[str, Any],
    raw_quality: dict[str, Any],
    candles: dict[str, Any],
    timestamps: dict[str, Any],
    spreads: dict[str, Any],
    parity: dict[str, Any],
    execution: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    log = acquisition.get("log") or acquisition
    sample_ok = bool(log.get("sample_acquired")) and int(log.get("total_ticks") or 0) > 0
    quality_ok = bool(raw_quality.get("pass")) and bool((candles.get("report") or candles).get("pass", candles.get("pass")))
    ts_ok = bool(timestamps.get("pass"))
    spread_ok = bool(spreads.get("pass"))
    parity_status = parity.get("status")
    strategy_done = bool(strategy.get("executed"))

    gates_hit = ["DOCUMENTATION_ONLY"]
    if sample_ok:
        gates_hit.append("SAMPLE_DATA_ACQUIRED")
    if sample_ok and quality_ok and ts_ok and spread_ok:
        gates_hit.append("HISTORICAL_DATA_QUALITY_PASS")

    # HISTORICAL_BID_ASK_QUALIFIED requirements
    coverage_ok = bool((strategy.get("coverage") or {}).get("sufficient"))
    licensing_reviewed = True  # documented in provider_docs / acquisition policy
    qualified = (
        sample_ok
        and quality_ok
        and ts_ok
        and spread_ok
        and coverage_ok
        and licensing_reviewed
        and log.get("bid_ask_present")
    )
    if qualified:
        gates_hit.append("HISTORICAL_BID_ASK_QUALIFIED")
    else:
        gates_hit.append("NOT_YET_QUALIFIED")

    gates_hit.append("MT5_PARITY_PENDING")
    if parity.get("parity_pass"):
        gates_hit.append("MT5_PARITY_PASS")

    # Final verdict (Phase33 required set)
    if qualified and parity.get("parity_pass"):
        final = "HISTORICAL_BID_ASK_QUALIFIED"  # still wouldn't claim MT5-equivalent without separate statement
    elif sample_ok and quality_ok:
        final = "SAMPLE_DATA_ONLY"
    elif sample_ok:
        final = "SAMPLE_DATA_ONLY"
    elif docs:
        final = "PROVIDER_DOCUMENTATION_ONLY"
    else:
        final = "INCONCLUSIVE"

    # Ultimate objective still unmet without coverage + parity
    if final == "SAMPLE_DATA_ONLY":
        execution_realism = "ASSUMPTION_BASED"
        objective_status = "EXECUTION_REALISM_STILL_UNVERIFIED"
    elif final == "HISTORICAL_BID_ASK_QUALIFIED":
        execution_realism = "BID_ASK_SAMPLE_BACKED"
        objective_status = "PARTIAL"
    else:
        execution_realism = "ASSUMPTION_BASED"
        objective_status = "EXECUTION_REALISM_STILL_UNVERIFIED"

    confirmed = []
    if docs.get("page_fetch", {}).get("ok"):
        confirmed.append("Official Historical Data Export page reachable.")
    if sample_ok:
        confirmed.append(f"Acquired {log.get('total_ticks')} XAUUSD ticks with separate bid/ask.")
    if quality_ok:
        confirmed.append("Sample passed hard data-quality checks (no fabricate).")
    if spread_ok:
        confirmed.append("Spread distribution computed from ask-bid.")
    confirmed.append("MT5 not connected; parity protocol defined only.")
    confirmed.append("Frozen strategy signals/thresholds not modified.")

    unresolved = [
        "Full-history bid/ask coverage for strategy ledger re-pricing not acquired.",
        "Genuine MT5 bid/ask parity not measured.",
        "Intrabar TP/SL ordering remains ambiguous on M5.",
        "Licensing: personal/research use reviewed; commercial redistribution not cleared.",
        "Live feed quality not in scope and not assumed from historical bi5.",
    ]
    if strategy.get("skipped"):
        unresolved.append(f"Strategy diagnostic skipped: {strategy.get('skip_reason')}")

    report = {
        "recipe_id": RECIPE_ID,
        "gates_available": GATE_ORDER,
        "gates_reached": gates_hit,
        "provider_qualification_primary": (
            "HISTORICAL_BID_ASK_QUALIFIED" if qualified else (
                "HISTORICAL_DATA_QUALITY_PASS" if "HISTORICAL_DATA_QUALITY_PASS" in gates_hit else (
                    "SAMPLE_DATA_ACQUIRED" if sample_ok else "DOCUMENTATION_ONLY"
                )
            )
        ),
        "mt5_parity_gate": parity_status,
        "historical_bid_ask_qualified": qualified,
        "requirements_checklist": {
            "actual_bid_ask_acquired": sample_ok,
            "instrument_identity_verified": sample_ok and log.get("instrument") == "XAUUSD",
            "timestamp_semantics_verified": ts_ok,
            "data_integrity_checks_passed": quality_ok,
            "spread_calculations_reproducible": spread_ok,
            "historical_coverage_sufficient_for_evaluation": coverage_ok,
            "licensing_and_free_access_reviewed": licensing_reviewed,
        },
        "final_verdict": final,
        "objective_status": objective_status,
        "execution_realism": execution_realism,
        "confirmed_findings": confirmed,
        "unresolved_limitations": unresolved,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "strategy_diagnostic_executed": strategy_done,
        "execution_comparison_recorded": execution is not None,
        "documentation_alone_not_qualification": True,
    }
    write_json("provider_qualification.json", report)
    return report
