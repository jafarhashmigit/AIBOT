"""Protected-hash and safety checks for Phase 31."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase31.constants import (
    AGENT_SHADOW_WRITES,
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    H13C_STATUS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    RESEARCH_CUTOFF_UTC,
    TELEGRAM_MESSAGES_SENT,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_protected_hashes() -> dict:
    files = {}
    all_ok = True
    for rel, expected in PROTECTED_HASHES.items():
        p = PROJECT_ROOT / rel
        actual = sha256_file(p) if p.exists() else None
        ok = actual == expected
        files[rel] = {"ok": ok, "expected": expected, "actual": actual}
        if not ok:
            all_ok = False
    return {"all_ok": all_ok, "files": files}


def safety_snapshot() -> dict:
    holdout = PROJECT_ROOT / "src" / "data" / HOLDOUT_NAME
    hashes = verify_protected_hashes()
    return {
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13c": H13C_STATUS,
        "broker_orders": BROKER_ORDERS,
        "mt5_connections": MT5_CONNECTIONS,
        "discord_sent": DISCORD_MESSAGES_SENT,
        "telegram_sent": TELEGRAM_MESSAGES_SENT,
        "holdout_accessed": HOLDOUT_ACCESSES != 0,
        "holdout_file_exists": holdout.exists(),
        "agent_shadow_writes": AGENT_SHADOW_WRITES,
        "packages_installed": PACKAGES_INSTALLED,
        "github_push": GITHUB_PUSH,
        "protected_artifacts_intact": hashes["all_ok"],
        "protected_hashes": hashes,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "cutoff_ok": RESEARCH_CUTOFF_UTC == "2026-09-29 18:50:00",
    }
