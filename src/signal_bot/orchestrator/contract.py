"""Canonical signal-event contract — strict validation; no invented confidence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from signal_bot.orchestrator.constants import SYMBOL, TIMEFRAME, USER_TZ

ACTIONS = frozenset({"BUY", "SELL", "WAIT"})
ENTRY_TYPES = frozenset({"CLOSE", "NEXT_OPEN", "LIMIT", "MARKET_REF", "UNSPECIFIED"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_pkt(iso_utc: str | None) -> str | None:
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(USER_TZ)).isoformat()
    except Exception:
        return None


def new_signal_id() -> str:
    return f"sig_{uuid.uuid4().hex}"


def build_signal_event(
    *,
    action: str,
    decision_id: str,
    strategy_id: str,
    strategy_version: str,
    reason_codes: list[str] | None = None,
    setup_id: str | None = None,
    entry_reference: float | None = None,
    entry_type: str = "UNSPECIFIED",
    stop_loss: float | None = None,
    take_profit: float | None = None,
    reward_risk: float | None = None,
    expiry_utc: str | None = None,
    max_holding_bars: int | None = None,
    invalidation: str | None = None,
    confidence: float | None = None,
    calibrated: bool = False,
    evidence_classification: str | None = None,
    validation_status: str = "UNVALIDATED",
    risk_check_status: str = "UNAPPROVED",
    market_data_provenance: str | None = None,
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
    created_utc: str | None = None,
    forming_bar: bool = False,
    data_quality_status: str = "OK",
    stale: bool = False,
    authorizes_execution: bool = False,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created = created_utc or _utc_now()
    act = str(action or "WAIT").upper()
    if act not in ACTIONS:
        act = "WAIT"
        reason_codes = list(reason_codes or []) + ["INVALID_ACTION_FORCED_WAIT"]
    # Never invent confidence
    if not calibrated:
        confidence = None
    et = entry_type if entry_type in ENTRY_TYPES else "UNSPECIFIED"
    event = {
        "schema": "aibot_signal_event_v1",
        "signal_id": new_signal_id(),
        "decision_id": decision_id,
        "setup_id": setup_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": act,
        "action": act,
        "created_utc": created,
        "display_timestamp_pkt": to_pkt(created),
        "entry_reference": entry_reference,
        "entry_type": et,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "reward_risk": reward_risk,
        "expiry_utc": expiry_utc,
        "max_holding_bars": max_holding_bars,
        "invalidation": invalidation,
        "reason_codes": list(reason_codes or []),
        "confidence": confidence,
        "calibrated": bool(calibrated),
        "evidence_classification": evidence_classification,
        "validation_status": validation_status,
        "risk_check_status": risk_check_status,
        "market_data_provenance": market_data_provenance,
        "forming_bar": bool(forming_bar),
        "data_quality_status": data_quality_status,
        "stale": bool(stale),
        "authorizes_execution": bool(authorizes_execution),
        "publication_status": "PENDING_GATE",
        "publication_block_reasons": [],
    }
    if extras:
        event["extras"] = dict(extras)
    return event


def validate_signal_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return {ok, errors, event}. Does not invent fields."""
    errors: list[str] = []
    e = dict(event)
    for req in (
        "signal_id",
        "decision_id",
        "strategy_id",
        "strategy_version",
        "symbol",
        "timeframe",
        "direction",
        "created_utc",
        "validation_status",
        "risk_check_status",
    ):
        if e.get(req) in (None, ""):
            errors.append(f"missing_{req}")

    action = str(e.get("direction") or e.get("action") or "").upper()
    if action not in ACTIONS:
        errors.append("invalid_direction")

    if e.get("symbol") != SYMBOL:
        errors.append("symbol_must_be_XAUUSDm")
    if e.get("timeframe") != TIMEFRAME:
        errors.append("timeframe_must_be_M5")

    if e.get("calibrated") and e.get("confidence") is None:
        errors.append("calibrated_requires_confidence")
    if not e.get("calibrated") and e.get("confidence") is not None:
        # Force null — never present uncalibrated confidence as real
        e["confidence"] = None
        errors.append("uncalibrated_confidence_cleared")

    if action in ("BUY", "SELL"):
        for fld in ("entry_reference", "stop_loss", "take_profit"):
            if e.get(fld) is None:
                errors.append(f"actionable_missing_{fld}")
        try:
            entry = float(e["entry_reference"]) if e.get("entry_reference") is not None else None
            sl = float(e["stop_loss"]) if e.get("stop_loss") is not None else None
            tp = float(e["take_profit"]) if e.get("take_profit") is not None else None
        except (TypeError, ValueError):
            errors.append("invalid_price_types")
            entry = sl = tp = None
        if entry is not None and sl is not None and tp is not None:
            if action == "BUY":
                if not (sl < entry < tp):
                    errors.append("buy_price_order_invalid")
            else:
                if not (tp < entry < sl):
                    errors.append("sell_price_order_invalid")
            risk = abs(entry - sl)
            if risk <= 0:
                errors.append("non_positive_risk")
            else:
                rr = abs(tp - entry) / risk
                declared = e.get("reward_risk")
                if declared is not None:
                    try:
                        if abs(float(declared) - rr) > 1e-6:
                            errors.append("reward_risk_mismatch")
                    except (TypeError, ValueError):
                        errors.append("reward_risk_invalid")
                e["reward_risk"] = round(rr, 6)

    if e.get("forming_bar") is True and action in ("BUY", "SELL"):
        errors.append("forming_bar_actionable")
    if e.get("stale") is True and action in ("BUY", "SELL"):
        errors.append("stale_actionable")
    if str(e.get("data_quality_status") or "") not in {"OK", "ACCEPTED", ""} and action in ("BUY", "SELL"):
        errors.append("data_quality_blocks_actionable")

    # Expiry
    if e.get("expiry_utc") and action in ("BUY", "SELL"):
        try:
            exp = datetime.fromisoformat(str(e["expiry_utc"]).replace("Z", "+00:00"))
            created = datetime.fromisoformat(str(e["created_utc"]).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if exp <= created:
                errors.append("expiry_not_after_created")
            if exp <= now:
                errors.append("signal_expired")
        except Exception:
            errors.append("expiry_unparseable")

    ok = len([x for x in errors if x != "uncalibrated_confidence_cleared"]) == 0
    return {"ok": ok, "errors": errors, "event": e}


def decision_to_signal_event(decision: dict[str, Any], *, market_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map Phase54 decide() output into canonical signal event."""
    ms = market_state or {}
    return build_signal_event(
        action=str(decision.get("action") or "WAIT"),
        decision_id=str(decision.get("decision_id") or uuid.uuid4().hex),
        strategy_id=str(decision.get("hypothesis_id") or decision.get("model_policy_version") or "NULL_POLICY"),
        strategy_version=str(decision.get("model_policy_version") or "unknown"),
        reason_codes=list(decision.get("reason_codes") or []),
        setup_id=decision.get("setup_id"),
        entry_reference=decision.get("entry_reference"),
        entry_type="CLOSE" if decision.get("entry_reference") is not None else "UNSPECIFIED",
        stop_loss=decision.get("stop_loss"),
        take_profit=decision.get("take_profit"),
        reward_risk=decision.get("reward_risk"),
        expiry_utc=decision.get("signal_expiry_utc"),
        max_holding_bars=decision.get("max_hold_bars"),
        invalidation=decision.get("invalidation"),
        confidence=decision.get("confidence") if decision.get("calibrated_probabilities") else None,
        calibrated=bool(decision.get("calibrated_probabilities")),
        evidence_classification=ms.get("evidence_classification") or ms.get("evidence_provenance"),
        validation_status=str(ms.get("validation_status") or "UNVALIDATED"),
        risk_check_status=str((decision.get("risk_check_status") or RISK_PLACEHOLDER)),
        market_data_provenance=ms.get("market_data_provenance") or ms.get("provenance"),
        symbol=str(decision.get("instrument") or ms.get("symbol") or SYMBOL),
        timeframe=str(decision.get("timeframe") or TIMEFRAME),
        created_utc=decision.get("created_iso") or decision.get("timestamp_utc"),
        forming_bar=bool(ms.get("forming_bar")),
        data_quality_status=str(ms.get("data_quality_status") or decision.get("data_quality_status") or "OK"),
        stale=bool(ms.get("stale")),
        authorizes_execution=bool(decision.get("authorizes_execution")),
    )


RISK_PLACEHOLDER = "UNAPPROVED"
