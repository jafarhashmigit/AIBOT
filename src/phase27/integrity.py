"""Phase 27 safety audit."""

from __future__ import annotations

from pathlib import Path

from phase14.constants import PRIMARY_PULLBACK_Q_HIGH, PRIMARY_PULLBACK_Q_LOW
from phase27.constants import (
    AUTONOMOUS_RETRAIN,
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    H13C_Q_HIGH,
    H13C_Q_LOW,
    H13C_STATUS,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
    PACKAGES_INSTALLED,
    PHASE25_VERDICT,
    PHASE26_VERDICT,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    TELEGRAM_MESSAGES_SENT,
    protected_hash_snapshot,
)


def safety_audit(m5: dict, project_root: Path) -> dict:
    holdout = project_root / "src" / "data" / HOLDOUT_NAME
    hashes = protected_hash_snapshot()
    core = [
        k
        for k, v in hashes.items()
        if v.get("expected") and k.startswith("src/phase")
    ]
    checks = {
        "holdout_exists_unopened": holdout.exists() and HOLDOUT_ACCESSES == 0,
        "m5_holdout_flag_false": m5.get("holdout_opened") is False,
        "times_le_cutoff": all(t <= RESEARCH_CUTOFF_UTC for t in m5["times"]),
        "h13c_q_low_unchanged": H13C_Q_LOW == PRIMARY_PULLBACK_Q_LOW == 25,
        "h13c_q_high_unchanged": H13C_Q_HIGH == PRIMARY_PULLBACK_Q_HIGH == 75,
        "broker_orders": BROKER_ORDERS == 0,
        "mt5": MT5_CONNECTIONS == 0,
        "discord": DISCORD_MESSAGES_SENT == 0,
        "telegram": TELEGRAM_MESSAGES_SENT == 0,
        "packages": PACKAGES_INSTALLED is False,
        "oci": OCI_PROVISIONED is False,
        "github_push": GITHUB_PUSH is False,
        "autonomous_retrain": AUTONOMOUS_RETRAIN is False,
        "production_wait": PRODUCTION_FINAL_ACTION == "WAIT",
        "champion_no_model": CHAMPION_STATUS == "NO_MODEL",
        "h13c_experimental": H13C_STATUS == "EXPERIMENTAL",
        "phase25_preserved": PHASE25_VERDICT == "NO_NEW_EDGE_FOUND",
        "phase26_preserved": PHASE26_VERDICT == "PROMISING_BUT_UNCONFIRMED",
        "phase16a_21_hashes_match": all(hashes[k]["match"] is True for k in core),
    }
    checks["all_pass"] = all(bool(v) for k, v in checks.items() if k != "all_pass")
    return {
        "checks": checks,
        "protected_hashes": hashes,
        "experience_sources": {
            "HISTORICAL_HYPOTHETICAL": "preserved",
            "AGENT_SHADOW": "preserved",
            "merged": False,
        },
    }
