"""UTC / DST / ordering validation for Dukascopy sample timestamps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from phase33.constants import RESEARCH_CUTOFF_UTC
from phase33.progress import write_json

UTC = timezone.utc

# Fixed 2026 civil DST boundaries (no tzdata / zoneinfo dependency; install forbidden).
# US: second Sunday of March 2026-03-08 07:00 UTC → EDT; ends 2026-11-01 06:00 UTC.
# EU: last Sunday of March 2026-03-29 01:00 UTC → summer; ends 2026-10-25 01:00 UTC.
_US_DST_START_UTC = datetime(2026, 3, 8, 7, 0, 0, tzinfo=UTC)
_US_DST_END_UTC = datetime(2026, 11, 1, 6, 0, 0, tzinfo=UTC)
_EU_DST_START_UTC = datetime(2026, 3, 29, 1, 0, 0, tzinfo=UTC)
_EU_DST_END_UTC = datetime(2026, 10, 25, 1, 0, 0, tzinfo=UTC)


def _us_dst(noon_utc: datetime) -> bool:
    return _US_DST_START_UTC <= noon_utc < _US_DST_END_UTC


def _eu_dst(noon_utc: datetime) -> bool:
    return _EU_DST_START_UTC <= noon_utc < _EU_DST_END_UTC


def validate_timestamps(ticks: list[dict[str, Any]], candles: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(ticks)
    if n == 0:
        report = {"pass": False, "reason": "no_ticks"}
        write_json("timestamp_validation.json", report)
        return report

    epochs = [int(t["epoch_ms"]) for t in ticks]
    ordered = all(epochs[i] >= epochs[i - 1] for i in range(1, n))
    after_cutoff = sum(1 for t in ticks if t["timestamp_utc"] > RESEARCH_CUTOFF_UTC)

    dst_checks = []
    probe_days = sorted({t["timestamp_utc"][:10] for t in ticks})
    for day in probe_days:
        noon = datetime.strptime(f"{day} 12:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        us_off = timedelta(hours=-4 if _us_dst(noon) else -5)
        eu_off = timedelta(hours=3 if _eu_dst(noon) else 2)
        us_local = noon + us_off
        eu_local = noon + eu_off
        dst_checks.append(
            {
                "day": day,
                "utc_noon": noon.strftime("%Y-%m-%d %H:%M:%S+0000"),
                "america_new_york": us_local.strftime("%Y-%m-%d %H:%M:%S")
                + ("-0400" if _us_dst(noon) else "-0500"),
                "europe_athens": eu_local.strftime("%Y-%m-%d %H:%M:%S")
                + ("+0300" if _eu_dst(noon) else "+0200"),
                "us_dst": _us_dst(noon),
                "eu_dst": _eu_dst(noon),
                "dst_method": "fixed_2026_civil_boundaries_no_tzdata",
            }
        )

    # M5 candle boundaries must be multiples of 5 minutes with second==0
    bad_boundaries = []
    for c in candles:
        dt = datetime.strptime(c["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
        if dt.minute % 5 != 0 or dt.second != 0:
            bad_boundaries.append(c["timestamp_utc"])

    report = {
        "n_ticks": n,
        "strictly_nondecreasing_epoch_ms": ordered,
        "after_cutoff_count": after_cutoff,
        "assumed_timezone": "UTC (reconstructed from hour archive + ms offset)",
        "timezone_evidence_class": "INFERRED_PENDING_MT5_PARITY",
        "dst_probes": dst_checks,
        "m5_boundary_violations": bad_boundaries[:20],
        "m5_boundaries_ok": len(bad_boundaries) == 0,
        "pass": ordered and after_cutoff == 0 and len(bad_boundaries) == 0,
        "notes": [
            "bi5 does not embed an explicit TZ tag; UTC is the research convention.",
            "DST affects local session labeling, not the UTC tick clock itself.",
            "DST probes use fixed 2026 civil boundaries (stdlib only; no tzdata package).",
        ],
    }
    write_json("timestamp_validation.json", report)
    return report
