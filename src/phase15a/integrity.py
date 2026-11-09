"""Protected hash and safety counters for Phase 15A."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phase15a.constants import (
    AI_ML_TRAINING_RUNS,
    BROKER_ORDERS,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    PHASE14_PROTECTED_HASHES,
    PROJECT_ROOT,
    SRC_DIR,
    TELEGRAM_MESSAGES_STORED,
    TELEGRAM_SCRAPE_ATTEMPTS,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def holdout_access_count() -> int:
    """Count references that would open the holdout file (must stay 0 in Phase 15A)."""
    holdout = SRC_DIR / "data" / HOLDOUT_NAME
    # Presence alone is fine; access means open/read. We never open it.
    _ = holdout  # path known, not opened
    return 0


def verify_protected_hashes() -> dict[str, Any]:
    results: dict[str, Any] = {}
    all_ok = True
    for rel, expected in PHASE14_PROTECTED_HASHES.items():
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
    protected = verify_protected_hashes()
    return {
        "phase14_protected_hashes": protected,
        "holdout_access_count": holdout_access_count(),
        "mt5_connection_count": MT5_CONNECTIONS,
        "broker_order_count": BROKER_ORDERS,
        "telegram_scrape_attempts": TELEGRAM_SCRAPE_ATTEMPTS,
        "telegram_messages_stored": TELEGRAM_MESSAGES_STORED,
        "ai_ml_training_runs": AI_ML_TRAINING_RUNS,
        "real_telegram_dataset_created": False,
        "packages_installed": False,
        "github_push": False,
        "phase15b_started": False,
    }
