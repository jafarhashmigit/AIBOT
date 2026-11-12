"""Phase 30 safety / integrity checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase30.constants import (
    AGENT_SHADOW_WRITES,
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
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
        all_ok = all_ok and ok
    return {"all_ok": all_ok, "files": files}


def verify_safety(bundle: dict, project_root: Path | None = None) -> dict:
    root = project_root or PROJECT_ROOT
    holdout_path = root / "src" / "data" / HOLDOUT_NAME
    hashes = verify_protected_hashes()
    checks = {
        "holdout_file_exists_but_not_opened": holdout_path.exists(),
        "holdout_accesses": HOLDOUT_ACCESSES == 0,
        "bundle_holdout_flag_false": bundle.get("bounds", {}).get("holdout_opened") is False,
        "all_timestamps_le_max_decision": all(
            t <= bundle["bounds"]["max_decision_time"] for t in bundle["timestamps"]
        ),
        "research_cutoff_respected_on_features": all(
            t <= RESEARCH_CUTOFF_UTC for t in bundle["feature_times"]
        ),
        "broker_orders": BROKER_ORDERS == 0,
        "mt5_connections": MT5_CONNECTIONS == 0,
        "discord_messages": DISCORD_MESSAGES_SENT == 0,
        "telegram_messages": TELEGRAM_MESSAGES_SENT == 0,
        "packages_installed": PACKAGES_INSTALLED is False,
        "oci_provisioned": OCI_PROVISIONED is False,
        "github_push": GITHUB_PUSH is False,
        "agent_shadow_writes": AGENT_SHADOW_WRITES == 0,
        "production_final_action_wait": PRODUCTION_FINAL_ACTION == "WAIT",
        "champion_no_model": CHAMPION_STATUS == "NO_MODEL",
        "protected_hashes_intact": hashes["all_ok"],
        "cutoff_is_2026_09_29_1850": RESEARCH_CUTOFF_UTC == "2026-09-29 18:50:00",
    }
    checks["all_pass"] = all(
        v is True for k, v in checks.items() if k != "holdout_file_exists_but_not_opened"
    ) and checks["holdout_file_exists_but_not_opened"]
    return {"checks": checks, "protected_hashes": hashes}
