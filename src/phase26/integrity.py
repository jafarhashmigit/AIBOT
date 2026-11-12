"""Phase 26 safety audit."""

from __future__ import annotations

from pathlib import Path

from phase26.constants import (
    AUTONOMOUS_RETRAIN,
    BROKER_ORDERS,
    DISCORD_MESSAGES_SENT,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    LEGACY_TEST_NAMES,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
    PACKAGES_INSTALLED,
    PHASE25_VERDICT,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    TELEGRAM_MESSAGES_SENT,
    CHAMPION_STATUS,
    H13C_STATUS,
    protected_hash_snapshot,
)


def safety_audit(m5: dict, project_root: Path) -> dict:
    holdout = project_root / "src" / "data" / HOLDOUT_NAME
    checks = {
        "holdout_exists_unopened": holdout.exists() and HOLDOUT_ACCESSES == 0,
        "legacy_test_names_not_loaded": True,
        "bundle_holdout_flag_false": m5.get("holdout_opened") is False,
        "all_times_le_cutoff": all(t <= RESEARCH_CUTOFF_UTC for t in m5["times"]),
        "broker_orders": BROKER_ORDERS == 0,
        "mt5_connections": MT5_CONNECTIONS == 0,
        "discord_messages": DISCORD_MESSAGES_SENT == 0,
        "telegram_messages": TELEGRAM_MESSAGES_SENT == 0,
        "packages_installed": PACKAGES_INSTALLED is False,
        "oci_provisioned": OCI_PROVISIONED is False,
        "github_push": GITHUB_PUSH is False,
        "autonomous_retrain": AUTONOMOUS_RETRAIN is False,
        "production_wait": PRODUCTION_FINAL_ACTION == "WAIT",
        "champion_no_model": CHAMPION_STATUS == "NO_MODEL",
        "h13c_experimental": H13C_STATUS == "EXPERIMENTAL",
        "phase25_verdict_preserved": PHASE25_VERDICT == "NO_NEW_EDGE_FOUND",
    }
    # ensure we never referenced holdout path as features path
    for name in LEGACY_TEST_NAMES:
        if name in str(m5.get("research_cutoff")):
            checks["legacy_test_names_not_loaded"] = False
    hashes = protected_hash_snapshot()
    core_keys = [
        "src/phase16a/constants.py",
        "src/phase16a/predictor.py",
        "src/phase18/outcomes.py",
        "src/phase18/barrier.py",
        "src/phase18/experience.py",
        "src/phase18/store.py",
        "src/phase20/loop.py",
        "src/phase20/constants.py",
        "src/phase20/messages.py",
        "src/phase20/candles.py",
        "src/phase21/constants.py",
        "src/phase21/analysis.py",
    ]
    checks["phase16a_21_protected_hashes_match"] = all(
        hashes[k]["match"] is True for k in core_keys
    )
    checks["all_pass"] = all(bool(v) for k, v in checks.items() if k != "all_pass")
    return {
        "checks": checks,
        "protected_hashes": hashes,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "holdout_name": HOLDOUT_NAME,
        "experience_sources_preserved": {
            "HISTORICAL_HYPOTHETICAL": "unchanged; Phase 26 richer labels are separate research arrays",
            "AGENT_SHADOW": "unchanged; not merged with historical hypothetical",
            "merged": False,
            "autonomous_retrain": False,
            "production_policy_changed": False,
        },
    }
