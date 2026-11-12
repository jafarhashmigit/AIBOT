"""Read-only discovery & inspection of genuine MT5 exports (CSV + XLSX)."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from phase64_5.constants import (
    ACTIVE_SYMBOL,
    PARSER_VERSION,
    PHASE63_EXPORTS_DIR,
    EXPORTS_DIR,
    file_sha256,
    canonical_json_sha256,
)
from phase64_5.formats import MT5_DEALS_CSV_HEADERS, REQUIRED_DEAL_CSV, SIDE_HEADERS
from phase64_5.xlsx_reader import read_xlsx_rows


def discovery_roots() -> list[Path]:
    roots = []
    for p in (EXPORTS_DIR, PHASE63_EXPORTS_DIR):
        p.mkdir(parents=True, exist_ok=True)
        roots.append(p)
    return roots


def list_export_files() -> list[Path]:
    files: list[Path] = []
    for root in discovery_roots():
        for pat in ("*.csv", "*.CSV", "*.xlsx", "*.XLSX"):
            for p in root.glob(pat):
                name = p.name
                if name.startswith("~$"):
                    continue
                files.append(p)
    # unique by resolved path
    seen = set()
    out = []
    for p in sorted(files):
        r = str(p.resolve())
        if r not in seen:
            seen.add(r)
            out.append(p)
    return out


def inspect_csv(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    mapped = {h: MT5_DEALS_CSV_HEADERS[h] for h in headers if h in MT5_DEALS_CSV_HEADERS}
    unmapped = [h for h in headers if h not in MT5_DEALS_CSV_HEADERS]
    missing = sorted(REQUIRED_DEAL_CSV - set(headers))
    has_side = bool(set(headers) & SIDE_HEADERS)
    if not has_side:
        missing.append("Direction|Type")
    return {
        "path": str(path),
        "format": "MT5_HISTORY_DEALS_CSV_V1",
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
        "headers": headers,
        "mapped": mapped,
        "unmapped": unmapped,
        "missing_critical_headers": missing,
        "mappable": len(missing) == 0,
        "timezone_provenance": "UNKNOWN",
        "parser_version": PARSER_VERSION,
        "rejected_reason": None if len(missing) == 0 else "unsupported_or_incomplete_headers",
    }


def _find_section_header(rows: list[list[Any]], marker: str) -> int | None:
    for i, row in enumerate(rows):
        if row and row[0] == marker:
            return i
    return None


def inspect_xlsx_trade_history(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    parsed = read_xlsx_rows(path)
    if not parsed.get("ok"):
        return {
            "path": str(path),
            "format": "UNSUPPORTED_XLSX",
            "sha256": file_sha256(path),
            "mappable": False,
            "rejected_reason": parsed.get("error"),
        }
    rows = parsed["rows"]
    account_label = None
    company = None
    export_date = None
    for row in rows[:10]:
        if not row:
            continue
        if row[0] == "Account:" and len(row) > 3:
            account_label = row[3]
        if row[0] == "Company:" and len(row) > 3:
            company = row[3]
        if row[0] == "Date:" and len(row) > 3:
            export_date = row[3]

    deals_i = _find_section_header(rows, "Deals")
    positions_i = _find_section_header(rows, "Positions")
    orders_i = _find_section_header(rows, "Orders")
    results_i = _find_section_header(rows, "Results")

    deals_header = None
    deal_data_rows: list[list[Any]] = []
    balance_rows = 0
    trade_deal_rows = 0
    if deals_i is not None and deals_i + 1 < len(rows):
        deals_header = [c for c in rows[deals_i + 1] if c is not None]
        end = results_i if results_i is not None else len(rows)
        for row in rows[deals_i + 2 : end]:
            if not row or all(c is None for c in row):
                continue
            if row[0] in ("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results"):
                break
            # skip summary continuation rows without Time
            if row[0] is None and (len(row) < 2 or row[1] is None):
                continue
            typ = str(row[3]).lower() if len(row) > 3 and row[3] is not None else ""
            if typ == "balance":
                balance_rows += 1
                deal_data_rows.append(row)
            elif row[0] is not None:
                trade_deal_rows += 1
                deal_data_rows.append(row)

    pos_data = 0
    if positions_i is not None and orders_i is not None:
        # data between positions header+1 and orders marker
        for row in rows[positions_i + 2 : orders_i]:
            if row and row[0] not in (None, "Orders") and row[0] != "Time":
                pos_data += 1

    ord_data = 0
    if orders_i is not None and deals_i is not None:
        for row in rows[orders_i + 2 : deals_i]:
            if row and row[0] not in (None, "Deals") and row[0] != "Open Time":
                ord_data += 1

    # Parse account login / server from label if present
    login = None
    server = None
    env = None
    if account_label:
        m = re.match(r"(\d+)\s*\(([^)]*)\)", str(account_label))
        if m:
            login = m.group(1)
            parts = m.group(2)
            if "Exness-" in parts or "MT5" in parts:
                # e.g. USD, Exness-MT5Trial15, demo, Hedge
                segs = [s.strip() for s in parts.split(",")]
                for s in segs:
                    if s.lower().startswith("exness-") or "MT5" in s:
                        server = s
                    if s.lower() in ("demo", "real", "live"):
                        env = s.lower()

    mappable = deals_header is not None and "Deal" in (deals_header or [])
    return {
        "path": str(path),
        "format": "MT5_TRADE_HISTORY_REPORT_XLSX_V1",
        "sha256": file_sha256(path),
        "size_bytes": len(raw),
        "account_label_observed": account_label,
        "account_login_observed": login,
        "broker_server_observed": server,
        "environment_observed": env,
        "company_observed": company,
        "export_date_observed": export_date,
        "deals_header": deals_header,
        "positions_data_rows": pos_data,
        "orders_data_rows": ord_data,
        "trade_deal_rows": trade_deal_rows,
        "balance_only_rows": balance_rows,
        "xauusdm_trade_deals": 0,  # filled during import if any Symbol==XAUUSDm
        "mappable": mappable,
        "timezone_provenance": "UNKNOWN",
        "parser_version": PARSER_VERSION,
        "rejected_reason": None if mappable else "xlsx_deals_header_missing",
        "active_symbol_expected": ACTIVE_SYMBOL,
        "deal_data_row_count": len(deal_data_rows),
        "_deal_data_rows": deal_data_rows,  # internal for importer
        "_deals_header": deals_header,
    }


def inspect_export(path: Path) -> dict[str, Any]:
    suf = path.suffix.lower()
    if suf == ".csv":
        return inspect_csv(path)
    if suf == ".xlsx":
        return inspect_xlsx_trade_history(path)
    return {
        "path": str(path),
        "format": "UNSUPPORTED",
        "sha256": file_sha256(path),
        "mappable": False,
        "rejected_reason": f"unsupported_extension:{suf}",
    }


def discover_all() -> dict[str, Any]:
    files = list_export_files()
    inspections = []
    for p in files:
        insp = inspect_export(p)
        # strip internal keys for report copy
        public = {k: v for k, v in insp.items() if not k.startswith("_")}
        inspections.append(public)
    accepted = [i for i in inspections if i.get("mappable")]
    rejected = [i for i in inspections if not i.get("mappable")]
    out = {
        "roots": [str(r) for r in discovery_roots()],
        "n_source_files_discovered": len(files),
        "n_accepted_for_parse": len(accepted),
        "n_rejected": len(rejected),
        "inspections": inspections,
        "paths": [str(p) for p in files],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
