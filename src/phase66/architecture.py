"""Architecture inventory — reuse existing collectors; do not duplicate."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API, PHASE64_8_APPROVED_READ_ONLY
from phase66.constants import canonical_json_sha256


def build_architecture_inventory() -> dict[str, Any]:
    out = {
        "existing_collection_components": [
            {
                "component": "phase64_8.collector",
                "role": "Read-only broker positions/orders/history → BrokerEvidenceJournal",
                "reuse": "Reuse for account/trade-history evidence; not M5 market stream",
            },
            {
                "component": "phase64_7.live_probe",
                "role": "symbol_info/account_info/copy_rates_from_pos snapshot",
                "reuse": "Pattern for permitted market snapshot APIs",
            },
            {
                "component": "phase64_6.readonly_adapter.LiveMt5Backend/FakeMt5Backend",
                "role": "Permitted MT5 backend abstraction",
                "reuse": "Reuse as market-collection backend",
            },
            {
                "component": "phase64_5.BrokerEvidenceJournal",
                "role": "Append-only journal, WAL, idempotent ingest, quarantine",
                "reuse": "Primary persistence for Phase66 market evidence",
            },
            {
                "component": "phase58/49/43 archives",
                "role": "Historical M5/ticks jsonl (MetaQuotes-Demo)",
                "reuse": "HISTORICAL_ARCHIVE class only; not live Exness ticks",
            },
            {
                "component": "phase64_13.schedule",
                "role": "XAUUSDm session states OPEN/CLOSE_ONLY/BREAK/CLOSED/UNKNOWN",
                "reuse": "Session-aware collection labeling",
            },
        ],
        "permitted_mt5_apis": sorted(PERMITTED_MT5_API),
        "phase64_8_ro_apis": sorted(PHASE64_8_APPROVED_READ_ONLY),
        "prohibited_mt5_apis_sample": sorted(list(PROHIBITED_MT5_API)[:12]),
        "market_collection_apis_used": ["symbol_info", "copy_rates_from_pos", "account_info", "terminal_info"],
        "apis_not_used_unapproved": ["copy_ticks_from", "copy_ticks_range", "symbol_info_tick"],
        "persistence": "phase64_5.BrokerEvidenceJournal (append-only, WAL, dedup index)",
        "recovery": "WAL recover + reconstruct_index + quarantine corrupt",
        "existing_schemas": ["phase64_8 broker evidence records", "phase58 archive jsonl"],
        "missing_capabilities_before_phase66": [
            "Dedicated continuous market-evidence collector for bid/ask snapshots + M5 rates",
            "Evidence-class taxonomy for market observations",
            "Collection health/watermark for market stream",
            "Research-eligibility registry for newly collected market dates",
        ],
        "reuse_decisions": [
            "Do NOT build a second BrokerEvidenceJournal",
            "Do NOT expand allowlist for tick copy APIs",
            "Do NOT rewrite Phase64.8 trade-history collector",
            "Extend with Phase66 market snapshot/rates collector on Fake/Live Mt5Backend",
        ],
        "security_boundaries": [
            "order_send PROHIBITED",
            "BROKER_SUBMISSION_ENABLED=False",
            "BROKER_EXECUTION_AUTHORIZED=False",
            "Wrong symbol/server fail-closed",
            "Synthetic fixtures never enter genuine store",
        ],
        "second_collector_built": False,
        "note": "Tick-stream APIs are not Phase12-permitted; bid/ask from symbol_info only",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
