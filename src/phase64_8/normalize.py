"""Normalize live/fake MT5 evidence into journal records."""

from __future__ import annotations

from typing import Any

from phase64_8.constants import (
    DEAL_TYPE_BALANCE,
    DEAL_TYPE_BONUS,
    DEAL_TYPE_BUY,
    DEAL_TYPE_CHARGE,
    DEAL_TYPE_COMMISSION,
    DEAL_TYPE_CORRECTION,
    DEAL_TYPE_CREDIT,
    DEAL_TYPE_SELL,
    JOURNAL_SCHEMA_VERSION,
    METADATA_VERSION,
    STORE_BROKER_EVIDENCE,
    UNKNOWN,
)
from phase64_8.costs import separate_costs
from phase64_8.evidence_backend import _as_dict, _g
from phase64_8.identity import (
    account_fingerprint,
    body_hash,
    event_id,
    identity_class,
    stable_key_account,
    stable_key_deal,
    stable_key_order,
    stable_key_position,
)


def _side_from_type(t: Any) -> str:
    try:
        ti = int(t)
    except Exception:
        return UNKNOWN
    if ti == DEAL_TYPE_BUY:
        return "BUY"
    if ti == DEAL_TYPE_SELL:
        return "SELL"
    return UNKNOWN


def _is_balance_like(t: Any) -> bool:
    try:
        ti = int(t)
    except Exception:
        return False
    return ti in {
        DEAL_TYPE_BALANCE,
        DEAL_TYPE_CREDIT,
        DEAL_TYPE_CHARGE,
        DEAL_TYPE_CORRECTION,
        DEAL_TYPE_BONUS,
        DEAL_TYPE_COMMISSION,
    }


def normalize_account(acct: Any, *, retrieved_at: str, provenance: dict[str, Any]) -> dict[str, Any]:
    d = _as_dict(acct)
    account = {
        "login": _g(d, "login"),
        "server": _g(d, "server") or UNKNOWN,
        "company": _g(d, "company") or UNKNOWN,
        "currency": _g(d, "currency") or UNKNOWN,
        "leverage": _g(d, "leverage") if _g(d, "leverage") not in (None, 0) else UNKNOWN,
        "balance": _g(d, "balance"),
        "equity": _g(d, "equity"),
        "margin": _g(d, "margin"),
        "trade_mode": _g(d, "trade_mode"),
        "name": _g(d, "name") or UNKNOWN,
    }
    fp = account_fingerprint(account)
    payload = {
        "record_kind": "BROKER_ACCOUNT",
        "account_fingerprint": fp,
        "server": account["server"],
        "currency": account["currency"],
        "leverage": account["leverage"],
        "retrieval_timestamp": retrieved_at,
        "metadata_version": METADATA_VERSION,
        "login_last4": str(account["login"])[-4:] if account.get("login") is not None else UNKNOWN,
        "trade_mode": account["trade_mode"],
        "company": account["company"],
    }
    bh = body_hash(payload)
    sk = stable_key_account(fp, retrieved_at)
    return {
        **payload,
        "stable_key": sk,
        "identity_class": identity_class(sk),
        "body_hash": bh,
        "event_id": event_id(kind="BROKER_ACCOUNT", stable_key=sk, body=bh),
        "provenance": provenance,
        "store_label": STORE_BROKER_EVIDENCE,
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label"),
        # raw login kept only in in-memory collection for fingerprint checks; stripped before journal
        "_raw_login": account.get("login"),
    }


def normalize_position(raw: Any, *, retrieved_at: str, provenance: dict[str, Any]) -> dict[str, Any]:
    d = _as_dict(raw)
    ticket = _g(d, "ticket")
    payload = {
        "record_kind": "BROKER_POSITION",
        "broker_position_id": str(ticket) if ticket is not None else None,
        "symbol": _g(d, "symbol") or UNKNOWN,
        "direction": _side_from_type(_g(d, "type")),
        "volume": _g(d, "volume"),
        "open_price": _g(d, "price_open"),
        "current_price": _g(d, "price_current"),
        "sl": _g(d, "sl"),
        "tp": _g(d, "tp"),
        "profit": _g(d, "profit"),
        "swap": _g(d, "swap"),
        "magic": _g(d, "magic"),
        "comment": _g(d, "comment"),
        "observation_timestamp": retrieved_at,
        "broker_time": _g(d, "time"),
    }
    bh = body_hash(payload)
    sk = stable_key_position(ticket)
    return {
        **payload,
        "stable_key": sk,
        "identity_class": identity_class(sk),
        "body_hash": bh,
        "event_id": event_id(kind="BROKER_POSITION", stable_key=sk, body=bh),
        "provenance": provenance,
        "store_label": STORE_BROKER_EVIDENCE,
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label"),
    }


def normalize_order(
    raw: Any, *, retrieved_at: str, provenance: dict[str, Any], historical: bool = False
) -> dict[str, Any]:
    d = _as_dict(raw)
    ticket = _g(d, "ticket")
    payload = {
        "record_kind": "BROKER_ORDER",
        "broker_order_id": str(ticket) if ticket is not None else None,
        "symbol": _g(d, "symbol") or UNKNOWN,
        "order_type": _g(d, "type"),
        "requested_volume": _g(d, "volume_initial", _g(d, "volume_current")),
        "volume_current": _g(d, "volume_current"),
        "price": _g(d, "price_open"),
        "sl": _g(d, "sl"),
        "tp": _g(d, "tp"),
        "state": _g(d, "state"),
        "time_setup": _g(d, "time_setup"),
        "time_done": _g(d, "time_done"),
        "reason": _g(d, "reason"),
        "magic": _g(d, "magic"),
        "comment": _g(d, "comment"),
        "observation_timestamp": retrieved_at,
        "historical": historical,
    }
    bh = body_hash(payload)
    sk = stable_key_order(ticket, historical=historical)
    return {
        **payload,
        "stable_key": sk,
        "identity_class": identity_class(sk),
        "body_hash": bh,
        "event_id": event_id(kind="BROKER_ORDER", stable_key=sk, body=bh),
        "provenance": provenance,
        "store_label": STORE_BROKER_EVIDENCE,
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label"),
    }


def normalize_deal(raw: Any, *, retrieved_at: str, provenance: dict[str, Any]) -> dict[str, Any]:
    d = _as_dict(raw)
    ticket = _g(d, "ticket")
    typ = _g(d, "type")
    if _is_balance_like(typ):
        kind = "BROKER_BALANCE_OPERATION"
        direction = UNKNOWN
    else:
        kind = "BROKER_DEAL"
        direction = _side_from_type(typ)

    commission = _g(d, "commission")
    swap = _g(d, "swap")
    fee = _g(d, "fee")
    # Missing fields → UNKNOWN (do not treat absent as zero unless broker returned 0.0)
    costs = separate_costs(
        commission=commission if "commission" in d else None,
        swap=swap if "swap" in d else None,
        fee=fee if "fee" in d else None,
        execution_price=_g(d, "price"),
        reference_price=None,
    )

    order_id = _g(d, "order")
    position_id = _g(d, "position_id")
    payload = {
        "record_kind": kind,
        "broker_deal_id": str(ticket) if ticket is not None else None,
        "broker_order_id": str(order_id) if order_id not in (None, 0, "0") else None,
        "broker_position_id": str(position_id) if position_id not in (None, 0, "0") else None,
        "symbol": _g(d, "symbol") or ("" if kind == "BROKER_BALANCE_OPERATION" else UNKNOWN),
        "direction": direction,
        "deal_type": typ,
        "volume": _g(d, "volume"),
        "execution_price": _g(d, "price"),
        "commission": costs["commission"],
        "swap": costs["swap"],
        "fee": costs["fee"],
        "profit": _g(d, "profit"),
        "execution_timestamp": _g(d, "time"),
        "execution_timestamp_msc": _g(d, "time_msc"),
        "magic": _g(d, "magic"),
        "comment": _g(d, "comment"),
        "observation_timestamp": retrieved_at,
        "costs": costs,
    }
    bh = body_hash(payload)
    sk = stable_key_deal(ticket)
    return {
        **payload,
        "stable_key": sk,
        "identity_class": identity_class(sk),
        "body_hash": bh,
        "event_id": event_id(kind=kind, stable_key=sk, body=bh),
        "provenance": provenance,
        "store_label": STORE_BROKER_EVIDENCE,
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label"),
    }


def strip_for_journal(rec: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if not k.startswith("_")}
    return out
