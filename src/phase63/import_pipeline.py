"""Genuine Exness MT5 demo CSV import — reuses Phase62 store; no fabricated evidence."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from phase62.importers import DEFAULT_CSV_COLUMN_MAP, import_csv
from phase62.store import ExecutionStore
from phase63.constants import EXPORTS_DIR, SCHEMA_SAMPLES_DIR, canonical_json_sha256, file_sha256
from phase63.progress import write_json

# Known MT5 / Exness History → Deals export header variants (candidates only)
MT5_DEALS_HEADER_CANDIDATES = {
    "Deal": "deal_id",
    "Order": "order_id",
    "Position": "position_id",
    "Symbol": "symbol",
    "Type": "side_or_type",
    "Direction": "side",
    "Volume": "volume",
    "Price": "actual_fill_price",
    "Order price": "requested_price",
    "Price / Order": "requested_price",
    "Time": "fill_timestamp_utc",
    "Time (Server)": "fill_timestamp_utc",
    "Commission": "commission",
    "Swap": "swap",
    "Profit": "profit",
    "Fee": "fee",
    "Comment": "comment",
    "Entry": "entry_exit_classification",
    "Magic": "magic",
}


def discover_csv_headers(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    mapped = {h: MT5_DEALS_HEADER_CANDIDATES[h] for h in headers if h in MT5_DEALS_HEADER_CANDIDATES}
    unmapped = [h for h in headers if h not in MT5_DEALS_HEADER_CANDIDATES]
    required_for_deal = {"Deal", "Symbol", "Price", "Time", "Volume"}
    # Direction OR Type for side
    has_side = ("Direction" in headers) or ("Type" in headers)
    missing_critical = sorted(required_for_deal - set(headers))
    if not has_side:
        missing_critical.append("Direction|Type")
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "headers": headers,
        "mapped": mapped,
        "unmapped": unmapped,
        "missing_critical_headers": missing_critical,
        "mappable": len(missing_critical) == 0,
        "timezone_semantics": "NAIVE_TIMESTAMPS_PRESERVED_AS_REPORTED_UTC_ASSUMPTION_LABELED",
        "inspected_before_mapping": True,
    }


def list_genuine_exports() -> list[Path]:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(EXPORTS_DIR.glob("*.csv")) + sorted(EXPORTS_DIR.glob("*.CSV"))


def build_column_map(discovered: dict[str, Any]) -> dict[str, str]:
    # Only map headers actually present
    return dict(discovered.get("mapped") or {})


def import_genuine_exports(
    store: ExecutionStore,
    *,
    expected_symbol: str = "XAUUSDm",
    expected_environment: str = "DEMO",
    platform: str = "MT5",
    pseudonymous_account_ref: str | None = None,
) -> dict[str, Any]:
    files = list_genuine_exports()
    if not files:
        return {
            "status": "AWAITING_GENUINE_DEMO_EXPORT",
            "exports_dir": str(EXPORTS_DIR),
            "n_files": 0,
            "imports": [],
            "fabricated_evidence": False,
            "note": "Place genuine MT5/Exness demo History Deals CSV exports in exports/genuine/",
        }

    SCHEMA_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    imports = []
    totals = {"ingested": 0, "duplicates": 0, "quarantined": 0, "rejected_wrong_symbol": 0}
    for path in files:
        disc = discover_csv_headers(path)
        write_json(SCHEMA_SAMPLES_DIR / f"headers_{path.stem}.json", disc)
        if not disc["mappable"]:
            imports.append({"path": str(path), "status": "SCHEMA_INCOMPLETE", "discovery": disc})
            continue
        cmap = build_column_map(disc)
        # Merge with defaults for optional cols present
        for k, v in DEFAULT_CSV_COLUMN_MAP.items():
            if k in disc["headers"] and k not in cmap:
                cmap[k] = v
        stats = import_csv(
            store,
            path,
            column_map=cmap,
            platform=platform,
            pseudonymous_account_ref=pseudonymous_account_ref,
        )
        # Post-filter: quarantine wrong symbol if any slipped (importer doesn't filter symbol)
        for row in list(store.all_normalized()):
            sym = row.get("symbol")
            if sym is not None and str(sym).strip() != expected_symbol:
                # Already ingested — mark via quarantine copy; cannot delete append-only
                store.quarantine(row, "wrong_symbol_for_configured_account")
                totals["rejected_wrong_symbol"] += 1
        imports.append({"path": str(path), "status": "IMPORTED", "discovery": disc, "stats": stats})
        totals["ingested"] += int(stats.get("ingested") or 0)
        totals["duplicates"] += int(stats.get("duplicates") or 0)
        totals["quarantined"] += int(stats.get("quarantined") or 0)

    out = {
        "status": "IMPORTED" if totals["ingested"] or totals["duplicates"] else "NO_ROWS_INGESTED",
        "exports_dir": str(EXPORTS_DIR),
        "n_files": len(files),
        "imports": imports,
        "totals": totals,
        "expected_symbol": expected_symbol,
        "expected_environment": expected_environment,
        "fabricated_evidence": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
