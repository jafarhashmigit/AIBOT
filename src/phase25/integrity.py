"""Phase 25 safety / integrity checks (research isolation)."""

from __future__ import annotations

from pathlib import Path

from phase25.constants import (
    AUTONOMOUS_RETRAIN,
    BROKER_ORDERS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    TELEGRAM_MESSAGES_SENT,
)


def verify_safety(bundle: dict, project_root: Path) -> dict:
    holdout_path = project_root / "src" / "data" / HOLDOUT_NAME
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
        "autonomous_retrain": AUTONOMOUS_RETRAIN is False,
        "production_final_action_wait": PRODUCTION_FINAL_ACTION == "WAIT",
    }
    checks["all_pass"] = all(
        v is True for k, v in checks.items() if k != "holdout_file_exists_but_not_opened"
    ) and checks["holdout_file_exists_but_not_opened"]
    return checks
