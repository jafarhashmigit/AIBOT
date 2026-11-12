"""Read-only import workflow for genuine + labeled simulated exports."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from phase64_5.constants import (
    ACTIVE_SYMBOL,
    PARSER_VERSION,
    SIMULATED_LABEL,
    SUPERSEDED_SYMBOL,
    canonical_json_sha256,
    file_sha256,
)
from phase64_5.export_discovery import discover_all, inspect_csv, inspect_xlsx_trade_history, list_export_files
from phase64_5.formats import MT5_DEALS_CSV_HEADERS
from phase64_5.journal import BrokerEvidenceJournal
from phase64_5.normalize import (
    normalize_balance_row,
    normalize_deal_row,
    normalize_fee_from_deal,
    normalize_order_row,
)


def _map_csv_row(raw: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    mapped = {}
    for src, dst in column_map.items():
        if src in raw:
            mapped[dst] = raw[src]
    return mapped


def import_csv_file(
    journal: BrokerEvidenceJournal,
    path: Path,
    *,
    synthetic: bool = False,
    evidence_label: str | None = None,
    expected_symbol: str = ACTIVE_SYMBOL,
    expected_server: str | None = None,
    expected_account_login: str | None = None,
) -> dict[str, Any]:
    disc = inspect_csv(path)
    if not disc["mappable"]:
        return {"status": "REJECTED", "reason": disc.get("rejected_reason"), "discovery": disc}

    content = path.read_bytes()
    raw_meta = journal.save_raw_bytes(
        source_name=path.name,
        content=content,
        provenance=f"csv_import:{path.name}",
    )
    batch_id = journal.begin_batch(
        source_file=str(path),
        source_sha256=raw_meta["sha256"],
        parser_version=PARSER_VERSION,
    )
    cmap = dict(disc["mapped"])
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    stats = {
        "ingested": 0,
        "duplicates": 0,
        "quarantined": 0,
        "balance_ops": 0,
        "deals": 0,
        "orders": 0,
        "fees": 0,
        "rejected_wrong_symbol": 0,
        "rows": 0,
    }
    provenance = {
        "source_file": str(path),
        "source_file_sha256": raw_meta["sha256"],
        "parser_version": PARSER_VERSION,
        "import_batch_id": batch_id,
        "synthetic": synthetic,
        "evidence_label": evidence_label or (SIMULATED_LABEL if synthetic else "GENUINE"),
        "broker_server": expected_server,
        "account_login": expected_account_login,
        "timezone_provenance": "UNKNOWN",
    }

    # Account/server gates when expected provided
    if expected_server is not None and provenance.get("broker_server") not in (None, expected_server):
        return {"status": "REJECTED", "reason": "wrong_broker_server", "discovery": disc}
    if expected_account_login is not None and provenance.get("account_login") not in (None, expected_account_login):
        # CSV may not carry account — if expected set but file has none, don't invent match
        pass

    for row in reader:
        stats["rows"] += 1
        mapped = _map_csv_row(row, cmap)
        typ = str(mapped.get("type_or_side") or "").strip().lower()
        if typ == "balance":
            rec, err = normalize_balance_row(mapped, provenance=provenance)
            if err:
                journal.quarantine({"raw": row, "error": err}, err)
                stats["quarantined"] += 1
                continue
            assert rec is not None
            res = journal.append_event(rec, import_batch_id=batch_id)
            if res["status"] == "INGESTED":
                stats["ingested"] += 1
                stats["balance_ops"] += 1
            elif res["status"] == "DUPLICATE_SUPPRESSED":
                stats["duplicates"] += 1
            else:
                stats["quarantined"] += 1
            continue

        # Deal path
        sym = mapped.get("symbol")
        if sym is not None and str(sym).strip() == SUPERSEDED_SYMBOL:
            journal.quarantine({"raw": row, "error": "superseded_symbol"}, "superseded_symbol_xauusd")
            stats["quarantined"] += 1
            stats["rejected_wrong_symbol"] += 1
            continue
        if sym is not None and str(sym).strip() and str(sym).strip() != expected_symbol:
            journal.quarantine({"raw": row, "error": "wrong_symbol"}, "wrong_symbol")
            stats["quarantined"] += 1
            stats["rejected_wrong_symbol"] += 1
            continue

        rec, err = normalize_deal_row(mapped, provenance=provenance)
        if err:
            journal.quarantine({"raw": row, "error": err}, err)
            stats["quarantined"] += 1
            continue
        assert rec is not None
        res = journal.append_event(rec, import_batch_id=batch_id)
        if res["status"] == "INGESTED":
            stats["ingested"] += 1
            stats["deals"] += 1
            fee = normalize_fee_from_deal(rec)
            if fee:
                fres = journal.append_event(fee, import_batch_id=batch_id)
                if fres["status"] == "INGESTED":
                    stats["fees"] += 1
                    stats["ingested"] += 1
                elif fres["status"] == "DUPLICATE_SUPPRESSED":
                    stats["duplicates"] += 1
        elif res["status"] == "DUPLICATE_SUPPRESSED":
            stats["duplicates"] += 1
        else:
            stats["quarantined"] += 1

    return {
        "status": "IMPORTED",
        "batch_id": batch_id,
        "discovery": {k: v for k, v in disc.items() if not str(k).startswith("_")},
        "raw": raw_meta,
        "stats": stats,
        "synthetic": synthetic,
        "evidence_label": provenance["evidence_label"],
    }


def import_xlsx_file(
    journal: BrokerEvidenceJournal,
    path: Path,
    *,
    synthetic: bool = False,
    evidence_label: str | None = None,
    expected_symbol: str = ACTIVE_SYMBOL,
    expected_server: str | None = None,
    expected_account_login: str | None = None,
) -> dict[str, Any]:
    disc = inspect_xlsx_trade_history(path)
    if not disc.get("mappable"):
        return {"status": "REJECTED", "reason": disc.get("rejected_reason"), "discovery": {k: v for k, v in disc.items() if not k.startswith("_")}}

    # Server / account checks when expected provided
    if expected_server is not None and disc.get("broker_server_observed") not in (None, expected_server):
        return {
            "status": "REJECTED",
            "reason": "wrong_broker_server",
            "discovery": {k: v for k, v in disc.items() if not k.startswith("_")},
        }
    if expected_account_login is not None and disc.get("account_login_observed") not in (None, expected_account_login):
        return {
            "status": "REJECTED",
            "reason": "wrong_or_missing_account_identity",
            "discovery": {k: v for k, v in disc.items() if not k.startswith("_")},
        }

    content = path.read_bytes()
    raw_meta = journal.save_raw_bytes(
        source_name=path.name,
        content=content,
        provenance=f"xlsx_import:{path.name}",
    )
    batch_id = journal.begin_batch(
        source_file=str(path),
        source_sha256=raw_meta["sha256"],
        parser_version=PARSER_VERSION,
    )
    header = disc.get("_deals_header") or []
    # Map header positions
    col = {name: i for i, name in enumerate(header)}
    stats = {
        "ingested": 0,
        "duplicates": 0,
        "quarantined": 0,
        "balance_ops": 0,
        "deals": 0,
        "orders": 0,
        "fees": 0,
        "rejected_wrong_symbol": 0,
        "rows": 0,
        "trade_deals_xauusdm": 0,
    }
    provenance = {
        "source_file": str(path),
        "source_file_sha256": raw_meta["sha256"],
        "parser_version": PARSER_VERSION,
        "import_batch_id": batch_id,
        "synthetic": synthetic,
        "evidence_label": evidence_label or (SIMULATED_LABEL if synthetic else "GENUINE"),
        "broker_server": disc.get("broker_server_observed"),
        "account_login": disc.get("account_login_observed"),
        "timezone_provenance": "UNKNOWN",
        "account_label": disc.get("account_label_observed"),
    }

    def cell(row: list[Any], name: str) -> Any:
        i = col.get(name)
        if i is None or i >= len(row):
            return None
        return row[i]

    for row in disc.get("_deal_data_rows") or []:
        stats["rows"] += 1
        mapped = {
            "broker_deal_id": cell(row, "Deal"),
            "broker_order_id": cell(row, "Order"),
            "symbol": cell(row, "Symbol"),
            "type_or_side": cell(row, "Type"),
            "direction": cell(row, "Direction"),
            "volume": cell(row, "Volume"),
            "price": cell(row, "Price"),
            "commission": cell(row, "Commission"),
            "fee": cell(row, "Fee"),
            "swap": cell(row, "Swap"),
            "profit": cell(row, "Profit"),
            "balance": cell(row, "Balance"),
            "comment": cell(row, "Comment"),
            "timestamp_raw": cell(row, "Time"),
        }
        typ = str(mapped.get("type_or_side") or "").strip().lower()
        if typ == "balance":
            # Do not invent a deal from balance
            rec, err = normalize_balance_row(mapped, provenance=provenance)
            if err:
                journal.quarantine({"raw": mapped, "error": err}, err)
                stats["quarantined"] += 1
                continue
            assert rec is not None
            res = journal.append_event(rec, import_batch_id=batch_id)
            if res["status"] == "INGESTED":
                stats["ingested"] += 1
                stats["balance_ops"] += 1
            elif res["status"] == "DUPLICATE_SUPPRESSED":
                stats["duplicates"] += 1
            else:
                stats["quarantined"] += 1
            continue

        sym = mapped.get("symbol")
        if sym is not None and str(sym).strip() == SUPERSEDED_SYMBOL:
            journal.quarantine({"raw": mapped}, "superseded_symbol_xauusd")
            stats["quarantined"] += 1
            stats["rejected_wrong_symbol"] += 1
            continue
        if sym is not None and str(sym).strip() and str(sym).strip() != expected_symbol:
            journal.quarantine({"raw": mapped}, "wrong_symbol")
            stats["quarantined"] += 1
            stats["rejected_wrong_symbol"] += 1
            continue

        rec, err = normalize_deal_row(mapped, provenance=provenance)
        if err:
            journal.quarantine({"raw": mapped, "error": err}, err)
            stats["quarantined"] += 1
            continue
        assert rec is not None
        res = journal.append_event(rec, import_batch_id=batch_id)
        if res["status"] == "INGESTED":
            stats["ingested"] += 1
            stats["deals"] += 1
            if rec.get("symbol") == expected_symbol:
                stats["trade_deals_xauusdm"] += 1
            fee = normalize_fee_from_deal(rec)
            if fee:
                fres = journal.append_event(fee, import_batch_id=batch_id)
                if fres["status"] == "INGESTED":
                    stats["fees"] += 1
                    stats["ingested"] += 1
        elif res["status"] == "DUPLICATE_SUPPRESSED":
            stats["duplicates"] += 1
        else:
            stats["quarantined"] += 1

    public_disc = {k: v for k, v in disc.items() if not k.startswith("_")}
    public_disc["xauusdm_trade_deals"] = stats["trade_deals_xauusdm"]
    return {
        "status": "IMPORTED",
        "batch_id": batch_id,
        "discovery": public_disc,
        "raw": raw_meta,
        "stats": stats,
        "synthetic": synthetic,
        "evidence_label": provenance["evidence_label"],
        "note": "Balance-only rows are BROKER_BALANCE_OPERATION, not fills",
    }


def import_genuine_exports(journal: BrokerEvidenceJournal) -> dict[str, Any]:
    """Import all discovered genuine exports into genuine journal."""
    files = list_export_files()
    discovery = discover_all()
    imports = []
    totals = {
        "ingested": 0,
        "duplicates": 0,
        "quarantined": 0,
        "balance_ops": 0,
        "deals": 0,
        "orders": 0,
        "fees": 0,
    }
    for path in files:
        if path.suffix.lower() == ".csv":
            res = import_csv_file(journal, path, synthetic=False)
        elif path.suffix.lower() == ".xlsx":
            res = import_xlsx_file(journal, path, synthetic=False)
        else:
            res = {"status": "REJECTED", "reason": "unsupported", "path": str(path)}
        imports.append(res)
        st = res.get("stats") or {}
        for k in totals:
            totals[k] += int(st.get(k) or 0)

    genuine_deals = sum(1 for e in journal.all_events() if e.get("record_kind") == "BROKER_DEAL" and not e.get("synthetic"))
    genuine_orders = sum(1 for e in journal.all_events() if e.get("record_kind") == "BROKER_ORDER" and not e.get("synthetic"))
    genuine_balance = sum(
        1 for e in journal.all_events() if e.get("record_kind") == "BROKER_BALANCE_OPERATION" and not e.get("synthetic")
    )
    genuine_fills = sum(
        1 for e in journal.all_events() if e.get("record_kind") == "BROKER_DEAL" and e.get("is_fill") and not e.get("synthetic")
    )

    status = "IMPORTED"
    if not files:
        status = "AWAITING_GENUINE_DEMO_EXPORT"
    elif genuine_deals == 0 and genuine_orders == 0:
        status = "GENUINE_FILES_PRESENT_ZERO_TRADE_DEALS"

    out = {
        "status": status,
        "discovery": discovery,
        "imports": [{k: v for k, v in r.items() if k != "discovery"} | {"discovery_format": (r.get("discovery") or {}).get("format")} for r in imports],
        "totals": totals,
        "counts": {
            "genuine_broker_orders": genuine_orders,
            "genuine_broker_deals": genuine_deals,
            "genuine_broker_fills": genuine_fills,
            "genuine_balance_operations": genuine_balance,
            "quarantined": len(journal.quarantine_rows()),
            "incidents": len(journal.incidents()),
        },
        "fabricated_evidence": False,
        "read_only": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def write_simulated_fixtures(dir_path: Path) -> dict[str, Any]:
    """Create clearly labeled SIMULATED_FIXTURE CSV files for parser tests."""
    dir_path.mkdir(parents=True, exist_ok=True)
    deals = dir_path / "simulated_xauusdm_deals.csv"
    deals.write_text(
        "\n".join(
            [
                "Deal,Order,Position,Symbol,Direction,Volume,Price,Time,Commission,Swap,Profit,Fee,Magic,Comment",
                "9001,8001,7001,XAUUSDm,buy,0.01,2650.120,2026-01-05 10:00:00,,,1.5,,4242,aibot_intent:INTENT_SIM_1",
                "9002,8001,7001,XAUUSDm,sell,0.01,2651.000,2026-01-05 11:00:00,0.0,0.0,0.8,0,4242,aibot_intent:INTENT_SIM_1",
                "9003,8002,7002,XAUUSDm,buy,0.02,2652.000,2026-01-05 12:00:00,,,,,4242,",
                "",
            ]
        ),
        encoding="utf-8",
    )
    balance = dir_path / "simulated_balance_only.csv"
    balance.write_text(
        "Deal,Order,Position,Symbol,Type,Direction,Volume,Price,Time,Commission,Swap,Profit,Fee,Comment\n"
        "9900,,,,balance,,, ,2026-01-01 00:00:00,,,500,,deposit\n",
        encoding="utf-8",
    )
    bad = dir_path / "simulated_unsupported_columns.csv"
    bad.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    wrong_sym = dir_path / "simulated_wrong_symbol.csv"
    wrong_sym.write_text(
        "Deal,Order,Position,Symbol,Direction,Volume,Price,Time,Commission,Swap,Profit,Fee\n"
        "9100,8100,7100,XAUUSD,buy,0.01,1900.0,2026-01-05 10:00:00,,,,\n",
        encoding="utf-8",
    )
    return {
        "deals": str(deals),
        "balance": str(balance),
        "unsupported": str(bad),
        "wrong_symbol": str(wrong_sym),
        "label": SIMULATED_LABEL,
        "sha256": {
            "deals": file_sha256(deals),
            "balance": file_sha256(balance),
            "unsupported": file_sha256(bad),
            "wrong_symbol": file_sha256(wrong_sym),
        },
    }
