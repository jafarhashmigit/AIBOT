"""Phase38 integrity audit (read-only) + Phase40 provenance inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase40.constants import (
    PHASE38_MANIFESTS,
    PHASE38_RAW_M5,
    PHASE38_RAW_TICKS,
    PHASE38_ROOT,
    TARGET_DATES,
    file_sha256,
)
from phase40.progress import write_json


def audit_phase38() -> dict[str, Any]:
    files = []
    if PHASE38_ROOT.exists():
        for p in sorted(PHASE38_ROOT.rglob("*")):
            if p.is_file():
                files.append(
                    {
                        "path": p.as_posix(),
                        "bytes": p.stat().st_size,
                        "sha256": file_sha256(p),
                    }
                )
    # verify manifests vs files where present
    manifest_checks = []
    ok = True
    if PHASE38_MANIFESTS.exists():
        for man in sorted(PHASE38_MANIFESTS.glob("*.manifest.json")):
            meta = json.loads(man.read_text(encoding="utf-8"))
            fp = Path(meta.get("file_path") or "")
            row = {"manifest": man.name, "expected_sha256": meta.get("sha256")}
            if not fp.is_file():
                row["ok"] = False
                row["error"] = "missing_file"
                ok = False
            else:
                dig = file_sha256(fp)
                row["actual_sha256"] = dig
                row["ok"] = dig == meta.get("sha256")
                if not row["ok"]:
                    ok = False
            manifest_checks.append(row)

    tick_windows = {}
    for day in TARGET_DATES:
        p = PHASE38_RAW_TICKS / f"ticks_XAUUSD_{day}_12h.jsonl"
        if p.is_file():
            lines = p.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])["timestamp_utc"] if lines else None
            last = json.loads(lines[-1])["timestamp_utc"] if lines else None
            tick_windows[day] = {"n": len(lines), "first": first, "last": last, "note": "Phase38 liquid 12h window only"}

    report = {
        "phase38_root": str(PHASE38_ROOT),
        "n_files": len(files),
        "files": files,
        "manifest_checks": manifest_checks,
        "manifest_integrity_ok": ok,
        "m5_dates_present": sorted(
            p.stem.replace("m5_XAUUSD_", "") for p in PHASE38_RAW_M5.glob("m5_XAUUSD_*.jsonl")
        )
        if PHASE38_RAW_M5.exists()
        else [],
        "phase38_tick_windows": tick_windows,
        "overwrite_policy": "Phase40 NEVER modifies Phase38 files; new data only under src/data/phase40/",
    }
    write_json("phase38_integrity_audit.json", report)
    return report
