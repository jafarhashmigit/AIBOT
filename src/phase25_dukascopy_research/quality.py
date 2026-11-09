"""Data quality report for Dukascopy downloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase25.constants import PARITY_DAYS, RAW_DIR, RESEARCH_CUTOFF_UTC, XAUUSD_PRICE_SCALE


def build_data_quality_report() -> dict[str, Any]:
    days = {}
    total_ticks = 0
    total_failed = 0
    total_empty = 0
    total_ok = 0
    sha_samples = []
    for day in PARITY_DAYS:
        man_path = RAW_DIR / day / "manifest.json"
        if not man_path.is_file():
            days[day] = {"present": False}
            continue
        man = json.loads(man_path.read_text(encoding="utf-8"))
        ok = sum(1 for x in man["files"] if x.get("ok") and not x.get("empty"))
        empty = sum(1 for x in man["files"] if x.get("ok") and x.get("empty"))
        failed = sum(1 for x in man["files"] if not x.get("ok"))
        total_ticks += man.get("tick_count", 0)
        total_ok += ok
        total_empty += empty
        total_failed += failed
        for x in man["files"]:
            if x.get("sha256") and x.get("bytes", 0) > 0:
                sha_samples.append({"day": day, "hour": x["hour"], "sha256": x["sha256"], "bytes": x["bytes"]})
        days[day] = {
            "present": True,
            "tick_count": man.get("tick_count", 0),
            "ok_hours": ok,
            "empty_hours": empty,
            "failed_hours": failed,
            "errors": man.get("errors", [])[:5],
            "after_cutoff": day > RESEARCH_CUTOFF_UTC[:10],
        }
    return {
        "symbol": "XAUUSD",
        "timeframe_built": "M5_from_ticks",
        "bid_ask_available": True,
        "utc_convention": "tick timestamps reconstructed as UTC from hour file + ms offset",
        "url_month_indexing": "zero_based",
        "price_scale": XAUUSD_PRICE_SCALE,
        "missing_data_behavior": (
            "HTTP 200 with empty body for hours without quotes (weekend/daily break); "
            "not treated as failure; M5 bars not fabricated for gaps."
        ),
        "download_integrity": {
            "sha256_per_nonempty_file": True,
            "sample_hashes": sha_samples[:10],
            "lzma_decode_required": True,
            "record_size_bytes": 20,
        },
        "days": days,
        "totals": {
            "ticks": total_ticks,
            "ok_hours": total_ok,
            "empty_hours": total_empty,
            "failed_hours": total_failed,
        },
        "fabricated_candles": False,
        "separated_from_mt5_path": str(RAW_DIR),
        "licensing_note": (
            "Public historical feed used for research parity only. Website/JForex terms emphasize "
            "personal non-commercial use and restrict redistribution/database/scraping — cloud commercial "
            "clearance is not established in Phase 25."
        ),
    }
