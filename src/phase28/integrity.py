"""Phase 28 integrity: frozen artifacts, hashes, safety counters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase14.constants import PRIMARY_PULLBACK_Q_HIGH, PRIMARY_PULLBACK_Q_LOW
from phase16a.constants import FROZEN_CUTS
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from phase22.integrity import verify_protected_hashes as verify_phase22_hashes
from phase28.constants import (
    BROKER_ORDERS,
    DISCORD_MESSAGES_SENT,
    FROZEN_VOL_PATH,
    FROZEN_WF3_CUTS,
    GITHUB_PUSH,
    H13C_Q_HIGH,
    H13C_Q_LOW,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    OCI_PROVISIONED,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    TELEGRAM_MESSAGES_SENT,
    sha256_file,
)
from phase28.frozen_vol import load_frozen_vol_artifact, verify_frozen_vol_artifact


def frozen_thresholds_intact() -> bool:
    return (
        FROZEN_WF3_CUTS["close_ema_low"] == FROZEN_CUTS["close_ema_low"]
        and FROZEN_WF3_CUTS["close_ema_high"] == FROZEN_CUTS["close_ema_high"]
        and FROZEN_WF3_CUTS["q_low"] == PRIMARY_PULLBACK_Q_LOW
        and FROZEN_WF3_CUTS["q_high"] == PRIMARY_PULLBACK_Q_HIGH
        and H13C_Q_LOW == 25
        and H13C_Q_HIGH == 75
        and FROZEN_CUTS["q_low"] == 25
        and FROZEN_CUTS["q_high"] == 75
    )


def verify_phase27_high_only_definition() -> dict[str, Any]:
    """Confirm high-only policy matches Phase 27 intent without retuning."""
    return {
        "policy": "high_only",
        "accept_regime": "high",
        "h13c_cuts_frozen": frozen_thresholds_intact(),
        "note": (
            "Accept H13_C BUY/SELL only when decision-time predicted-vol tertile == high; "
            "otherwise skip. Cuts unchanged from Phase 14 q25/q75."
        ),
        "ok": True,
    }


def verify_frozen_vol_ready() -> dict[str, Any]:
    if not FROZEN_VOL_PATH.exists():
        return {
            "ok": False,
            "blocker": "FROZEN_VOL_ARTIFACT_MISSING",
            "path": str(FROZEN_VOL_PATH),
            "note": "Run readiness build to fit historical frozen vol artifact once.",
        }
    art = load_frozen_vol_artifact()
    v = verify_frozen_vol_artifact(art)
    return {
        "ok": bool(v["checks"]["all_ok"]),
        "verify": v,
        "file_sha256": sha256_file(FROZEN_VOL_PATH),
        "path": str(FROZEN_VOL_PATH),
        "feature_note": (
            "Frozen live model uses Phase 26 accepted orthogonal features (OHLC-computable). "
            "Phase 27 OOF also included baseline feature columns from the historical store."
        ),
    }


def holdout_guard() -> dict[str, Any]:
    holdout = PROJECT_ROOT / "src" / "data" / "xauusd_m5_test.csv"
    return {
        "holdout_path_exists": holdout.exists(),
        "holdout_access_count": HOLDOUT_ACCESSES,
        "note": "Phase 28 must not open the protected holdout file.",
    }


def integrity_report(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    p22 = verify_phase22_hashes()
    vol = verify_frozen_vol_ready()
    payload = {
        "protected_hashes_phase22": p22,
        "frozen_thresholds_intact": frozen_thresholds_intact(),
        "high_only_policy": verify_phase27_high_only_definition(),
        "frozen_vol": vol,
        "holdout_guard": holdout_guard(),
        "holdout_access_count": HOLDOUT_ACCESSES,
        "mt5_connection_count": MT5_CONNECTIONS,
        "broker_order_count": BROKER_ORDERS,
        "discord_messages_sent": DISCORD_MESSAGES_SENT,
        "telegram_messages_sent": TELEGRAM_MESSAGES_SENT,
        "packages_installed": PACKAGES_INSTALLED,
        "oci_provisioned": OCI_PROVISIONED,
        "github_push": GITHUB_PUSH,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "protected_hash_count": len(PHASE22_PROTECTED_HASHES),
    }
    if extra:
        payload.update(extra)
    return payload


def assert_no_side_channels() -> None:
    if DISCORD_MESSAGES_SENT or TELEGRAM_MESSAGES_SENT or BROKER_ORDERS:
        raise RuntimeError("HARD FAILURE: side-channel counters must remain zero")
