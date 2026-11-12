"""Operational health monitoring — UTC + PKT; paper ≠ live."""

from __future__ import annotations

from typing import Any

from phase54.timeutil import dual_stamp, now_utc_iso
from phase56.constants import AGENT_VERSION, CHAMPION_STATUS, POLICY_VERSION, PRODUCTION_FINAL_ACTION, REPORTS_DIR
from phase56.progress import write_json, write_text


def build_health_report(engine, poll_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = engine.state.data.get("counts") or {}
    last = engine.observer.last_success
    now = dual_stamp(now_utc_iso())
    report = {
        "title": "Phase56 Autonomous Replay Agent — Health",
        "disclaimer": "Paper activity only. Not real trading. No validated profitable policy.",
        "generated": now,
        "agent_status": "STOPPED" if engine.shutting_down else "RUNNING_OR_IDLE",
        "agent_version": AGENT_VERSION,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "policy_version": getattr(engine.policy, "version", POLICY_VERSION),
        "last_processed_candle": last,
        "last_processed_stamps": dual_stamp(last["timestamp_utc"]) if last and last.get("timestamp_utc") else None,
        "last_heartbeat": (engine.feed_safety.snapshot() or {}).get("last_heartbeat_iso"),
        "candles_received": engine.metrics.get("candles_received"),
        "candles_accepted": engine.metrics.get("candles_accepted"),
        "candles_rejected": engine.metrics.get("candles_rejected"),
        "duplicate_candles": engine.metrics.get("duplicates"),
        "decisions_generated": counts.get("decisions"),
        "action_counts": {
            "BUY": counts.get("buy", 0),
            "SELL": counts.get("sell", 0),
            "WAIT": counts.get("wait", 0),
        },
        "open_paper_positions": len(engine.risk.open_positions),
        "closed_paper_positions": counts.get("closes", 0),
        "pending_outcomes": len(getattr(engine, "pending_outcomes", []) or []),
        "risk_rejections": engine.metrics.get("risk_rejections"),
        "sl_exits": engine.metrics.get("sl_exits"),
        "tp_exits": engine.metrics.get("tp_exits"),
        "horizon_exits": engine.metrics.get("horizon_exits"),
        "circuit_breaker": {
            "risk": engine.risk.snapshot().get("circuit_open"),
            "feed": engine.feed_safety.snapshot(),
        },
        "restart_recovery": {
            "state_path": str(engine.state.path),
            "cursor": engine.state.data.get("cursor"),
            "open_ids": sorted(engine.risk.open_positions),
        },
        "data_source": (poll_meta or {}).get("provenance"),
        "poll": poll_meta or {},
        "validated_profitable_policy": False,
        "streaming_ready": False,
    }
    write_json(REPORTS_DIR / "operational_health.json", report)
    md = [
        "# Phase 56 — Operational Health",
        "",
        f"**Generated:** {now['utc']} / {now['pkt']}",
        f"**Status:** `{report['agent_status']}` | **Policy:** `{report['policy_version']}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "> Paper activity only — not live trading.",
        "",
        f"- Candles recv/acc/rej/dup: `{report['candles_received']}` / `{report['candles_accepted']}` / `{report['candles_rejected']}` / `{report['duplicate_candles']}`",
        f"- Actions BUY/SELL/WAIT: `{report['action_counts']}`",
        f"- Open/Closed: `{report['open_paper_positions']}` / `{report['closed_paper_positions']}`",
        f"- Exits SL/TP/HORIZON: `{report['sl_exits']}` / `{report['tp_exits']}` / `{report['horizon_exits']}`",
        f"- Risk rejections: `{report['risk_rejections']}`",
        f"- Last candle: `{report['last_processed_candle']}`",
        f"- Streaming ready: `False` (historical replay verified only)",
    ]
    write_text(REPORTS_DIR / "operational_health.md", "\n".join(md) + "\n")
    return report
