"""Final architecture path audit for Prompt10."""

from __future__ import annotations

from typing import Any

from phase67.service import health_check, single_instance_status
from phase69.accounting import build_live_evidence_accounting
from phase67.session_evidence import build_session_evidence_report
from phase16b.secrets import safe_config_status, webhook_configured
from signal_bot.final_delivery.constants import (
    CHAMPION_STATUS,
    PRODUCTION_FINAL_ACTION,
    PROMPT09_VERDICT,
    STATUS_ENGINEERING,
    STATUS_LIVE_TRADING,
    STATUS_QUANT,
    STATUS_RUNTIME,
)
from signal_bot.orchestrator.service import health as orch_health


def build_architecture_audit() -> dict[str, Any]:
    try:
        health = health_check()
    except Exception as exc:  # noqa: BLE001
        health = {"service_status": "ERROR", "error": str(exc)}
    try:
        acc = build_live_evidence_accounting()
    except Exception as exc:  # noqa: BLE001
        acc = {"error": str(exc)}
    try:
        sess = build_session_evidence_report()
    except Exception as exc:  # noqa: BLE001
        sess = {"error": str(exc)}
    inst = single_instance_status()
    try:
        oh = orch_health()
    except Exception as exc:  # noqa: BLE001
        oh = {"error": str(exc)}

    path = [
        {"step": 1, "component": "Exness MT5 READ_ONLY", "status": health.get("mt5_connection_state") or "UNKNOWN"},
        {"step": 2, "component": "Live quote/M5 collection", "status": health.get("service_status")},
        {"step": 3, "component": "Evidence journal", "status": "OPERATIONAL" if not acc.get("error") else "ERROR"},
        {"step": 4, "component": "Closed-candle validation", "status": "IMPLEMENTED (forming skipped)"},
        {"step": 5, "component": "Signal orchestrator", "status": "IMPLEMENTED (Prompt6)"},
        {"step": 6, "component": "Phase54 NullPolicy", "status": "ACTIVE → WAIT"},
        {"step": 7, "component": "Risk/publication gates", "status": "HARD_BLOCK actionable"},
        {"step": 8, "component": "Decision ledger", "status": "IMPLEMENTED"},
        {"step": 9, "component": "Discord operational reporting", "status": "SHADOW default; live ops opt-in"},
    ]

    defects: list[str] = []
    if health.get("service_status") != "RUNNING":
        defects.append("collector_not_running_at_audit_time")
    if int(sess.get("n_independent_complete_live_dates") or 0) == 0:
        defects.append("no_complete_independent_live_dates — expected; not an integration defect")

    return {
        "four_statuses": {
            "software_engineering_readiness": STATUS_ENGINEERING,
            "operational_runtime_verification": (
                "VERIFIED_RUNNING"
                if health.get("service_status") == "RUNNING"
                else "NOT_RUNNING_AT_AUDIT"
            ),
            "quantitative_strategy_validation": STATUS_QUANT,
            "live_trading_authorization": STATUS_LIVE_TRADING,
        },
        "operational_path": path,
        "canonical_symbol": "XAUUSDm",
        "timeframe": "M5",
        "timezones": {"utc": True, "asia_karachi_pkt": True},
        "live_vs_backfill": {
            "live_m5": acc.get("unique_newly_closed_live_m5_bars"),
            "backfill_m5": acc.get("unique_historical_backfill_m5_bars"),
            "quotes": acc.get("live_quote_observations"),
            "complete_dates": sess.get("n_independent_complete_live_dates"),
        },
        "duplicate_suppression": "journal market_identity + delivery ledger dedupe",
        "conflict_quarantine": "BrokerEvidenceJournal incidents/quarantine",
        "stale_data": "orchestrator forced WAIT on stale",
        "closed_bar_only": "forming_bar → WAIT",
        "single_instance": inst,
        "collector_health": {
            "service_status": health.get("service_status"),
            "pid": health.get("pid"),
            "pid_alive": health.get("pid_alive"),
            "mt5": health.get("mt5_connection_state"),
        },
        "orchestrator_health": oh,
        "discord_webhook_configured": webhook_configured(),
        "discord_config_safe": safe_config_status(),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "prompt09_verdict": PROMPT09_VERDICT,
        "integration_defects_requiring_code_fix": [
            d for d in defects if "not an integration defect" not in d
        ],
        "notes": defects,
    }
