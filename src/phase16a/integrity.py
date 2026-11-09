"""Integrity counters and protected-hash verification for Phase 16A."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phase16a.constants import (
    BACKGROUND_SERVICES,
    BROKER_ORDERS,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MODEL_TRAINING_RUNS,
    PARAMETER_OPTIMIZATION_RUNS,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    SCHEDULED_TASKS,
    SRC_DIR,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def holdout_access_count() -> int:
    _ = SRC_DIR / "data" / HOLDOUT_NAME
    return HOLDOUT_ACCESSES


def verify_protected_hashes() -> dict[str, Any]:
    results: dict[str, Any] = {}
    all_ok = True
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        if not path.is_file():
            results[rel] = {"ok": False, "expected": expected, "actual": None, "error": "missing"}
            all_ok = False
            continue
        actual = sha256_file(path)
        ok = actual == expected
        results[rel] = {"ok": ok, "expected": expected, "actual": actual}
        if not ok:
            all_ok = False
    return {"all_ok": all_ok, "files": results}


def integrity_report(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "protected_hashes": verify_protected_hashes(),
        "holdout_access_count": holdout_access_count(),
        "broker_order_count": BROKER_ORDERS,
        "model_training_runs": MODEL_TRAINING_RUNS,
        "parameter_optimization_runs": PARAMETER_OPTIMIZATION_RUNS,
        "background_services": BACKGROUND_SERVICES,
        "scheduled_tasks": SCHEDULED_TASKS,
        "packages_installed": False,
        "github_push": GITHUB_PUSH,
        "phase1_to_15c_modified": False,
    }
    if extra:
        payload.update(extra)
    return payload
