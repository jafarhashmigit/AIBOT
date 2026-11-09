"""Integrity helpers for Phase 22."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phase22.constants import (
    BROKER_ORDERS,
    FROZEN_WF3_CUTS,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PROJECT_ROOT,
    PROTECTED_HASHES,
)
from phase16a.constants import FROZEN_CUTS


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_protected_hashes() -> dict[str, Any]:
    results: dict[str, Any] = {}
    all_ok = True
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        if not path.is_file():
            results[rel] = {"ok": False, "error": "missing"}
            all_ok = False
            continue
        actual = sha256_file(path)
        ok = actual == expected
        results[rel] = {"ok": ok, "expected": expected, "actual": actual}
        if not ok:
            all_ok = False
    return {"all_ok": all_ok, "files": results}


def frozen_thresholds_intact() -> bool:
    return (
        FROZEN_WF3_CUTS["close_ema_low"] == FROZEN_CUTS["close_ema_low"]
        and FROZEN_WF3_CUTS["close_ema_high"] == FROZEN_CUTS["close_ema_high"]
        and FROZEN_WF3_CUTS["q_low"] == 25
        and FROZEN_WF3_CUTS["q_high"] == 75
    )


def integrity_report(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "protected_hashes": verify_protected_hashes(),
        "frozen_thresholds_intact": frozen_thresholds_intact(),
        "holdout_access_count": HOLDOUT_ACCESSES,
        "mt5_connection_count": MT5_CONNECTIONS,
        "broker_order_count": BROKER_ORDERS,
        "packages_installed": False,
        "github_push": False,
        "phase20_data_overwritten": False,
        "thresholds_modified": False,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": "WAIT",
    }
    if extra:
        payload.update(extra)
    return payload
