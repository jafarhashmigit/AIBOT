"""Canonical broker evidence normalization — distinct record kinds."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from phase64_5.constants import (
    ACTIVE_SYMBOL,
    SCHEMA_VERSION,
    SIMULATED_LABEL,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    canonical_json_sha256,
    sha256_hex,
)


def _num(v: Any) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", ""))
    except Exception:
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip()


def parse_timestamp_raw(raw: str | None) -> dict[str, Any]:
    if raw is None or str(raw).strip() == "":
        return {
            "timestamp_raw": None,
            "timestamp_normalized": None,
            "timezone_provenance": UNKNOWN,
            "ok": False,
            "error": "missing_timestamp",
        }
    s = str(raw).strip()
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y.%m.%d %H:%M:%S.%f",
        "%d.%m.%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            datetime.strptime(s[:26], fmt)
            return {
                "timestamp_raw": s,
                "timestamp_normalized": s,  # preserve reported clock; do not invent TZ
                "timezone_provenance": UNKNOWN,
                "ok": True,
                "error": None,
            }
        except Exception:
            continue
    return {
        "timestamp_raw": s,
        "timestamp_normalized": None,
        "timezone_provenance": UNKNOWN,
        "ok": False,
        "error": "ambiguous_or_unparseable_timestamp",
    }


def resolve_side(direction: Any, type_or_side: Any) -> str | None:
    for tok in (direction, type_or_side):
        if tok is None:
            continue
        t = str(tok).strip().lower()
        if t in ("buy", "0"):
            return "BUY"
        if t in ("sell", "1"):
            return "SELL"
        if "buy" in t:
            return "BUY"
        if "sell" in t:
            return "SELL"
    return None


def make_event_id(*, kind: str, stable_key: str, body_hash: str) -> str:
    return sha256_hex(f"{SCHEMA_VERSION}:{kind}:{stable_key}:{body_hash}")


def normalize_deal_row(mapped: dict[str, Any], *, provenance: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Build BROKER_DEAL or reject. Balance rows must not become deals."""
    typ = str(mapped.get("type_or_side") or "").strip().lower()
    if typ == "balance":
        return None, "balance_row_not_a_deal"

    deal_id = _str_or_none(mapped.get("broker_deal_id"))
    order_id = _str_or_none(mapped.get("broker_order_id"))
    symbol = _str_or_none(mapped.get("symbol"))
    if symbol == SUPERSEDED_SYMBOL:
        return None, "superseded_symbol_xauusd"
    price = _num(mapped.get("price"))
    volume = _num(mapped.get("volume"))
    ts = parse_timestamp_raw(_str_or_none(mapped.get("timestamp_raw")))
    if not ts["ok"]:
        return None, ts["error"] or "bad_timestamp"
    if deal_id is None:
        return None, "missing_deal_id"
    if price is None:
        return None, "deal_missing_price"
    if volume is None:
        return None, "deal_missing_volume"

    side = resolve_side(mapped.get("direction"), mapped.get("type_or_side"))
    body = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": "BROKER_DEAL",
        "broker_deal_id": deal_id,
        "broker_order_id": order_id,
        "broker_position_id": _str_or_none(mapped.get("broker_position_id")),
        "symbol": symbol if symbol is not None else UNKNOWN,
        "side": side if side is not None else UNKNOWN,
        "volume": volume,
        "price": price,
        "commission": _num(mapped.get("commission")) if "commission" in mapped else None,
        "swap": _num(mapped.get("swap")) if "swap" in mapped else None,
        "fee": _num(mapped.get("fee")) if "fee" in mapped else None,
        "profit": _num(mapped.get("profit")) if "profit" in mapped else None,
        "comment": _str_or_none(mapped.get("comment")),
        "magic": _str_or_none(mapped.get("magic")),
        "entry_exit": _str_or_none(mapped.get("entry_exit")),
        "timestamp_raw": ts["timestamp_raw"],
        "timestamp_normalized": ts["timestamp_normalized"],
        "timezone_provenance": ts["timezone_provenance"],
        "is_fill": True,  # deal is an execution fill fragment; not a full position lifecycle
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label") or ("GENUINE" if not provenance.get("synthetic") else SIMULATED_LABEL),
    }
    # blanks for commission etc stay None — never 0 unless explicitly present as 0
    if "commission" in mapped and str(mapped.get("commission")).strip() == "":
        body["commission"] = None
    stable_key = f"deal:{deal_id}"
    body_hash = canonical_json_sha256({k: v for k, v in body.items() if k not in ("event_id",)})
    body["stable_key"] = stable_key
    body["body_hash"] = body_hash
    body["event_id"] = make_event_id(kind="BROKER_DEAL", stable_key=stable_key, body_hash=body_hash)
    body["provenance"] = provenance
    return body, None


def normalize_order_row(mapped: dict[str, Any], *, provenance: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    order_id = _str_or_none(mapped.get("broker_order_id"))
    if order_id is None:
        return None, "missing_order_id"
    symbol = _str_or_none(mapped.get("symbol"))
    if symbol == SUPERSEDED_SYMBOL:
        return None, "superseded_symbol_xauusd"
    body = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": "BROKER_ORDER",
        "broker_order_id": order_id,
        "symbol": symbol if symbol is not None else UNKNOWN,
        "side": resolve_side(mapped.get("direction"), mapped.get("type_or_side")) or UNKNOWN,
        "volume": _num(mapped.get("volume")),
        "price": _num(mapped.get("price")),
        "state": _str_or_none(mapped.get("state")) or UNKNOWN,
        "comment": _str_or_none(mapped.get("comment")),
        "timestamp_raw": _str_or_none(mapped.get("timestamp_raw")),
        "timezone_provenance": UNKNOWN,
        "is_fill": False,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label") or ("GENUINE" if not provenance.get("synthetic") else SIMULATED_LABEL),
    }
    ts = parse_timestamp_raw(body["timestamp_raw"])
    body["timestamp_normalized"] = ts["timestamp_normalized"]
    if body["timestamp_raw"] and not ts["ok"]:
        return None, ts["error"] or "bad_timestamp"
    stable_key = f"order:{order_id}"
    body_hash = canonical_json_sha256({k: v for k, v in body.items() if k not in ("event_id",)})
    body["stable_key"] = stable_key
    body["body_hash"] = body_hash
    body["event_id"] = make_event_id(kind="BROKER_ORDER", stable_key=stable_key, body_hash=body_hash)
    body["provenance"] = provenance
    return body, None


def normalize_balance_row(mapped: dict[str, Any], *, provenance: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    deal_id = _str_or_none(mapped.get("broker_deal_id"))
    ts = parse_timestamp_raw(_str_or_none(mapped.get("timestamp_raw")))
    if not ts["ok"]:
        return None, ts["error"] or "bad_timestamp"
    if deal_id is None:
        return None, "balance_missing_id"
    # Balance is NOT a trade deal / fill
    profit = _num(mapped.get("profit"))
    body = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": "BROKER_BALANCE_OPERATION",
        "broker_deal_id": deal_id,
        "symbol": _str_or_none(mapped.get("symbol")) or UNKNOWN,
        "type": "balance",
        "profit": profit,
        "balance": _num(mapped.get("balance")),
        "comment": _str_or_none(mapped.get("comment")),
        "commission": _num(mapped.get("commission")) if "commission" in mapped else None,
        "fee": _num(mapped.get("fee")) if "fee" in mapped else None,
        "swap": _num(mapped.get("swap")) if "swap" in mapped else None,
        "timestamp_raw": ts["timestamp_raw"],
        "timestamp_normalized": ts["timestamp_normalized"],
        "timezone_provenance": ts["timezone_provenance"],
        "is_fill": False,
        "is_trade": False,
        "synthetic": bool(provenance.get("synthetic")),
        "evidence_label": provenance.get("evidence_label") or ("GENUINE" if not provenance.get("synthetic") else SIMULATED_LABEL),
    }
    stable_key = f"balance:{deal_id}"
    body_hash = canonical_json_sha256({k: v for k, v in body.items() if k not in ("event_id",)})
    body["stable_key"] = stable_key
    body["body_hash"] = body_hash
    body["event_id"] = make_event_id(kind="BROKER_BALANCE_OPERATION", stable_key=stable_key, body_hash=body_hash)
    body["provenance"] = provenance
    return body, None


def normalize_fee_from_deal(deal: dict[str, Any]) -> dict[str, Any] | None:
    """Extract BROKER_FEE fragment when fee/commission/swap present — still may be incomplete."""
    parts = {}
    for k in ("commission", "swap", "fee"):
        if deal.get(k) is not None:
            parts[k] = deal[k]
    if not parts:
        return None
    body = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": "BROKER_FEE",
        "broker_deal_id": deal.get("broker_deal_id"),
        "broker_order_id": deal.get("broker_order_id"),
        "components": parts,
        "synthetic": deal.get("synthetic"),
        "evidence_label": deal.get("evidence_label"),
        "is_fill": False,
    }
    stable_key = f"fee:{deal.get('broker_deal_id')}"
    body_hash = canonical_json_sha256(body)
    body["stable_key"] = stable_key
    body["body_hash"] = body_hash
    body["event_id"] = make_event_id(kind="BROKER_FEE", stable_key=stable_key, body_hash=body_hash)
    body["provenance"] = deal.get("provenance")
    return body


def assert_active_symbol_or_unknown(symbol: Any) -> bool:
    if symbol in (None, UNKNOWN, ""):
        return True
    return str(symbol).strip() == ACTIVE_SYMBOL
