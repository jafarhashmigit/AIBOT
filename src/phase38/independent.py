"""Independent reload / recompute path — does not trust in-memory validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase38.constants import MANIFESTS_DIR, RAW_M5_DIR, RAW_TICKS_DIR
from phase38.diagnostics import spread_diagnostics
from phase38.storage import load_jsonl, sha256_file
from phase38.validation import validate_m5_bars, validate_ticks


def verify_all_manifests() -> dict[str, Any]:
    results = []
    ok = True
    if not MANIFESTS_DIR.exists():
        return {"ok": False, "reason": "no_manifests_dir", "results": []}
    for man in sorted(MANIFESTS_DIR.glob("*.manifest.json")):
        meta = json.loads(man.read_text(encoding="utf-8"))
        path = Path(meta["file_path"])
        row: dict[str, Any] = {"manifest": man.name, "file": str(path)}
        if not path.is_file():
            row["ok"] = False
            row["error"] = "missing_file"
            ok = False
        else:
            digest = sha256_file(path)
            row["sha256_recomputed"] = digest
            row["sha256_manifest"] = meta.get("sha256")
            row["ok"] = digest == meta.get("sha256")
            if not row["ok"]:
                ok = False
            # reload + revalidate
            rows = load_jsonl(path)
            row["reload_n"] = len(rows)
            row["manifest_n"] = meta.get("record_count")
            if len(rows) != int(meta.get("record_count") or -1):
                row["ok"] = False
                ok = False
                row["count_mismatch"] = True
            if meta.get("kind") == "m5":
                # map to validation shape
                bars = [
                    {
                        "time_epoch": r.get("time_epoch"),
                        "timestamp_utc": r.get("timestamp_utc"),
                        "time_utc": r.get("timestamp_utc"),
                        "open": r.get("open"),
                        "high": r.get("high"),
                        "low": r.get("low"),
                        "close": r.get("close"),
                        "tick_volume": r.get("tick_volume"),
                        "spread": r.get("spread"),
                        "real_volume": r.get("real_volume"),
                    }
                    for r in rows
                ]
                v = validate_m5_bars(bars)
                row["recomputed_validation_pass"] = v.get("pass")
                row["duplicate_timestamps"] = v.get("duplicate_timestamps")
                row["out_of_order"] = v.get("out_of_order")
            else:
                ticks = [
                    {
                        "bid": r.get("bid"),
                        "ask": r.get("ask"),
                        "timestamp_msc": r.get("timestamp_msc"),
                        "time_msc": r.get("timestamp_msc"),
                        "timestamp_utc": r.get("timestamp_utc"),
                    }
                    for r in rows
                ]
                v = validate_ticks(ticks)
                row["recomputed_validation_pass"] = v.get("pass")
                row["duplicate_timestamps_msc"] = v.get("duplicate_timestamps_msc")
                row["out_of_order"] = v.get("out_of_order")
                # spread recompute sample
                full = load_jsonl(path)
                row["spread_recompute"] = spread_diagnostics(full).get("overall")
        results.append(row)
    return {"ok": ok, "n_manifests": len(results), "results": results}


def inventory_raw_counts() -> dict[str, Any]:
    m5_files = sorted(RAW_M5_DIR.glob("*.jsonl")) if RAW_M5_DIR.exists() else []
    tick_files = sorted(RAW_TICKS_DIR.glob("*.jsonl")) if RAW_TICKS_DIR.exists() else []
    m5_n = 0
    tick_n = 0
    firsts, lasts = [], []
    for p in m5_files:
        rows = load_jsonl(p)
        m5_n += len(rows)
        if rows:
            firsts.append(rows[0].get("timestamp_utc"))
            lasts.append(rows[-1].get("timestamp_utc"))
    for p in tick_files:
        rows = load_jsonl(p)
        tick_n += len(rows)
        if rows:
            firsts.append(rows[0].get("timestamp_utc"))
            lasts.append(rows[-1].get("timestamp_utc"))
    firsts = [x for x in firsts if x]
    lasts = [x for x in lasts if x]
    return {
        "m5_files": [p.name for p in m5_files],
        "tick_files": [p.name for p in tick_files],
        "m5_record_count": m5_n,
        "tick_record_count": tick_n,
        "first_verified_timestamp": min(firsts) if firsts else None,
        "last_verified_timestamp": max(lasts) if lasts else None,
    }
