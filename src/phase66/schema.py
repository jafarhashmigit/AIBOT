"""Evidence identity, provenance, and record builders.

Market observation identity (content_hash / body_hash / stable_key) must NOT depend on
retrieval-only metadata such as collection_timestamp_utc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase66.constants import (
    ACTIVE_SYMBOL,
    BROKER_OBSERVED,
    COLLECTOR_VERSION,
    DATASET_VERSION,
    SCHEMA_VERSION,
    SERVER_TZ,
    SYNTHETIC_TEST_FIXTURE,
    USER_TZ,
    canonical_json_sha256,
    sha256_hex,
)

UTC = ZoneInfo("UTC")
PKT = ZoneInfo(USER_TZ)

# Identity schema: v2 = market-only hash + identity stable_key (no retrieval metadata).
IDENTITY_SCHEMA_VERSION = "market_identity_v2"

# Fields that must never enter market content_hash (retrieval / process metadata).
RETRIEVAL_METADATA_FIELDS = frozenset(
    {
        "collection_timestamp_utc",
        "collector_started_utc",
        "collector_cycle",
        "retrieval_attempt",
        "ingested_utc",
        "import_batch_id",
        "user_facing_pkt",
        "raw_source",
        "evidence_provenance",  # classification metadata; not market OHLC/quote
        "note",
        "journal_schema_version",
        "store_label",
        "prior",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_pkt(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(PKT).isoformat()


def stable_evidence_id(*, kind: str, symbol: str, server_ts: str, payload_key: str) -> str:
    """Deterministic ID from canonical source fields — not random/PID."""
    raw = f"{kind}|{symbol}|{server_ts}|{payload_key}|{SCHEMA_VERSION}|{IDENTITY_SCHEMA_VERSION}"
    return f"ev_{sha256_hex(raw)[:32]}"


def quote_market_payload(
    *,
    symbol: str,
    server_time_utc: str,
    bid: float | None,
    ask: float | None,
    spread: float | None,
) -> dict[str, Any]:
    """Stable market fields for quote identity hashing."""
    return {
        "kind": "QUOTE_SNAPSHOT",
        "symbol": symbol,
        "timeframe": "TICK_SNAPSHOT",
        "server_timestamp_utc": server_time_utc,
        "bid": bid,
        "ask": ask,
        "spread": spread,
    }


def m5_market_payload(*, symbol: str, bar: dict[str, Any], server_timestamp_utc: str) -> dict[str, Any]:
    """Stable market fields for M5 bar identity hashing."""
    payload: dict[str, Any] = {
        "kind": "M5_BAR",
        "symbol": symbol,
        "timeframe": "M5",
        "server_timestamp_utc": server_timestamp_utc,
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "tick_volume": bar.get("tick_volume"),
    }
    if bar.get("spread") is not None:
        payload["spread_points_bar"] = bar.get("spread")
    # Omit missing/zero real_volume — MT5 often returns 0; including it caused false conflicts
    # vs records that omitted the field.
    rv = bar.get("real_volume")
    if rv is not None and float(rv) != 0.0:
        payload["real_volume"] = rv
    return payload


def market_content_hash(payload: dict[str, Any]) -> str:
    return canonical_json_sha256(payload)


def m5_stable_key(*, symbol: str, server_timestamp_utc: str) -> str:
    """Identity key: same bar open time → same key (content differences → conflict)."""
    return f"market_m5:{symbol}:M5:{server_timestamp_utc}"


def quote_stable_key(*, symbol: str, server_time_utc: str) -> str:
    """Identity key: same quote server timestamp → same key (price differences → conflict)."""
    return f"market_quote:{symbol}:QUOTE:{server_time_utc}"


def build_quote_record(
    *,
    bid: float,
    ask: float,
    server_time_utc: str,
    collection_time_utc: str,
    source_server: str,
    session_state: str,
    evidence_class: str,
    raw_payload: dict[str, Any],
    validation_status: str = "OK",
    rejection_reason: str | None = None,
    symbol: str = ACTIVE_SYMBOL,
) -> dict[str, Any]:
    spread = ask - bid if bid is not None and ask is not None else None
    payload_key = f"{bid}|{ask}|{spread}"
    eid = stable_evidence_id(kind="quote", symbol=symbol, server_ts=server_time_utc, payload_key=payload_key)
    market = quote_market_payload(
        symbol=symbol,
        server_time_utc=server_time_utc,
        bid=bid,
        ask=ask,
        spread=spread,
    )
    content_hash = market_content_hash(market)
    stable_key = quote_stable_key(symbol=symbol, server_time_utc=server_time_utc)
    body = {
        "evidence_id": eid,
        "kind": "QUOTE_SNAPSHOT",
        "symbol": symbol,
        "timeframe": "TICK_SNAPSHOT",
        "source_classification": evidence_class,
        "source_server": source_server,
        "server_timestamp_utc": server_time_utc,
        "collection_timestamp_utc": collection_time_utc,
        "user_facing_pkt": to_pkt(server_time_utc),
        "timezone_canonical": SERVER_TZ,
        "timestamp_precision": "second_or_better_from_symbol_info_time",
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "session_state": session_state,
        "schema_version": SCHEMA_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "dataset_version": DATASET_VERSION,
        "validation_status": validation_status,
        "rejection_reason": rejection_reason,
        "raw_source": raw_payload,
        "synthetic": evidence_class == SYNTHETIC_TEST_FIXTURE,
        "evidence_label": evidence_class,
        "authorizes_execution": False,
        "permits_new_entry": False,  # collection ≠ entry permission
        "content_hash": content_hash,
        "body_hash": content_hash,
        "stable_key": stable_key,
        "event_id": f"evt_{sha256_hex(f'{stable_key}:{content_hash}')[:24]}",
        "market_payload": market,
    }
    return body


def build_m5_record(
    *,
    bar: dict[str, Any],
    collection_time_utc: str,
    source_server: str,
    session_state: str,
    evidence_class: str,
    validation_status: str = "OK",
    rejection_reason: str | None = None,
    symbol: str = ACTIVE_SYMBOL,
) -> dict[str, Any]:
    ts = str(bar.get("timestamp_utc") or bar.get("time") or "")
    payload_key = f"{bar.get('open')}|{bar.get('high')}|{bar.get('low')}|{bar.get('close')}|{bar.get('tick_volume')}"
    eid = stable_evidence_id(kind="m5", symbol=symbol, server_ts=ts, payload_key=payload_key)
    market = m5_market_payload(symbol=symbol, bar=bar, server_timestamp_utc=ts)
    content_hash = market_content_hash(market)
    stable_key = m5_stable_key(symbol=symbol, server_timestamp_utc=ts)
    body = {
        "evidence_id": eid,
        "kind": "M5_BAR",
        "symbol": symbol,
        "timeframe": "M5",
        "source_classification": evidence_class,
        "source_server": source_server,
        "server_timestamp_utc": ts,
        "collection_timestamp_utc": collection_time_utc,
        "user_facing_pkt": to_pkt(ts) if "T" in ts else None,
        "timezone_canonical": SERVER_TZ,
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "tick_volume": bar.get("tick_volume"),
        "spread_points_bar": bar.get("spread"),
        "real_volume": bar.get("real_volume"),
        "session_state": session_state,
        "schema_version": SCHEMA_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "dataset_version": DATASET_VERSION,
        "validation_status": validation_status,
        "rejection_reason": rejection_reason,
        "raw_source": bar,
        "synthetic": evidence_class == SYNTHETIC_TEST_FIXTURE,
        "evidence_label": evidence_class,
        "authorizes_execution": False,
        "note": "M5 bar is not a genuine tick; never infer ticks from candles",
        "content_hash": content_hash,
        "body_hash": content_hash,
        "stable_key": stable_key,
        "event_id": f"evt_{sha256_hex(f'{stable_key}:{content_hash}')[:24]}",
        "market_payload": market,
    }
    return body
