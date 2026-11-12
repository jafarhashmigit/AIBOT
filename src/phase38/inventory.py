"""Phase37 artifact inventory (read-only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from phase38.constants import PHASE37_DATA, PHASE37_REPORTS
from phase38.progress import write_json


def _hash_file(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    return {
        "path": path.as_posix(),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _schema_sample(path: Path) -> list[str] | None:
    if path.suffix != ".jsonl" or not path.is_file() or path.stat().st_size == 0:
        return None
    line = path.read_text(encoding="utf-8").splitlines()[0]
    return sorted(json.loads(line).keys())


def build_phase37_inventory() -> dict[str, Any]:
    data_files = []
    if PHASE37_DATA.exists():
        for p in sorted(PHASE37_DATA.rglob("*")):
            if p.is_file():
                row = _hash_file(p)
                schema = _schema_sample(p)
                if schema:
                    row["schema_keys"] = schema
                data_files.append(row)
    report_files = []
    if PHASE37_REPORTS.exists():
        for p in sorted(PHASE37_REPORTS.glob("*")):
            if p.is_file():
                report_files.append(_hash_file(p))

    verdict = {}
    fv = PHASE37_REPORTS / "final_verdict.json"
    if fv.is_file():
        verdict = json.loads(fv.read_text(encoding="utf-8"))

    range_probe = {}
    rp = PHASE37_REPORTS / "range_probe.json"
    if rp.is_file():
        range_probe = json.loads(rp.read_text(encoding="utf-8"))

    inventory = {
        "phase37_verdict": verdict.get("final_verdict"),
        "earliest_confirmed_m5": verdict.get("earliest_confirmed_m5") or range_probe.get("EARLIEST_CONFIRMED_M5"),
        "earliest_confirmed_tick": verdict.get("earliest_confirmed_tick") or range_probe.get("EARLIEST_CONFIRMED_TICK"),
        "verified_vs_probed": {
            "verified_saved_samples": [
                "bars/m5_xauusd_2026-09-28.jsonl (full day M5)",
                "ticks/ticks_xauusd_2026-02-16_12h.jsonl (1h tick sample)",
            ],
            "verified_bounded_tests": [
                "M5 periods A/B/C in m5_tests.json",
                "Tick 3h liquid samples in tick_tests.json (2026-02-16, 2026-06-02, 2026-09-15)",
            ],
            "probed_only": [
                "Range checkpoints in range_probe.json (not full-day acquisitions)",
                "DST windows in utc_dst.json",
            ],
            "note": "A successful liquid-hour sample does not prove full-day coverage.",
        },
        "data_files": data_files,
        "report_files": report_files,
        "reuse_policy": "Phase38 may read Phase37 samples for schema reference; never overwrite Phase37 files.",
    }
    write_json("phase37_inventory.json", inventory)
    return inventory
