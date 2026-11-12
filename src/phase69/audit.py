"""Initial repository audit for Phase 69."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase69.constants import PHASE67_JOURNAL, PROJECT_ROOT, canonical_json_sha256


def initial_audit() -> dict[str, Any]:
    defects = [
        {
            "id": "D69_1",
            "severity": (
                "Phase66/67 ingest labeled all live-path M5 as source_classification=BROKER_OBSERVED, "
                "including copy_rates lookback bars closed before process start. Phase68 post-hoc "
                "accounting separated backfill (245) from newly closed live (0), proving the defect."
            ),
            "fix": (
                "Phase69 stamps evidence_provenance at ingest (HISTORICAL_BACKFILL vs "
                "BROKER_OBSERVED_LIVE_BAR vs BROKER_OBSERVED_QUOTE); accounting uses unique live bars only."
            ),
            "severity_before_fix": True,
        },
        {
            "id": "D69_2",
            "severity": "Short verify runs can inflate event counts if backfill is treated as live progress.",
            "fix": "Sufficiency uses n_independent_live_dates from BROKER_OBSERVED_LIVE_BAR only.",
            "severity_before_fix": True,
        },
    ]
    out = {
        "phases_inspected": ["phase66", "phase67", "phase68"],
        "collector_reused": "phase66.collect_once + phase67.service.run_loop",
        "journal_reused": str(PHASE67_JOURNAL),
        "second_collector_created": False,
        "second_journal_created": False,
        "permitted_mt5_apis": sorted(PERMITTED_MT5_API),
        "prohibited_sample": sorted(list(PROHIBITED_MT5_API))[:8],
        "tick_apis_permitted": {
            a: a in PERMITTED_MT5_API for a in ("copy_ticks_from", "copy_ticks_range", "symbol_info_tick")
        },
        "existing_integrity": [
            "phase64_5 BrokerEvidenceJournal dedup/WAL/quarantine",
            "phase68 live_integrity backfill vs newly observed",
            "phase66 synthetic blocked from genuine store",
        ],
        "existing_tests": [
            "phase66 synthetic_not_in_genuine",
            "phase68 test_live_backfill_split",
            "phase12 allowlist",
        ],
        "defects_documented_before_fix": defects,
        "phase58_holdout_policy": "untouched",
        "reports_present": {
            "phase66": (PROJECT_ROOT / "reports" / "phase66" / "PHASE66_FINAL_REPORT.md").is_file(),
            "phase67": (PROJECT_ROOT / "reports" / "phase67" / "PHASE67_FINAL_REPORT.md").is_file(),
            "phase68": (PROJECT_ROOT / "reports" / "phase68" / "PHASE68_FINAL_REPORT.md").is_file(),
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
