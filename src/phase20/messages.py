"""Phase 20 Discord formatting for real shadow BUY/SELL only."""

from __future__ import annotations

from typing import Any

from phase18.constants import FORBIDDEN_SIGNAL_PHRASES, HORIZON_LABELS, HORIZONS
from phase18.horizons import expected_outcome_check_pkt, format_pkt, format_pkt_clock, parse_utc
from phase20.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    OUTCOME_HEADER,
    SELECTED_HORIZON_DISPLAY,
    SHADOW_BUY_HEADER,
    SHADOW_DISCLAIMER,
    SHADOW_SELL_HEADER,
    STRATEGY_ID,
    SYMBOL,
)


def build_shadow_signal_payload(decision: dict[str, Any], observation: dict[str, Any]) -> dict[str, str]:
    exp = str(decision.get("experimental_action", "WAIT")).upper()
    if exp not in {"BUY", "SELL"}:
        raise ValueError("Phase 20 Discord signals are BUY/SELL only")
    final = str(decision.get("final_action", "WAIT")).upper()
    header = SHADOW_BUY_HEADER if exp == "BUY" else SHADOW_SELL_HEADER
    close_utc = observation.get("bar_close_timestamp_utc") or decision.get("decision_timestamp_utc", "")
    close_pkt = format_pkt(parse_utc(close_utc)) if close_utc else ""
    entry_ref = observation.get("close", decision.get("entry_reference", ""))

    lines = [
        f"**{header}**",
        SHADOW_DISCLAIMER,
        "",
        f"Symbol: {observation.get('symbol', SYMBOL)}",
        f"Side: {exp}",
        f"Timestamp UTC: {close_utc}",
        f"Timestamp PKT: {close_pkt}",
        f"Entry/reference price: {entry_ref}",
        "",
        f"Selected Horizon: {SELECTED_HORIZON_DISPLAY}",
        "Expected Horizon: NOT ESTABLISHED",
        "Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.",
        "",
        "Expected Outcome Checks (PKT):",
    ]
    for hid in HORIZONS:
        lines.append(f"  {HORIZON_LABELS[hid]}: {expected_outcome_check_pkt(close_utc, hid) if close_utc else 'n/a'}")
    lines.extend(
        [
            "",
            f"Strategy: {STRATEGY_ID}",
            f"Status: {CANDIDATE_STATUS}",
            f"Production Action: {final}",
            f"Champion: {CHAMPION_STATUS}",
            "",
            f"decision_id: {decision.get('decision_id', '')}",
            "Shadow research only. No broker order.",
        ]
    )
    content = "\n".join(lines)
    for phrase in FORBIDDEN_SIGNAL_PHRASES:
        if phrase.lower() in content.lower():
            raise ValueError(f"forbidden guarantee language: {phrase}")
    if SHADOW_DISCLAIMER not in content:
        raise ValueError("missing shadow disclaimer")
    return {"content": content}


def build_shadow_outcome_payload(outcome: dict[str, Any]) -> dict[str, str]:
    status = str(outcome.get("status", "")).upper()
    horizon = outcome.get("horizon_label") or HORIZON_LABELS.get(str(outcome.get("horizon_id", "")), "")
    lines = [
        f"**{OUTCOME_HEADER}**",
        SHADOW_DISCLAIMER,
        "",
        f"Event: {outcome.get('decision_id', '')}",
        f"Outcome Event: {outcome.get('outcome_event_id', '')}",
        f"Symbol: {outcome.get('symbol', SYMBOL)}",
        f"Side: {outcome.get('side', '')}",
        f"Horizon: {horizon}",
        f"Outcome: {status}",
    ]
    if status in {"PASS", "FAIL"}:
        try:
            r = float(outcome.get("realized_r", 0.0))
            sign = "+" if r >= 0 else ""
            lines.append(f"Realized R: {sign}{r:.2f}R")
        except (TypeError, ValueError):
            lines.append(f"Realized R: {outcome.get('realized_r', '')}")
    elif status == "TIMEOUT":
        lines.append("No TP/SL barrier completed within the selected horizon.")
    if outcome.get("decision_timestamp_utc"):
        lines.append(f"Signal Time: {format_pkt_clock(parse_utc(outcome['decision_timestamp_utc']))}")
    out_ts = outcome.get("outcome_timestamp_utc") or outcome.get("exit_timestamp_utc") or ""
    if out_ts:
        lines.append(f"Outcome Time: {format_pkt_clock(parse_utc(out_ts))}")
    lines.extend(["", f"Status: {CANDIDATE_STATUS}", "Shadow observation only — NOT validated trading performance."])
    return {"content": "\n".join(lines)}
