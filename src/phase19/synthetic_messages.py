"""Synthetic Discord formatters — explicitly labeled, never real trading signals."""

from __future__ import annotations

from typing import Any

from phase18.constants import HORIZON_LABELS, HORIZONS
from phase18.horizons import expected_outcome_check_pkt, expected_outcome_check_utc, format_pkt_clock, parse_utc
from phase19.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FORBIDDEN_PHRASES,
    STRATEGY_ID,
    SYMBOL,
    SYNTHETIC_DAILY_BANNER,
    SYNTHETIC_NAMESPACE,
    SYNTHETIC_NOT_REAL,
    SYNTHETIC_OUTCOME_BANNER,
    SYNTHETIC_SIGNAL_BANNER,
)


def assert_no_guarantee_language(text: str) -> None:
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in lower:
            raise AssertionError(f"forbidden guarantee language: {phrase}")


def build_synthetic_signal_payload(
    decision: dict[str, Any],
    observation: dict[str, Any],
    *,
    expected_horizon_id: str | None = None,
) -> dict[str, str]:
    """Format a synthetic BUY/SELL signal with explicit Expected Horizon for validation."""
    exp = str(decision.get("experimental_action", "WAIT")).upper()
    final = str(decision.get("final_action", "WAIT")).upper()
    close_utc = observation.get("bar_close_timestamp_utc") or decision.get("decision_timestamp_utc", "")

    lines = [
        f"**{SYNTHETIC_SIGNAL_BANNER}**",
        SYNTHETIC_NOT_REAL,
        f"Namespace: {SYNTHETIC_NAMESPACE}",
        "",
        f"{observation.get('symbol', SYMBOL)}",
        f"Action: {exp}",
        f"Strategy: {STRATEGY_ID}",
        f"Status: {CANDIDATE_STATUS}",
        f"Production Action: {final}",
        f"Champion: {CHAMPION_STATUS}",
        "",
    ]

    if expected_horizon_id:
        label = HORIZON_LABELS[expected_horizon_id]
        lines.append(f"Expected Horizon: {label}")
        if close_utc:
            lines.append(f"Expected Outcome Check: {expected_outcome_check_pkt(close_utc, expected_horizon_id)}")
        lines.append("Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.")
    else:
        lines.append("Selected Horizon: NOT ESTABLISHED")
        lines.append("Expected Horizon: NOT ESTABLISHED")
        lines.append("Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.")
        lines.append("Expected Outcome Checks (PKT):")
        for hid in HORIZONS:
            pkt = expected_outcome_check_pkt(close_utc, hid) if close_utc else "n/a"
            lines.append(f"  {HORIZON_LABELS[hid]}: {pkt}")

    lines.extend(
        [
            "",
            f"decision_id: {decision.get('decision_id', '')}",
            f"event_id: {decision.get('decision_id', '')}",
            f"candle_close_utc: {close_utc}",
            "Synthetic validation only. No broker order.",
        ]
    )
    content = "\n".join(lines)
    assert_no_guarantee_language(content)
    if SYNTHETIC_SIGNAL_BANNER not in content or SYNTHETIC_NOT_REAL not in content:
        raise ValueError("synthetic labels missing")
    return {"content": content}


def build_synthetic_outcome_payload(outcome: dict[str, Any]) -> dict[str, str]:
    status = str(outcome.get("status", "")).upper()
    horizon = outcome.get("horizon_label") or HORIZON_LABELS.get(str(outcome.get("horizon_id", "")), "")
    lines = [
        f"**{SYNTHETIC_OUTCOME_BANNER}**",
        SYNTHETIC_NOT_REAL,
        f"Namespace: {SYNTHETIC_NAMESPACE}",
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
    lines.extend(["", f"Status: {CANDIDATE_STATUS}", "NOT A LIVE TRADING RESULT"])
    content = "\n".join(lines)
    assert_no_guarantee_language(content)
    return {"content": content}


def build_synthetic_daily_payload(report: dict[str, Any]) -> dict[str, str]:
    signals = report.get("signals", {})
    lines = [
        f"**{SYNTHETIC_DAILY_BANNER}**",
        SYNTHETIC_NOT_REAL,
        f"Namespace: {SYNTHETIC_NAMESPACE}",
        f"Date: {report.get('date_pkt')} PKT",
        "",
        "Signals",
        f"BUY: {signals.get('BUY', 0)}",
        f"SELL: {signals.get('SELL', 0)}",
        f"WAIT: {signals.get('WAIT', 0)}",
        f"Total: {signals.get('total', 0)}",
        "",
    ]
    by_h = report.get("outcomes_by_horizon", {})
    for hid in HORIZONS:
        block = by_h.get(hid, {})
        lines.extend(
            [
                HORIZON_LABELS[hid],
                f"PASS: {block.get('PASS', 0)}",
                f"FAIL: {block.get('FAIL', 0)}",
                f"TIMEOUT: {block.get('TIMEOUT', 0)}",
                f"PENDING: {block.get('PENDING', 0)}",
                "",
            ]
        )
    perf = report.get("performance", {})
    lines.extend(
        [
            "Resolved PASS/FAIL Rate:",
            f"{perf.get('pass_fail_rate_pct', 0.0):.1f}%",
            "",
            "Net R:",
            f"{perf.get('net_r_display', '0.00R')}",
            "",
            "⚠️ Synthetic validation only — NOT LIVE TRADING",
            "Do not mix into production daily report.",
        ]
    )
    return {"content": "\n".join(lines)}


def expected_check_utc_for(close_utc: str, horizon_id: str) -> str:
    return expected_outcome_check_utc(close_utc, horizon_id)
