"""Pre-implementation gap analysis (Phase0–53 audit)."""

from __future__ import annotations

from typing import Any

from phase54.constants import REPORTS_DIR
from phase54.progress import write_json


def build_gap_analysis() -> dict[str, Any]:
    rows = [
        {
            "component": "Market observer",
            "existing": "phase40/43/49/51/53 acquisition+data; phase29/28 observers (legacy)",
            "missing": "Incremental validated observation object for agent loop; reject stale/incomplete",
            "action": "NEW wrap in phase54.observer using phase49 features + archive loader",
        },
        {
            "component": "Data validation",
            "existing": "aibot_time; phase40.validation; phase43.quality; outcome data_quality_status",
            "missing": "Streaming observation QC API unified for paper agent",
            "action": "WRAP aibot_time + bar/tick checks in observer.validate",
        },
        {
            "component": "Feature engine",
            "existing": "phase49.features.compute_features + registry",
            "missing": "Warm cache across day boundary (optional)",
            "action": "REUSE phase49.compute_features by import",
        },
        {
            "component": "Decision engine",
            "existing": "phase6/9/14 engines; phase50 policies; phase51 FrozenAIBOTCandidate; phase53 families (NO_EDGE)",
            "missing": "Pluggable decide() for NO_MODEL default WAIT without reviving failed policies",
            "action": "NEW phase54.decision NullPolicy + Protocol; do not revive phase53",
        },
        {
            "component": "Expected-value interface",
            "existing": "phase46/49 net_r outcomes; phase50 expected_value field",
            "missing": "Structured EV fields only when calibrated — currently unsupported",
            "action": "NEW decision payload fields; leave expected_net_r=None until validated model",
        },
        {
            "component": "Risk engine",
            "existing": "phase6.risk_gate (wait_only / no_model blocks directional)",
            "missing": "Configurable paper limits: size, daily loss, DD, spread, circuit breaker",
            "action": "NEW phase54.risk.RiskManager (paper-only)",
        },
        {
            "component": "Paper execution",
            "existing": "phase10 PaperSimulator (fixture-based); phase39/41 simulate_trade",
            "missing": "Deterministic bid/ask entry/exit from replay ticks with audit trail",
            "action": "NEW phase54.paper_exec wrapping bid/ask rules; no MT5 orders",
        },
        {
            "component": "Position lifecycle",
            "existing": "phase10 open/complete; research event stride",
            "missing": "OBSERVATION→…→EXPERIENCE state machine with restart recovery",
            "action": "NEW phase54.lifecycle persistent FSM",
        },
        {
            "component": "Experience learning",
            "existing": "phase50 ExperienceStore HISTORICAL_HYPOTHETICAL + AGENT_SHADOW (shadow empty)",
            "missing": "Agent path that appends SHADOW; hist counterfactuals in agent runs",
            "action": "WRAP phase50 stores into phase54.experience with isolated data root",
        },
        {
            "component": "Reporting",
            "existing": "per-phase progress + FINAL_REPORT patterns",
            "missing": "Operational paper-agent dashboard (UTC+PKT)",
            "action": "NEW phase54.reporting",
        },
        {
            "component": "Recovery and monitoring",
            "existing": "acquisition_state.json resume in phase49/51/53",
            "missing": "Idempotent decision/position recovery for agent loop",
            "action": "NEW phase54.state + lifecycle checkpoint",
        },
    ]
    report = {
        "phase": 54,
        "priority": "70% engineering / 30% research readiness",
        "champion": "NO_MODEL",
        "production": "WAIT",
        "phase53_note": "NO_EDGE_FOUND — failed candidates not revived",
        "rows": rows,
    }
    write_json(REPORTS_DIR / "gap_analysis.json", report)
    return report
