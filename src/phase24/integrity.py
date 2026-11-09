"""Read-only integrity helpers for Phase 24."""

from __future__ import annotations

from typing import Any

from phase22.integrity import frozen_thresholds_intact, verify_protected_hashes
from phase24.constants import (
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
)


def protected_hashes_report() -> dict[str, Any]:
    report = verify_protected_hashes()
    return {
        "source": "phase22.constants.PROTECTED_HASHES (read-only)",
        "all_ok": report["all_ok"],
        "files": report["files"],
        "frozen_thresholds_intact": frozen_thresholds_intact(),
        "phase16a_23_modified": False,
        "safety": {
            "champion_status": CHAMPION_STATUS,
            "h13c_status": CANDIDATE_STATUS,
            "production_final_action": PRODUCTION_FINAL_ACTION,
            "broker_orders": BROKER_ORDERS,
            "holdout_accesses": HOLDOUT_ACCESSES,
            "mt5_connections": MT5_CONNECTIONS,
            "discord_messages_sent": DISCORD_MESSAGES_SENT,
            "packages_installed": PACKAGES_INSTALLED,
            "oci_provisioned": OCI_PROVISIONED,
            "github_push": GITHUB_PUSH,
        },
    }
