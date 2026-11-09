"""Phase 18 Discord message formatting for signals, outcomes, and daily reports."""

from __future__ import annotations

from typing import Any

from phase18.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DAILY_FOOTER,
    DAILY_HEADER,
    EXPERIMENTAL_DISCLAIMER,
    FORBIDDEN_SIGNAL_PHRASES,
    HORIZON_LABELS,
    HORIZONS,
    OUTCOME_FAIL,
    OUTCOME_HEADER,
    OUTCOME_PASS,
    OUTCOME_PENDING,
    OUTCOME_TIMEOUT,
    SELECTED_HORIZON_DISPLAY,
    SHADOW_BUY_HEADER,
    SHADOW_SELL_HEADER,
    SHADOW_WAIT_HEADER,
    STRATEGY_ID,
    SYMBOL,
)
from phase18.horizons import (
    expected_outcome_check_pkt,
    format_pkt,
    format_pkt_clock,
    parse_utc,
    selected_horizon_info,
)


def _tp_sl_lines(decision: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    tp = decision.get("tp_level")
    sl = decision.get("sl_level")
    atr = decision.get("atr")
    if tp not in (None, ""):
        lines.append(f"TP Level: {tp}")
    if sl not in (None, ""):
        lines.append(f"SL Level: {sl}")
    if atr not in (None, ""):
        lines.append(f"ATR(14): {atr}")
    if not lines:
        lines.append("TP/SL: computed at outcome evaluation from ATR barriers")
    return lines


def build_signal_payload(
    decision: dict[str, Any],
    observation: dict[str, Any],
    *,
    pending_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    exp = str(decision.get("experimental_action", "WAIT")).upper()
    final = str(decision.get("final_action", "WAIT")).upper()
    if exp == "BUY":
        header = SHADOW_BUY_HEADER
    elif exp == "SELL":
        header = SHADOW_SELL_HEADER
    else:
        header = SHADOW_WAIT_HEADER

    sel = selected_horizon_info()
    close_utc = observation.get("bar_close_timestamp_utc") or decision.get("decision_timestamp_utc", "")
    lines = [f"**{header}**"]
    if exp in {"BUY", "SELL"}:
        lines.append(EXPERIMENTAL_DISCLAIMER)
        lines.extend(
            [
                "",
                f"{observation.get('symbol', SYMBOL)}",
                f"Action: {exp}",
                "",
                f"Selected Horizon: {sel['selected_horizon_display']}",
                "Expected Horizon: NOT ESTABLISHED",
                "Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.",
                "",
                "Expected Outcome Checks (PKT):",
            ]
        )
        for hid in HORIZONS:
            label = HORIZON_LABELS[hid]
            pkt = expected_outcome_check_pkt(close_utc, hid) if close_utc else "n/a"
            lines.append(f"  {label}: {pkt}")
        lines.append("")
        # Optional multi-horizon board — experimental action applies to all pending evals
        lines.append("Horizon board (decision action; selection not established):")
        for hid in HORIZONS:
            label = HORIZON_LABELS[hid]
            lines.append(f"  {label}: {exp}")
        lines.append("")
        lines.extend(_tp_sl_lines(decision))
        lines.append("")
        lines.append(f"Strategy: {STRATEGY_ID}")
        lines.append(f"Status: {CANDIDATE_STATUS}")
        lines.append("")
        lines.append(f"Production Action: {final}")
        lines.append(f"Champion: {CHAMPION_STATUS}")
    else:
        lines.extend(
            [
                f"symbol: {observation.get('symbol', SYMBOL)}",
                f"experimental_action: WAIT",
                f"Production Action: {final}",
                f"Champion: {CHAMPION_STATUS}",
                f"Strategy: {STRATEGY_ID} ({CANDIDATE_STATUS})",
            ]
        )

    lines.extend(
        [
            "",
            f"decision_id: {decision.get('decision_id', '')}",
            f"event_id: {decision.get('decision_id', '')}",
            f"candle_close_utc: {close_utc}",
            "Notification only. No broker order.",
        ]
    )
    content = "\n".join(lines)
    for phrase in FORBIDDEN_SIGNAL_PHRASES:
        if phrase.lower() in content.lower():
            raise ValueError(f"forbidden guarantee language in signal: {phrase}")
    if exp in {"BUY", "SELL"} and EXPERIMENTAL_DISCLAIMER not in content:
        content = EXPERIMENTAL_DISCLAIMER + "\n" + content
    return {"content": content}


def build_outcome_payload(outcome: dict[str, Any]) -> dict[str, str]:
    status = str(outcome.get("status", "")).upper()
    side = str(outcome.get("side", "")).upper()
    horizon = outcome.get("horizon_label") or HORIZON_LABELS.get(outcome.get("horizon_id", ""), "")
    signal_pkt = format_pkt(parse_utc(outcome["decision_timestamp_utc"])) if outcome.get("decision_timestamp_utc") else ""
    out_ts = outcome.get("outcome_timestamp_utc") or outcome.get("exit_timestamp_utc") or ""
    outcome_pkt = format_pkt(parse_utc(out_ts)) if out_ts else ""

    lines = [
        f"**{OUTCOME_HEADER}**",
        "",
        f"Event: {outcome.get('decision_id', '')}",
        f"Outcome Event: {outcome.get('outcome_event_id', '')}",
        f"Symbol: {outcome.get('symbol', SYMBOL)}",
        f"Side: {side}",
        "",
        f"Horizon: {horizon}",
        f"Outcome: {status}",
    ]
    if status in {OUTCOME_PASS, OUTCOME_FAIL}:
        try:
            r = float(outcome.get("realized_r", 0.0))
            sign = "+" if r >= 0 else ""
            lines.append(f"Realized R: {sign}{r:.2f}R")
        except (TypeError, ValueError):
            lines.append(f"Realized R: {outcome.get('realized_r', '')}")
    elif status == OUTCOME_TIMEOUT:
        lines.append("No TP/SL barrier completed within the selected horizon.")
        try:
            r = float(outcome.get("realized_r", 0.0))
            sign = "+" if r >= 0 else ""
            lines.append(f"Mark-to-horizon R: {sign}{r:.2f}R")
        except (TypeError, ValueError):
            pass
    elif status == OUTCOME_PENDING:
        lines.append("Still pending candle availability.")

    lines.extend(
        [
            "",
            f"Signal Time: {format_pkt_clock(parse_utc(outcome['decision_timestamp_utc'])) if outcome.get('decision_timestamp_utc') else ''}",
            f"Outcome Time: {format_pkt_clock(parse_utc(out_ts)) if out_ts else ''}",
            f"Signal Day PKT: {signal_pkt}",
            f"Outcome Day PKT: {outcome_pkt}",
            "",
            f"Status: {CANDIDATE_STATUS}",
            "NOT A LIVE TRADING RESULT",
        ]
    )
    content = "\n".join(lines)
    for phrase in FORBIDDEN_SIGNAL_PHRASES:
        if phrase.lower() in content.lower():
            raise ValueError(f"forbidden guarantee language in outcome: {phrase}")
    return {"content": content}


def build_daily_report_payload(report: dict[str, Any]) -> dict[str, str]:
    signals = report.get("signals", {})
    lines = [
        f"**{DAILY_HEADER}**",
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
        label = HORIZON_LABELS[hid]
        block = by_h.get(hid, {})
        lines.extend(
            [
                label,
                f"PASS: {block.get(OUTCOME_PASS, 0)}",
                f"FAIL: {block.get(OUTCOME_FAIL, 0)}",
                f"TIMEOUT: {block.get(OUTCOME_TIMEOUT, 0)}",
                f"PENDING: {block.get(OUTCOME_PENDING, 0)}",
                "",
            ]
        )
    perf = report.get("performance", {})
    lines.extend(
        [
            f"Resolved PASS/FAIL Rate:",
            f"{perf.get('pass_fail_rate_pct', 0.0):.1f}%",
            "",
            "Net R:",
            f"{perf.get('net_r_display', '0.00R')}",
            "",
            f"BUY Net R: {perf.get('buy_net_r_display', '0.00R')}",
            f"SELL Net R: {perf.get('sell_net_r_display', '0.00R')}",
            "",
            "Pending",
            f"From today: {report.get('pending_today', 0)}",
            f"Carried from prior days: {report.get('pending_prior', 0)}",
            "",
            "Status:",
            f"Champion: {CHAMPION_STATUS}",
            f"H13_C: {CANDIDATE_STATUS}",
            "Production: WAIT",
            "Broker Orders: 0",
            "",
            DAILY_FOOTER,
        ]
    )
    return {"content": "\n".join(lines)}


def assert_no_guarantee_language(text: str) -> None:
    lower = text.lower()
    for phrase in FORBIDDEN_SIGNAL_PHRASES:
        if phrase.lower() in lower:
            raise AssertionError(f"forbidden phrase present: {phrase}")
