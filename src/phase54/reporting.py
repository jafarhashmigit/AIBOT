"""Operational reporting — UTC + PKT; never present paper as live profit."""

from __future__ import annotations

from typing import Any

from phase54.constants import (
    AGENT_VERSION,
    CHAMPION_STATUS,
    POLICY_VERSION,
    PRODUCTION_FINAL_ACTION,
    REPORTS_DIR,
)
from phase54.progress import write_json, write_text
from phase54.state import AgentState
from phase54.timeutil import dual_stamp, now_utc_iso


def build_operational_report(
    *,
    state: AgentState,
    risk_snap: dict[str, Any],
    hist_n: int,
    shadow_n: int,
    replay_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = dual_stamp(now_utc_iso())
    counts = state.data.get("counts") or {}
    report = {
        "title": "Phase54 Paper Agent Operational Report",
        "disclaimer": "All positions and PnL are HYPOTHETICAL paper results — not real trading profits.",
        "generated": now,
        "agent_version": AGENT_VERSION,
        "policy_version": POLICY_VERSION,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "validated_profitable_policy": False,
        "market_observations_processed": counts.get("observations", 0),
        "data_quality_failures": counts.get("dq_reject", 0),
        "action_counts": {
            "BUY": counts.get("buy", 0),
            "SELL": counts.get("sell", 0),
            "WAIT": counts.get("wait", 0),
            "decisions": counts.get("decisions", 0),
        },
        "hypothetical_positions_opened": counts.get("opens", 0),
        "hypothetical_positions_closed": counts.get("closes", 0),
        "open_hypothetical_exposure": {
            "n_open": risk_snap.get("n_open"),
            "open_ids": risk_snap.get("open_ids"),
            "equity_r": risk_snap.get("equity_r"),
        },
        "realized_hypothetical_r": risk_snap.get("equity_r"),
        "unrealized_note": "Unrealized tracked only while positions OPEN in state",
        "spread_and_cost_assumptions": {
            "commission": None,
            "slippage": None,
            "execution": "BUY ask→bid / SELL bid→ask; spread once",
        },
        "experience_records": {
            "HISTORICAL_HYPOTHETICAL": hist_n,
            "AGENT_SHADOW": shadow_n,
            "merged": False,
        },
        "agent_errors": state.data.get("errors") or [],
        "last_successful_processing": state.data.get("last_success_iso"),
        "last_success_stamps": dual_stamp(state.data["last_success_iso"])
        if state.data.get("last_success_iso")
        else None,
        "current_policy_version": POLICY_VERSION,
        "current_safety_state": risk_snap.get("safety_state"),
        "circuit_open": risk_snap.get("circuit_open"),
        "cursor": state.data.get("cursor"),
        "replay": replay_meta or {},
    }
    write_json(REPORTS_DIR / "operational_report.json", report)
    md = [
        "# Phase 54 — Operational Report",
        "",
        f"**Generated:** {now['utc']} / {now['pkt']}",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "> Hypothetical paper results only — not live trading profits. No validated profitable policy.",
        "",
        f"- Observations: `{report['market_observations_processed']}`",
        f"- DQ failures: `{report['data_quality_failures']}`",
        f"- Actions BUY/SELL/WAIT: `{report['action_counts']}`",
        f"- Opens/Closes: `{report['hypothetical_positions_opened']}` / `{report['hypothetical_positions_closed']}`",
        f"- Open exposure n: `{report['open_hypothetical_exposure']['n_open']}`",
        f"- Realized hypothetical R: `{report['realized_hypothetical_r']}`",
        f"- Experience hist/shadow: `{hist_n}` / `{shadow_n}`",
        f"- Safety: `{report['current_safety_state']}` circuit=`{report['circuit_open']}`",
        f"- Last success: `{report['last_successful_processing']}`",
        f"- Policy: `{POLICY_VERSION}`",
    ]
    write_text(REPORTS_DIR / "operational_report.md", "\n".join(md) + "\n")
    return report
