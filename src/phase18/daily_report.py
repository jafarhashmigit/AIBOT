"""PKT calendar-day aggregation for Discord daily shadow reports."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from phase18.constants import (
    HORIZON_LABELS,
    HORIZONS,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_PENDING,
    OUTCOME_TIMEOUT,
    PKT_TZ,
)
from phase18.horizons import pkt_calendar_date, parse_utc
from phase18.messages import build_daily_report_payload

PKT = ZoneInfo(PKT_TZ)


def daily_report_id(date_pkt: str) -> str:
    return f"daily_shadow_{date_pkt}"


def _fmt_r(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}R"


def aggregate_daily(
    *,
    decisions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    date_pkt: str,
) -> dict[str, Any]:
    """Summarize signals by decision PKT date; outcomes counted under that signal day."""
    day_decisions = [
        d
        for d in decisions
        if d.get("decision_timestamp_utc")
        and pkt_calendar_date(parse_utc(d["decision_timestamp_utc"])) == date_pkt
    ]
    signal_counts = {"BUY": 0, "SELL": 0, "WAIT": 0, "total": 0}
    for d in day_decisions:
        action = str(d.get("experimental_action", "WAIT")).upper()
        if action not in {"BUY", "SELL", "WAIT"}:
            action = "WAIT"
        signal_counts[action] += 1
        signal_counts["total"] += 1

    day_decision_ids = {d["decision_id"] for d in day_decisions}
    day_outcomes = [o for o in outcomes if o.get("decision_id") in day_decision_ids]

    by_horizon: dict[str, dict[str, int]] = {
        hid: {OUTCOME_PASS: 0, OUTCOME_FAIL: 0, OUTCOME_TIMEOUT: 0, OUTCOME_PENDING: 0}
        for hid in HORIZONS
    }
    resolved_pass_fail: list[dict[str, Any]] = []
    buy_r = 0.0
    sell_r = 0.0
    net_r = 0.0
    per_horizon_net: dict[str, float] = {hid: 0.0 for hid in HORIZONS}

    for o in day_outcomes:
        hid = o.get("horizon_id", "")
        if hid not in by_horizon:
            continue
        status = str(o.get("status", OUTCOME_PENDING)).upper()
        if status not in by_horizon[hid]:
            status = OUTCOME_PENDING
        by_horizon[hid][status] += 1
        if status in {OUTCOME_PASS, OUTCOME_FAIL}:
            resolved_pass_fail.append(o)
            try:
                r = float(o.get("realized_r") or 0.0)
            except (TypeError, ValueError):
                r = 0.0
            net_r += r
            per_horizon_net[hid] += r
            if str(o.get("side", "")).upper() == "BUY":
                buy_r += r
            elif str(o.get("side", "")).upper() == "SELL":
                sell_r += r
        elif status == OUTCOME_TIMEOUT:
            # TIMEOUT is experience but excluded from PASS/FAIL rate; still track R separately
            try:
                r = float(o.get("realized_r") or 0.0)
            except (TypeError, ValueError):
                r = 0.0
            per_horizon_net[hid] += r
            net_r += r

    pf = len(resolved_pass_fail)
    passes = sum(1 for o in resolved_pass_fail if str(o.get("status")).upper() == OUTCOME_PASS)
    rate = (100.0 * passes / pf) if pf else 0.0

    pending_today = sum(1 for o in day_outcomes if str(o.get("status")).upper() == OUTCOME_PENDING)
    pending_prior = sum(
        1
        for o in outcomes
        if str(o.get("status")).upper() == OUTCOME_PENDING
        and o.get("decision_id") not in day_decision_ids
    )

    report = {
        "report_id": daily_report_id(date_pkt),
        "date_pkt": date_pkt,
        "signals": signal_counts,
        "outcomes_by_horizon": by_horizon,
        "performance": {
            "pass_fail_rate_pct": rate,
            "resolved_pass_fail_n": pf,
            "pass_n": passes,
            "fail_n": pf - passes,
            "net_r": net_r,
            "net_r_display": _fmt_r(net_r),
            "buy_net_r": buy_r,
            "buy_net_r_display": _fmt_r(buy_r),
            "sell_net_r": sell_r,
            "sell_net_r_display": _fmt_r(sell_r),
            "per_horizon_net_r": {hid: per_horizon_net[hid] for hid in HORIZONS},
            "per_horizon_labels": {hid: HORIZON_LABELS[hid] for hid in HORIZONS},
        },
        "pending_today": pending_today,
        "pending_prior": pending_prior,
        "note": "PENDING excluded from PASS/FAIL rate; WAIT excluded from trade stats",
    }
    return report


def payload_sha256(payload: dict[str, str]) -> str:
    text = payload.get("content", "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_daily_discord_bundle(
    *,
    decisions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    date_pkt: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    report = aggregate_daily(decisions=decisions, outcomes=outcomes, date_pkt=date_pkt)
    payload = build_daily_report_payload(report)
    return {
        "report": report,
        "payload": payload,
        "record": {
            "report_id": report["report_id"],
            "date_pkt": date_pkt,
            "generated_at_utc": generated_at_utc,
            "discord_status": "PENDING_SEND",
            "payload_sha256": payload_sha256(payload),
            "note": "idempotent daily PKT report",
        },
    }


def current_pkt_date(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(tz=PKT)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=PKT)
    else:
        now = now.astimezone(PKT)
    return now.strftime("%Y-%m-%d")
