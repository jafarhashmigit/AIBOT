"""Verify Phase 33 artifacts were not modified by Phase 34."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phase34.constants import PHASE33_RAW_DIR, PHASE33_REPORTS, PROJECT_ROOT, PROTECTED_HASHES, file_sha256
from phase34.progress import write_json

# Snapshot of critical Phase 33 report files at Phase 34 start (content hash check each run).
PHASE33_IMMUTABLE_GLOBS = [
    "reports/phase33/final_verdict.json",
    "reports/phase33/provider_qualification.json",
    "reports/phase33/spread_analysis.json",
]


def _sha_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_phase33_immutability(*, baseline: dict[str, str] | None = None) -> dict[str, Any]:
    """If baseline provided, compare; else record current hashes as observed (first run establishes)."""
    observed = {}
    for rel in PHASE33_IMMUTABLE_GLOBS:
        path = PROJECT_ROOT / rel
        if path.is_file():
            observed[rel] = _sha_text(path)
        else:
            observed[rel] = None

    protected = {}
    intact = True
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        if not path.is_file():
            protected[rel] = "MISSING"
            intact = False
            continue
        actual = file_sha256(path)
        ok = actual == expected
        protected[rel] = "OK" if ok else "MISMATCH"
        if not ok:
            intact = False

    phase33_raw_writable_check = {
        "path": str(PHASE33_RAW_DIR).replace("\\", "/"),
        "exists": PHASE33_RAW_DIR.is_dir(),
        "phase34_write_policy": "READ_ONLY_SEED_ONLY",
    }

    mismatches = []
    if baseline:
        for rel, prev in baseline.items():
            if observed.get(rel) != prev:
                mismatches.append({"path": rel, "baseline": prev, "current": observed.get(rel)})

    report = {
        "phase33_report_hashes": observed,
        "baseline_provided": baseline is not None,
        "phase33_hash_mismatches": mismatches,
        "phase33_immutable_ok": len(mismatches) == 0,
        "protected_artifacts_intact": intact,
        "protected_status": protected,
        "phase33_raw": phase33_raw_writable_check,
        "phase33_reports_dir_exists": PHASE33_REPORTS.is_dir(),
    }
    write_json("phase33_immutability.json", report)
    return report
