"""Integrity counters and protected-hash verification for Phase 15C."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phase15c.constants import (
    BROKER_ORDERS,
    EXTERNAL_DATA_COLLECTED,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MODEL_TRAINING_RUNS,
    MT5_CONNECTIONS,
    PAID_SUBSCRIPTIONS,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    PROVIDER_MESSAGES_SENT,
    SRC_DIR,
    TELEGRAM_CONNECTIONS,
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
            results[rel] = {
                "ok": False,
                "expected": expected,
                "actual": None,
                "error": "missing_file",
            }
            all_ok = False
            continue
        actual = sha256_file(path)
        ok = actual == expected
        results[rel] = {"ok": ok, "expected": expected, "actual": actual}
        if not ok:
            all_ok = False
    return {"all_ok": all_ok, "files": results}


def integrity_report() -> dict[str, Any]:
    return {
        "protected_hashes": verify_protected_hashes(),
        "holdout_access_count": holdout_access_count(),
        "mt5_connection_count": MT5_CONNECTIONS,
        "broker_order_count": BROKER_ORDERS,
        "telegram_connections": TELEGRAM_CONNECTIONS,
        "provider_messages_sent": PROVIDER_MESSAGES_SENT,
        "external_data_collected": EXTERNAL_DATA_COLLECTED,
        "paid_subscriptions": PAID_SUBSCRIPTIONS,
        "model_training_runs": MODEL_TRAINING_RUNS,
        "packages_installed": False,
        "github_push": False,
        "phase15d_started": False,
        "phase1_to_15b_modified": False,
    }
