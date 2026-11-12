"""Execution latency & quote freshness — measured only when timestamps exist."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from phase61.constants import canonical_json_sha256


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


def ms_between(a: str | None, b: str | None) -> float | None:
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    return (db - da).total_seconds() * 1000.0


def analyze_latency(records: list[dict[str, Any]]) -> dict[str, Any]:
    decision_to_submit: list[float] = []
    submit_to_fill: list[float] = []
    quote_age_decision: list[float] = []
    unavailable = 0
    measured = 0
    simulated = 0

    for r in records:
        cat = r.get("evidence_category")
        d2s = ms_between(r.get("decision_timestamp_utc"), r.get("simulated_submission_timestamp_utc"))
        if d2s is not None:
            decision_to_submit.append(d2s)
            if cat in ("EXNESS_DEMO_EXECUTION", "EXNESS_LIVE_EXECUTION"):
                measured += 1
            else:
                simulated += 1
        else:
            unavailable += 1

        s2f = ms_between(
            r.get("simulated_submission_timestamp_utc") or r.get("decision_timestamp_utc"),
            r.get("actual_broker_fill_timestamp_utc"),
        )
        if s2f is not None:
            submit_to_fill.append(s2f)
            measured += 1

        qage = ms_between(r.get("quote_timestamp_utc"), r.get("decision_timestamp_utc"))
        if qage is not None:
            quote_age_decision.append(qage)

        # Never estimate from candle timestamps alone — skip if only bar ts present without quote ts
        if r.get("quote_timestamp_utc") is None and r.get("m5_bar_timestamp_only"):
            unavailable += 1

    def _summ(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0, "mean_ms": None, "max_ms": None}
        return {"n": len(xs), "mean_ms": sum(xs) / len(xs), "max_ms": max(xs)}

    out = {
        "decision_to_submission_ms": _summ(decision_to_submit),
        "submission_to_fill_ms": _summ(submit_to_fill),
        "quote_age_at_decision_ms": _summ(quote_age_decision),
        "measured_latency_observations": measured,
        "simulated_latency_observations": simulated,
        "unavailable_latency_observations": unavailable,
        "stale_crossed_rejected_requoted": {
            "stale": "UNKNOWN_WITHOUT_THRESHOLD_AND_TIMESTAMPS",
            "crossed": "UNKNOWN",
            "rejected_orders": "UNKNOWN_NO_BROKER_RECORDS",
            "requotes": "UNKNOWN_NO_BROKER_RECORDS",
        },
        "never_manufacture_timestamps": True,
        "never_estimate_from_candle_only": True,
        "broker_latency_status": "UNKNOWN",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
