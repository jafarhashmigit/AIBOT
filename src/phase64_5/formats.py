"""Supported export format specification — reject ambiguous mappings."""

from __future__ import annotations

from typing import Any

from phase64_5.constants import PARSER_VERSION, canonical_json_sha256

# MT5 History → Deals CSV header candidates (must inspect before mapping)
MT5_DEALS_CSV_HEADERS = {
    "Deal": "broker_deal_id",
    "Order": "broker_order_id",
    "Position": "broker_position_id",
    "Symbol": "symbol",
    "Type": "type_or_side",
    "Direction": "direction",
    "Volume": "volume",
    "Price": "price",
    "Order price": "requested_price",
    "Time": "timestamp_raw",
    "Time (Server)": "timestamp_raw",
    "Commission": "commission",
    "Swap": "swap",
    "Profit": "profit",
    "Fee": "fee",
    "Comment": "comment",
    "Entry": "entry_exit",
    "Magic": "magic",
}

REQUIRED_DEAL_CSV = frozenset({"Deal", "Symbol", "Price", "Time", "Volume"})
SIDE_HEADERS = frozenset({"Direction", "Type"})

# MT5 Trade History Report XLSX section markers
XLSX_SECTION_MARKERS = ("Positions", "Orders", "Deals", "Results")


def supported_format_specification() -> dict[str, Any]:
    return {
        "parser_version": PARSER_VERSION,
        "formats": [
            {
                "id": "MT5_HISTORY_DEALS_CSV_V1",
                "extensions": [".csv", ".CSV"],
                "description": "MetaTrader 5 History → Deals CSV export",
                "required_headers": sorted(REQUIRED_DEAL_CSV),
                "side_header_alternatives": sorted(SIDE_HEADERS),
                "optional_headers": sorted(set(MT5_DEALS_CSV_HEADERS) - REQUIRED_DEAL_CSV - SIDE_HEADERS),
                "header_map_candidates": dict(MT5_DEALS_CSV_HEADERS),
                "reject_if": [
                    "missing critical headers",
                    "ambiguous unmapped critical columns",
                    "balance-only rows presented as deals without Type=balance explicit",
                ],
                "timezone": "Preserve raw timestamp string; timezone_provenance=UNKNOWN unless export documents TZ",
            },
            {
                "id": "MT5_TRADE_HISTORY_REPORT_XLSX_V1",
                "extensions": [".xlsx", ".XLSX"],
                "description": "MetaTrader 5 Trade History Report workbook (OOXML)",
                "sections": list(XLSX_SECTION_MARKERS),
                "deals_header_row_marker": "Deals",
                "balance_row_type": "balance",
                "reject_if": [
                    "Excel lock temp (~$*)",
                    "unsupported workbook layout without Deals header",
                ],
                "note": "Empty Positions/Orders with balance-only Deals → 0 trade evidence",
            },
        ],
        "unsupported": [
            "HTML reports",
            "PDF",
            "undocumented column renames without inspection",
            "silent XAUUSD→XAUUSDm remapping",
        ],
        "missing_values_policy": "Never coerce blank/missing to zero; use null/UNKNOWN",
        "synthetic_policy": "SIMULATED_FIXTURE only; never import unmarked synthetic into genuine store",
    }


def audit_formats() -> dict[str, Any]:
    spec = supported_format_specification()
    out = {"specification": spec, "pass": len(spec["formats"]) == 2}
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
