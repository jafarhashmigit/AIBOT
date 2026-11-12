"""UTC reconstruction and DST transition validation (stdlib; no tzdata)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from phase34.constants import DST_2026, RESEARCH_CUTOFF_UTC
from phase34.progress import write_json

UTC = timezone.utc


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def us_dst(ts: datetime) -> bool:
    return _parse(DST_2026["us_start_utc"]) <= ts < _parse(DST_2026["us_end_utc"])


def eu_dst(ts: datetime) -> bool:
    return _parse(DST_2026["eu_start_utc"]) <= ts < _parse(DST_2026["eu_end_utc"])


def validate_utc_dst(ticks: list[dict[str, Any]], acquisition_days: list[str]) -> dict[str, Any]:
    """Validate tick UTC semantics across winter/summer and DST-adjacent days."""
    if not ticks:
        report = {"pass": False, "reason": "no_ticks", "unqualified_periods": acquisition_days}
        write_json("utc_dst_validation.json", report)
        return report

    epochs = [int(t["epoch_ms"]) for t in ticks]
    ordered = all(epochs[i] >= epochs[i - 1] for i in range(1, len(epochs)))
    after = sum(1 for t in ticks if t["timestamp_utc"] > RESEARCH_CUTOFF_UTC)

    # Hour-boundary consistency: ms offset must place tick within its declared hour archive
    # (checked implicitly by decode). Probe DST-adjacent days.
    dst_days = {
        "us_pre": "2026-03-06",
        "us_post": "2026-03-09",
        "eu_pre": "2026-03-27",
        "eu_post": "2026-03-30",
        "winter_sample": "2026-02-17",
        "summer_sample": "2026-07-08",
    }
    probes = []
    unqualified = []
    for label, day in dst_days.items():
        day_ticks = [t for t in ticks if t["timestamp_utc"].startswith(day)]
        noon = _parse(f"{day} 12:00:00")
        us = us_dst(noon)
        eu = eu_dst(noon)
        us_off = -4 if us else -5
        eu_off = 3 if eu else 2
        local_us = noon + timedelta(hours=us_off)
        local_eu = noon + timedelta(hours=eu_off)
        present = len(day_ticks) > 0
        if day in acquisition_days and not present:
            unqualified.append({"day": day, "reason": "selected_but_no_ticks"})
        probes.append(
            {
                "label": label,
                "day": day,
                "ticks_present": present,
                "n_ticks": len(day_ticks),
                "us_dst": us,
                "eu_dst": eu,
                "america_new_york_offset_hours": us_off,
                "europe_athens_offset_hours": eu_off,
                "utc_noon_to_us_local": local_us.strftime("%Y-%m-%d %H:%M:%S"),
                "utc_noon_to_eu_local": local_eu.strftime("%Y-%m-%d %H:%M:%S"),
                "evidence_class": "INFERRED_CIVIL_RULES_2026" if present else "UNVERIFIED_NO_SAMPLE",
            }
        )

    # Day/hour boundary: first tick of each hour should have epoch >= hour start
    boundary_issues = []
    by_hour: dict[str, list[dict[str, Any]]] = {}
    for t in ticks:
        key = t["timestamp_utc"][:13]  # YYYY-MM-DD HH
        by_hour.setdefault(key, []).append(t)
    for key, group in list(by_hour.items())[:500]:
        hour_start = _parse(key + ":00:00")
        first = min(int(x["epoch_ms"]) for x in group)
        if first < int(hour_start.timestamp() * 1000):
            boundary_issues.append(key)

    # Ambiguous local times: US spring-forward skips 02:00–02:59 local — we store UTC only,
    # so no ambiguous local storage. Fall-back would create ambiguous local hours; outside window.
    report = {
        "internal_timestamps": "UTC",
        "bi5_convention": (
            "Hour archive HHh_ticks.bi5; tick ms is offset from that hour start; "
            "reconstructed as UTC. No TZ tag in bi5 payload."
        ),
        "dst_rules_source": "US/EU civil DST 2026 published rules (hardcoded; no tzdata package)",
        "dst_rules": DST_2026,
        "monotonic_ok": ordered,
        "after_cutoff": after,
        "probes": probes,
        "hour_boundary_issues": boundary_issues[:20],
        "unqualified_periods": unqualified,
        "ambiguous_local_time_handling": (
            "All stored timestamps are UTC; local DST labels are derived for session analysis only. "
            "No silent offset guessing for bi5 reconstruction."
        ),
        "pass": ordered and after == 0 and len(boundary_issues) == 0,
        "confidence": "HIGH_FOR_UTC_RECONSTRUCTION" if ordered else "LOW",
    }
    write_json("utc_dst_validation.json", report)
    return report
