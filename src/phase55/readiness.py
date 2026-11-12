"""Operational readiness audit for continuous observation — estimate only, no loop."""

from __future__ import annotations

from typing import Any

from phase55.constants import REPORTS_DIR
from phase55.progress import write_json


def continuous_operation_audit() -> dict[str, Any]:
    items = [
        {
            "requirement": "Bounded polling architecture",
            "status": "MISSING",
            "notes": "Phase54/55 are historical replay only; need bounded poll with max iterations/wall clock",
            "estimate_hours": 6,
        },
        {
            "requirement": "New candle detection",
            "status": "MISSING",
            "notes": "Need last_bar_ts cursor vs incoming M5 open",
            "estimate_hours": 3,
        },
        {
            "requirement": "Duplicate candle protection",
            "status": "PARTIAL",
            "notes": "AgentState.already_processed covers decision keys; needs candle-hash guard for poller",
            "estimate_hours": 2,
        },
        {
            "requirement": "Stale-feed detection",
            "status": "MISSING",
            "notes": "Heartbeat age vs wall clock; reject stale observations (observer rejects incomplete only)",
            "estimate_hours": 3,
        },
        {
            "requirement": "Data-quality circuit breaker",
            "status": "PARTIAL",
            "notes": "RiskManager circuit on errors exists; not wired to feed-staleness metrics",
            "estimate_hours": 2,
        },
        {
            "requirement": "Graceful shutdown",
            "status": "MISSING",
            "notes": "Need signal handler + persist open positions + flush stores",
            "estimate_hours": 3,
        },
        {
            "requirement": "Restart recovery",
            "status": "PARTIAL",
            "notes": "State persistence exists; OPEN-position continue path verified in Phase55 harness",
            "estimate_hours": 2,
        },
        {
            "requirement": "Operational health monitoring",
            "status": "PARTIAL",
            "notes": "operational_report exists; need continuous heartbeat file",
            "estimate_hours": 3,
        },
    ]
    blockers = [
        "No live/demo streaming feed (by design restriction — no live MT5 in this phase)",
        "No automatic startup (required restriction)",
        "Broker execution out of scope — paper only",
        "NullPolicy remains production default — no validated edge",
    ]
    total = sum(int(i["estimate_hours"]) for i in items)
    report = {
        "items": items,
        "total_estimate_hours": total,
        "blockers": blockers,
        "recommendation": (
            "After PAPER_EXECUTION_VERIFIED, implement a bounded offline-or-demo poller behind an "
            "explicit CLI flag (never auto-start), reusing Phase54 lifecycle + Phase55 recovery patterns."
        ),
        "do_not": ["unbounded_loop", "live_broker", "auto_startup", "phase56_auto"],
    }
    write_json(REPORTS_DIR / "continuous_operation_readiness.json", report)
    return report
