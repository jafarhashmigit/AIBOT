"""Phase 29 integrity — frozen cuts, hashes, safety counters."""

from __future__ import annotations

from typing import Any

from phase14.constants import PRIMARY_PULLBACK_Q_HIGH, PRIMARY_PULLBACK_Q_LOW
from phase16a.constants import FROZEN_CUTS
from phase22.integrity import verify_protected_hashes as verify_phase22_hashes
from phase28.integrity import verify_frozen_vol_ready
from phase29.constants import (
    BROKER_ORDERS,
    DISCORD_MESSAGES_SENT,
    FROZEN_WF3_CUTS,
    GITHUB_PUSH,
    H13C_Q_HIGH,
    H13C_Q_LOW,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    TELEGRAM_MESSAGES_SENT,
    protected_hash_snapshot,
)


def frozen_thresholds_intact() -> bool:
    return (
        FROZEN_WF3_CUTS["close_ema_low"] == FROZEN_CUTS["close_ema_low"]
        and FROZEN_WF3_CUTS["close_ema_high"] == FROZEN_CUTS["close_ema_high"]
        and H13C_Q_LOW == PRIMARY_PULLBACK_Q_LOW == 25
        and H13C_Q_HIGH == PRIMARY_PULLBACK_Q_HIGH == 75
    )


def integrity_report(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    holdout = PROJECT_ROOT / "src" / "data" / HOLDOUT_NAME
    payload = {
        "protected_hashes_phase22": verify_phase22_hashes(),
        "protected_hash_snapshot": protected_hash_snapshot(),
        "frozen_thresholds_intact": frozen_thresholds_intact(),
        "frozen_vol": verify_frozen_vol_ready(),
        "holdout_path_exists": holdout.exists(),
        "holdout_access_count": HOLDOUT_ACCESSES,
        "mt5_connection_count": MT5_CONNECTIONS,
        "broker_order_count": BROKER_ORDERS,
        "discord_messages_sent_counter": DISCORD_MESSAGES_SENT,
        "telegram_messages_sent": TELEGRAM_MESSAGES_SENT,
        "packages_installed": PACKAGES_INSTALLED,
        "github_push": GITHUB_PUSH,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "high_only_research_only": True,
    }
    if extra:
        payload.update(extra)
    return payload
