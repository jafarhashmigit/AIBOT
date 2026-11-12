"""CSV/JSON ingestion with explicit mapping, quarantine, idempotency."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase62.constants import FIXTURES_DIR, canonical_json_sha256, file_sha256
from phase62.store import ExecutionStore

# Explicit optional maps — do not assume broker CSV headers until inspected
DEFAULT_CSV_COLUMN_MAP = {
    "Deal": "deal_id",
    "Order": "order_id",
    "Position": "position_id",
    "Symbol": "symbol",
    "Type": "side_or_type",
    "Direction": "side",
    "Volume": "volume",
    "Price": "actual_fill_price",
    "Order price": "requested_price",
    "Time": "fill_timestamp_utc",
    "Commission": "commission",
    "Swap": "swap",
    "Profit": "profit",
    "Fee": "fee",
    "Comment": "comment",
}


def _parse_ts(value: str | None, *, assume_utc: bool = True) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y.%m.%d %H:%M:%S.%f",
        "%d.%m.%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw[:26], fmt)
            if assume_utc and dt.tzinfo is None:
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if dt.tzinfo else dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            continue
    return None  # invalid — caller quarantines


def _num(v: Any) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", ""))
    except Exception:
        return None


def normalize_row(
    raw: dict[str, Any],
    *,
    column_map: dict[str, str],
    platform: str | None,
    pseudonymous_account_ref: str | None,
    source_provenance: str,
    source_file_sha256: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    mapped = {}
    for src, dst in column_map.items():
        if src in raw and raw[src] not in (None, ""):
            mapped[dst] = raw[src]
    # side resolution
    side = mapped.get("side")
    if not side and mapped.get("side_or_type"):
        tok = str(mapped["side_or_type"]).strip().lower()
        if tok in ("buy", "0"):
            side = "BUY"
        elif tok in ("sell", "1"):
            side = "SELL"
        else:
            # may be order type like "buy limit" 
            if "buy" in tok:
                side = "BUY"
            elif "sell" in tok:
                side = "SELL"
    deal_id = str(mapped["deal_id"]) if mapped.get("deal_id") not in (None, "") else None
    order_id = str(mapped["order_id"]) if mapped.get("order_id") not in (None, "") else None
    fill_ts = _parse_ts(str(mapped["fill_timestamp_utc"])) if mapped.get("fill_timestamp_utc") else None
    if mapped.get("fill_timestamp_utc") and fill_ts is None:
        return None, "invalid_timestamp"

    # No silent symbol normalization
    symbol = mapped.get("symbol")
    if symbol is not None:
        symbol = str(symbol).strip()  # trim only — do not uppercase/strip suffix

    volume = _num(mapped.get("volume"))
    fill = _num(mapped.get("actual_fill_price"))
    commission = _num(mapped.get("commission")) if "commission" in mapped else None
    # Empty commission field → null not zero
    if "commission" in mapped and str(mapped.get("commission")).strip() == "":
        commission = None

    if deal_id is None and order_id is None:
        return None, "missing_deal_and_order_id"
    if fill is None and deal_id is not None:
        # Deal without fill price — quarantine rather than invent
        return None, "deal_missing_fill_price"

    record = {
        "broker": "Exness",
        "environment": "DEMO",
        "pseudonymous_account_ref": pseudonymous_account_ref,
        "platform": platform or "UNKNOWN",
        "symbol": symbol,
        "order_id": order_id,
        "deal_id": deal_id,
        "position_id": str(mapped["position_id"]) if mapped.get("position_id") not in (None, "") else None,
        "side": side,
        "volume": volume,
        "entry_exit_classification": mapped.get("entry_exit_classification"),
        "order_type": mapped.get("side_or_type") if not side else mapped.get("order_type"),
        "requested_price": _num(mapped.get("requested_price")),
        "actual_fill_price": fill,
        "fill_timestamp_utc": fill_ts,
        "commission": commission,
        "swap": _num(mapped.get("swap")) if "swap" in mapped else None,
        "profit": _num(mapped.get("profit")) if "profit" in mapped else None,
        "fee": _num(mapped.get("fee")) if "fee" in mapped else None,
        "currency": mapped.get("currency"),
        "rejection_or_execution_status": mapped.get("rejection_or_execution_status") or "UNKNOWN",
        "source_timestamp_utc": fill_ts,
        "source_provenance": source_provenance,
        "source_file_sha256": source_file_sha256,
        "record_kind": "DEAL" if deal_id else "ORDER",
        "synthetic": False,
    }
    return record, None


def import_csv(
    store: ExecutionStore,
    path: Path,
    *,
    column_map: dict[str, str] | None = None,
    platform: str | None = None,
    pseudonymous_account_ref: str | None = None,
    timezone_assumption: str = "UTC_ASSUMED_WHEN_NAIVE",
) -> dict[str, Any]:
    column_map = column_map or DEFAULT_CSV_COLUMN_MAP
    text = path.read_text(encoding="utf-8-sig")
    raw_meta = store.save_raw(source_name=path.name, content=text, provenance=f"csv_import:{path.name}")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {"ok": False, "error": "empty_or_headerless_csv", "ingested": 0}

    # Detect unknown headers — do not silently remap
    headers = list(reader.fieldnames)
    mapped_headers = [h for h in headers if h in column_map]
    unmapped = [h for h in headers if h not in column_map]

    stats = {
        "ingested": 0,
        "duplicates": 0,
        "quarantined": 0,
        "rows": 0,
        "unmapped_headers": unmapped,
        "mapped_headers": mapped_headers,
        "source_sha256": raw_meta["sha256"],
        "timezone_assumption": timezone_assumption,
        "column_map_used": column_map,
    }
    for row in reader:
        stats["rows"] += 1
        rec, err = normalize_row(
            row,
            column_map=column_map,
            platform=platform,
            pseudonymous_account_ref=pseudonymous_account_ref,
            source_provenance=f"csv:{path.name}",
            source_file_sha256=raw_meta["sha256"],
        )
        if err:
            store.quarantine({"raw": row, "error": err}, err)
            stats["quarantined"] += 1
            continue
        assert rec is not None
        result = store.ingest_normalized(rec)
        if result["status"] == "INGESTED":
            stats["ingested"] += 1
        elif result["status"] == "DUPLICATE_SUPPRESSED":
            stats["duplicates"] += 1
        else:
            stats["quarantined"] += 1
    stats["ok"] = True
    stats["idempotent_reimport_safe"] = True
    return stats


def import_json_records(
    store: ExecutionStore,
    path: Path,
    *,
    platform: str | None = None,
    pseudonymous_account_ref: str | None = None,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    raw_meta = store.save_raw(source_name=path.name, content=text, provenance=f"json_import:{path.name}")
    data = json.loads(text)
    if isinstance(data, dict) and "records" in data:
        records = data["records"]
        synthetic_file = bool(data.get("synthetic"))
    elif isinstance(data, list):
        records = data
        synthetic_file = False
    else:
        return {"ok": False, "error": "unsupported_json_shape", "ingested": 0}

    stats = {"ingested": 0, "duplicates": 0, "quarantined": 0, "rows": 0, "source_sha256": raw_meta["sha256"]}
    for row in records:
        stats["rows"] += 1
        rec = dict(row)
        rec.setdefault("broker", "Exness")
        rec.setdefault("environment", "DEMO")
        rec.setdefault("platform", platform or "UNKNOWN")
        rec.setdefault("pseudonymous_account_ref", pseudonymous_account_ref)
        rec.setdefault("source_provenance", f"json:{path.name}")
        rec["source_file_sha256"] = raw_meta["sha256"]
        if synthetic_file:
            rec["synthetic"] = True
        result = store.ingest_normalized(rec, allow_synthetic=allow_synthetic and bool(rec.get("synthetic")))
        if result["status"] == "INGESTED":
            stats["ingested"] += 1
        elif result["status"] == "DUPLICATE_SUPPRESSED":
            stats["duplicates"] += 1
        else:
            stats["quarantined"] += 1
    stats["ok"] = True
    return stats


def write_synthetic_fixtures() -> dict[str, Any]:
    """Labeled synthetic fixtures for tests — must never enter genuine store unmarked."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = FIXTURES_DIR / "synthetic_deals.csv"
    json_path = FIXTURES_DIR / "synthetic_deals.json"
    csv_body = (
        "Deal,Order,Position,Symbol,Direction,Volume,Price,Time,Commission,Swap,Profit,Fee\n"
        "1001,2001,3001,XAUUSD,buy,0.01,2650.12,2026-01-05 10:00:00,,0,1.5,0\n"
        "1002,2001,3001,XAUUSD,sell,0.01,2651.00,2026-01-05 11:00:00,,0,0.8,0\n"
        "bad,,,XAUUSD,buy,0.01,,not-a-date,,,,\n"
    )
    csv_path.write_text(csv_body, encoding="utf-8")
    payload = {
        "synthetic": True,
        "label": "SYNTHETIC_NOT_GENUINE_EXNESS_EVIDENCE",
        "records": [
            {
                "deal_id": "S9001",
                "order_id": "S8001",
                "record_kind": "DEAL",
                "side": "BUY",
                "symbol": "XAUUSD",
                "volume": 0.01,
                "actual_fill_price": 2600.0,
                "fill_timestamp_utc": "2026-02-01 09:00:00",
                "commission": None,
                "synthetic": True,
            }
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    out = {
        "csv": str(csv_path),
        "json": str(json_path),
        "csv_sha256": file_sha256(csv_path),
        "json_sha256": file_sha256(json_path),
        "label": "SYNTHETIC_NOT_GENUINE_EXNESS_EVIDENCE",
        "must_not_enter_genuine_store_unmarked": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
