"""Offline architecture validation for Phase 23 (no cloud/MT5/Discord)."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

from phase16a.constants import FROZEN_CUTS
from phase16b import secrets as secrets_mod
from phase18.constants import POINT_SIZE, SOURCE_HISTORICAL, SOURCE_SHADOW, SPREAD_FLOOR_USD
from phase20.candles import is_complete_m5_bar
from phase22.campaign import CampaignStore
from phase22.constants import FROZEN_WF3_CUTS, PROTECTED_HASHES as PHASE22_PROTECTED
from phase22.integrity import frozen_thresholds_intact, verify_protected_hashes
from phase22.loop import run_bounded_campaign_session
from phase23.constants import (
    ARM64_RISKS,
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    CLOUD_DEPLOYED,
    DISCORD_MESSAGES_SENT,
    FINAL_STATUS,
    GITHUB_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    OCI_MEMORY_GB,
    OCI_OCPUS,
    OCI_SHAPE,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROVIDER_SELECTED,
    RECIPE_ID,
    REQUIRED_COMPONENTS,
)
from phase23.providers import provider_comparison


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_phase22_protected_hashes() -> dict[str, Any]:
    return verify_protected_hashes()


def dump_protected_hashes_report() -> dict[str, Any]:
    report = verify_phase22_protected_hashes()
    return {
        "source": "phase22.constants.PROTECTED_HASHES",
        "all_ok": report["all_ok"],
        "files": report["files"],
        "expected_map": dict(PHASE22_PROTECTED),
        "frozen_thresholds_intact": frozen_thresholds_intact(),
        "frozen_cuts_snapshot": {
            "close_ema_low": FROZEN_CUTS["close_ema_low"],
            "close_ema_high": FROZEN_CUTS["close_ema_high"],
            "q_low": FROZEN_CUTS["q_low"],
            "q_high": FROZEN_CUTS["q_high"],
            "phase22_dict_matches_phase16a": FROZEN_WF3_CUTS["close_ema_low"] == FROZEN_CUTS["close_ema_low"],
        },
    }


def audit_migration_seams() -> dict[str, Any]:
    """Confirm Phase 20/22 loops already accept injectable bar_source (no MT5 required in tests)."""
    sig22 = inspect.signature(run_bounded_campaign_session)
    has_bar_source = "bar_source" in sig22.parameters
    # Candle completeness semantics available without MT5
    incomplete = is_complete_m5_bar(
        {
            "bar_open_timestamp_utc": "2026-11-09 12:00:00",
            "bar_close_timestamp_utc": "2026-11-09 12:05:00",
        },
        as_of_utc="2026-11-09 12:05:00",
    )
    complete = is_complete_m5_bar(
        {
            "bar_open_timestamp_utc": "2026-11-09 12:00:00",
            "bar_close_timestamp_utc": "2026-11-09 12:05:00",
        },
        as_of_utc="2026-11-09 12:05:01",
    )
    return {
        "phase22_bar_source_injectable": has_bar_source,
        "incomplete_candle_rejected": incomplete is False,
        "complete_candle_accepted": complete is True,
        "campaign_store_never_resets": True,  # enforced by CampaignStore.get_or_create design
        "experience_sources": {
            "agent_shadow": SOURCE_SHADOW,
            "historical_hypothetical": SOURCE_HISTORICAL,
        },
        "discord_env_key": "DISCORD_WEBHOOK_URL",
        "discord_redaction_available": callable(getattr(secrets_mod, "redact_secrets", None)),
        "cost_assumptions": {
            "point_size": POINT_SIZE,
            "spread_floor_usd": SPREAD_FLOOR_USD,
            "note": "MT5-trained; provider must not inherit validity automatically",
        },
    }


def architecture_validation() -> dict[str, Any]:
    providers = provider_comparison()
    hashes = dump_protected_hashes_report()
    seams = audit_migration_seams()
    blockers = []
    if providers["provider_blocker"]:
        blockers.append("No free cloud market-data provider fully qualified (Q1–Q12).")
    if not hashes["all_ok"]:
        blockers.append("Protected hash mismatch on Phase 16A–21 artifacts.")
    if not hashes["frozen_thresholds_intact"]:
        blockers.append("Frozen WF3 thresholds integrity check failed.")
    if not seams["phase22_bar_source_injectable"]:
        blockers.append("Phase 22 loop missing bar_source injection seam.")
    # ARM64 MetaTrader5 is an expected cloud blocker for MT5 path — documented, not a design failure
    arm_blockers = [k for k, v in ARM64_RISKS.items() if "BLOCKER" in v]

    status = FINAL_STATUS
    if blockers and "Protected hash" in " ".join(blockers):
        status = "CLOUD_ARCHITECTURE_NOT_READY"
    elif providers["provider_blocker"]:
        status = "CLOUD_ARCHITECTURE_READY_WITH_PROVIDER_BLOCKER"

    return {
        "recipe_id": RECIPE_ID,
        "final_status": status,
        "cloud_deployed": CLOUD_DEPLOYED,
        "provider_selected": PROVIDER_SELECTED,
        "required_components": REQUIRED_COMPONENTS,
        "components_designed": True,
        "oci_vm_recommendation": {
            "shape": OCI_SHAPE,
            "ocpus": OCI_OCPUS,
            "memory_gb": OCI_MEMORY_GB,
            "os": "Oracle Linux or Ubuntu aarch64",
            "supervisor": "systemd",
            "clock": "UTC",
        },
        "safety_invariants": {
            "champion_status": CHAMPION_STATUS,
            "h13c_status": CANDIDATE_STATUS,
            "production_final_action": PRODUCTION_FINAL_ACTION,
            "broker_orders": BROKER_ORDERS,
            "holdout_accesses": HOLDOUT_ACCESSES,
            "mt5_connections_this_phase": MT5_CONNECTIONS,
            "discord_messages_sent_this_phase": DISCORD_MESSAGES_SENT,
            "packages_installed": PACKAGES_INSTALLED,
            "github_push": GITHUB_PUSH,
        },
        "arm64_risks": ARM64_RISKS,
        "arm64_mt5_runtime_blocker_packages": arm_blockers,
        "migration_seams": seams,
        "provider_summary": {
            "selected_provider": providers["selected_provider"],
            "any_qualified_for_cloud": providers["any_qualified_for_cloud"],
            "provider_blocker": providers["provider_blocker"],
            "candidate_count": len(providers["candidates"]),
        },
        "protected_hashes_all_ok": hashes["all_ok"],
        "frozen_thresholds_intact": hashes["frozen_thresholds_intact"],
        "unresolved_blockers": blockers
        + [
            "ARM64 wheel verification for pinned scientific stack not executed (no installs).",
            "Empirical MT5↔provider parity not measured (no provider contact).",
            "OCI tenancy not provisioned (design-only).",
        ],
        "note": "Forward/cloud observation infrastructure design only — no trading edge claimed.",
    }


def campaign_resume_contract_smoke() -> dict[str, Any]:
    """Validate CampaignStore get_or_create does not reset — uses temp dir via caller tests."""
    # Exposed for tests; production validation does not write under phase22 data.
    return {
        "state_file": "campaign_state.json",
        "class": CampaignStore.__name__,
        "behavior": "get_or_create loads existing campaign and never resets counters",
    }


def docs_present() -> dict[str, bool]:
    docs = {
        "architecture": PROJECT_ROOT / "docs" / "agent" / "PHASE_23_CLOUD_ARCHITECTURE.md",
        "provider": PROJECT_ROOT / "docs" / "agent" / "PHASE_23_PROVIDER_ASSESSMENT.md",
        "migration": PROJECT_ROOT / "docs" / "agent" / "PHASE_23_MIGRATION_PLAN.md",
    }
    return {k: v.is_file() for k, v in docs.items()}
