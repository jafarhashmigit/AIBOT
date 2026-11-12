"""Centralized Discord publication gate — missing/unknown evidence ⇒ BLOCKED."""

from __future__ import annotations

from typing import Any

from signal_bot.orchestrator.constants import (
    CHAMPION_STATUS,
    COMMISSION,
    DEFAULT_MODE,
    DISCORD_ACTIONABLE_PUBLICATION,
    HARD_BLOCK_ACTIONABLE_DISCORD,
    H70_STATUS,
    MARGIN,
    MODE_AUTHORIZED,
    MODE_DISABLED,
    MODE_DRY_RUN,
    MODE_SHADOW,
    NET_PROFITABILITY,
    PROMPT09_VERDICT,
    PUBLICATION_AUTHORIZATION_ENABLED,
    RISK_POLICY,
    STRATEGY_APPROVAL,
    SWAP,
)
from signal_bot.orchestrator.contract import validate_signal_event


def evaluate_publication_gate(
    event: dict[str, Any],
    *,
    mode: str = DEFAULT_MODE,
    champion: str = CHAMPION_STATUS,
    publication_authorization_enabled: bool = PUBLICATION_AUTHORIZATION_ENABLED,
    approved_strategies: set[str] | None = None,
    cost_model_status: str = COMMISSION,
    risk_policy_status: str = RISK_POLICY,
    swap_status: str = SWAP,
    margin_status: str = MARGIN,
) -> dict[str, Any]:
    """
    Actionable Discord BUY/SELL requires ALL conditions.
    WAIT / status notifications are not 'actionable trading recommendations'.
    """
    approved_strategies = approved_strategies or set()
    blocks: list[str] = []
    validation = validate_signal_event(event)
    event = validation["event"]
    if not validation["ok"]:
        blocks.extend([f"schema:{e}" for e in validation["errors"] if e != "uncalibrated_confidence_cleared"])

    action = str(event.get("direction") or "WAIT").upper()
    strategy_id = str(event.get("strategy_id") or "")

    # Always-on safety
    if champion != "NO_MODEL" and champion not in approved_strategies:
        # Champion must be NO_MODEL until registry says otherwise; any other unapproved → block
        blocks.append("champion_not_approved")
    if champion == "NO_MODEL" and action in ("BUY", "SELL"):
        blocks.append("champion_NO_MODEL_blocks_actionable")

    if strategy_id.startswith("H70") or "H70_LS1" in strategy_id:
        blocks.append("H70_UNVALIDATED")
        if H70_STATUS != "VALIDATED":
            blocks.append(f"H70_status_{H70_STATUS}")

    if str(event.get("validation_status") or "").upper() not in {
        "INDEPENDENTLY_VALIDATED",
        "INDEPENDENT_VALIDATION_PASSED",
        "APPROVED",
    }:
        if action in ("BUY", "SELL"):
            blocks.append("strategy_validation_not_approved")

    if strategy_id not in approved_strategies and action in ("BUY", "SELL"):
        blocks.append("strategy_not_in_champion_registry")

    if str(event.get("validation_status") or "").upper() not in {
        "INDEPENDENTLY_VALIDATED",
        "INDEPENDENT_VALIDATION_PASSED",
    }:
        if action in ("BUY", "SELL"):
            blocks.append("independent_oos_not_passed")

    if cost_model_status in (None, "", "UNKNOWN", COMMISSION) or cost_model_status.upper() == "UNKNOWN":
        if action in ("BUY", "SELL"):
            blocks.append("cost_model_unknown")
    if swap_status in (None, "", "UNKNOWN", "UNKNOWN_FOR_EXECUTION") or "UNKNOWN" in str(swap_status).upper():
        if action in ("BUY", "SELL"):
            blocks.append("swap_unknown")
    if margin_status in (None, "", "INCOMPLETE", "UNKNOWN") or str(margin_status).upper() in {
        "INCOMPLETE",
        "UNKNOWN",
    }:
        if action in ("BUY", "SELL"):
            blocks.append("margin_incomplete")

    if risk_policy_status.upper() != "APPROVED":
        if action in ("BUY", "SELL"):
            blocks.append("risk_policy_unapproved")
    if str(event.get("risk_check_status") or "").upper() != "APPROVED":
        if action in ("BUY", "SELL"):
            blocks.append("risk_check_not_approved")

    prov = str(event.get("market_data_provenance") or event.get("evidence_classification") or "")
    if action in ("BUY", "SELL") and not prov:
        blocks.append("provenance_missing")
    if action in ("BUY", "SELL") and "HISTORICAL_BACKFILL" in prov.upper():
        blocks.append("provenance_historical_backfill_ineligible")

    dq = str(event.get("data_quality_status") or "")
    if action in ("BUY", "SELL") and dq not in {"OK", "ACCEPTED"}:
        blocks.append("data_quality_invalid")

    if event.get("stale") and action in ("BUY", "SELL"):
        blocks.append("signal_stale")
    if event.get("forming_bar") and action in ("BUY", "SELL"):
        blocks.append("forming_bar")

    if not publication_authorization_enabled:
        blocks.append("publication_authorization_disabled")
    if DISCORD_ACTIONABLE_PUBLICATION != "ENABLED":
        blocks.append("discord_actionable_publication_disabled")

    if STRATEGY_APPROVAL != "APPROVED" and action in ("BUY", "SELL"):
        blocks.append("strategy_approval_not_approved")
    if PROMPT09_VERDICT == "NO_QUALIFIED_STRATEGY" and action in ("BUY", "SELL"):
        blocks.append("prompt09_no_qualified_strategy")
    if NET_PROFITABILITY != "ESTABLISHED" and action in ("BUY", "SELL"):
        blocks.append("net_profitability_not_established")
    if HARD_BLOCK_ACTIONABLE_DISCORD and action in ("BUY", "SELL"):
        blocks.append("hard_block_actionable_discord")

    mode = str(mode or DEFAULT_MODE).upper()
    if mode != MODE_AUTHORIZED:
        blocks.append(f"mode_{mode}_not_authorized")
    if mode == MODE_AUTHORIZED and not publication_authorization_enabled:
        blocks.append("authorized_mode_without_explicit_flag")

    # Deduplicate block reasons
    uniq: list[str] = []
    for b in blocks:
        if b not in uniq:
            uniq.append(b)

    actionable = action in ("BUY", "SELL")
    allowed = actionable and len(uniq) == 0
    # WAIT is never an actionable trading recommendation publication
    if not actionable:
        allowed = False
        if "non_actionable_wait_or_status" not in uniq:
            # Not a failure — WAIT simply isn't gated for actionable Discord BUY/SELL
            pass

    status = "ALLOWED" if allowed else "BLOCKED"
    out_event = {
        **event,
        "publication_status": status,
        "publication_block_reasons": uniq,
        "publication_mode": mode,
        "actionable_discord": allowed,
    }
    return {
        "allowed": allowed,
        "status": status,
        "block_reasons": uniq,
        "mode": mode,
        "actionable": actionable,
        "event": out_event,
        "schema_validation": validation,
    }


def effective_operating_mode(requested: str | None = None) -> str:
    """Clamp AUTHORIZED requests down — env/config cannot unlock AUTHORIZED while hard-blocked."""
    req = str(requested or DEFAULT_MODE).upper()
    if req not in {MODE_DISABLED, MODE_DRY_RUN, MODE_SHADOW, MODE_AUTHORIZED}:
        return DEFAULT_MODE
    if req == MODE_AUTHORIZED:
        # Hard clamp: Prompt9 NO_QUALIFIED_STRATEGY + HARD_BLOCK_ACTIONABLE_DISCORD
        return MODE_SHADOW
    return req
