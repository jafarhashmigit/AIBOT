"""MT5 order_send security review — documentation only; API remains PROHIBITED."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_9.constants import ORDER_SEND, canonical_json_sha256


def build_order_send_security_review() -> dict[str, Any]:
    input_surface = {
        "symbol": "Instrument name (must be XAUUSDm)",
        "action": "TRADE_ACTION_DEAL / PENDING / SLTP / MODIFY / REMOVE / CLOSE_BY",
        "order_type": "ORDER_TYPE_BUY/SELL and pending variants",
        "volume": "Lots; must align to volume_min/step/max",
        "price": "Request/limit price; market may use 0 depending filling",
        "sl": "Stop loss price",
        "tp": "Take profit price",
        "deviation": "Max price deviation (points)",
        "magic": "EA magic number / intent tag",
        "comment": "Order comment (size-limited)",
        "type_filling": "FOK / IOC / RETURN — must match symbol filling_mode",
        "type_time": "GTC / DAY / SPECIFIED time-in-force",
        "expiration": "For SPECIFIED TIF",
        "position": "Position ticket for close/modify paths",
        "position_by": "Close-by hedge position",
    }
    output_surface = {
        "retcode": "TRADE_RETCODE_* acceptance/rejection",
        "deal": "Deal ticket if immediate fill",
        "order": "Order ticket",
        "volume": "Filled volume (may be partial)",
        "price": "Execution price",
        "bid": "Market bid at request",
        "ask": "Market ask at request",
        "comment": "Broker comment",
        "request_id": "Terminal request id",
        "retcode_external": "External/broker code when present",
    }
    risks = [
        {"id": "accidental_execution", "severity": "CRITICAL", "mitigation": "BROKER_SUBMISSION_ENABLED=False; order_send PROHIBITED"},
        {"id": "wrong_account", "severity": "CRITICAL", "mitigation": "Preflight account fingerprint + server match"},
        {"id": "wrong_symbol", "severity": "HIGH", "mitigation": "Preflight ACTIVE_SYMBOL only; reject XAUUSD"},
        {"id": "wrong_volume", "severity": "HIGH", "mitigation": "min/max/step validation"},
        {"id": "wrong_direction", "severity": "HIGH", "mitigation": "Direction must match decision; SL/TP consistency"},
        {"id": "stale_price", "severity": "HIGH", "mitigation": "Fresh tick age gate"},
        {"id": "invalid_sl_tp", "severity": "HIGH", "mitigation": "Distance + direction checks"},
        {"id": "excessive_risk", "severity": "CRITICAL", "mitigation": "Risk calc + approved limits; else RISK_INCOMPLETE"},
        {"id": "duplicate_submission", "severity": "CRITICAL", "mitigation": "One intent per decision; durable before submit"},
        {"id": "replay_submission", "severity": "CRITICAL", "mitigation": "Replay flagged; no submit after restart without recon"},
        {"id": "partial_fill", "severity": "MEDIUM", "mitigation": "FSM preserves one-to-many deals"},
        {"id": "broker_rejection", "severity": "MEDIUM", "mitigation": "BROKER_REJECTED terminal; no auto-retry"},
        {"id": "timeout_unknown_state", "severity": "CRITICAL", "mitigation": "SUBMISSION_UNKNOWN → reconcile RO evidence first"},
        {"id": "client_timeout_after_broker_accept", "severity": "CRITICAL", "mitigation": "Never blind retry; RO history/orders/deals"},
        {"id": "crash_after_submission", "severity": "CRITICAL", "mitigation": "WAL intent before submit; recover → RECONCILIATION_PENDING"},
        {"id": "duplicate_retry", "severity": "CRITICAL", "mitigation": "Forbidden until RECONCILED/REJECTED"},
        {"id": "wrong_filling_mode", "severity": "HIGH", "mitigation": "Preflight filling bitmask check"},
        {"id": "wrong_execution_mode", "severity": "MEDIUM", "mitigation": "Symbol trade_exemode awareness"},
        {"id": "configuration_drift", "severity": "HIGH", "mitigation": "Symbol spec hash/version in preflight"},
        {"id": "authorization_bypass", "severity": "CRITICAL", "mitigation": "Multi-gate auth; env cannot authorize"},
    ]
    out = {
        "api": "order_send",
        "phase12_status": "PROHIBITED" if "order_send" in PROHIBITED_MT5_API else "UNEXPECTED",
        "aibot_status": ORDER_SEND,
        "input_surface": input_surface,
        "output_surface": output_surface,
        "security_risks": risks,
        "enabled_in_phase64_9": False,
        "pass": "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
