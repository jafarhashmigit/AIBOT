"""Adversarial import tests — temp stores only; never pollute genuine evidence."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase62.importers import import_csv, import_json_records
from phase62.store import ExecutionStore
from phase63.constants import canonical_json_sha256
from phase63.import_pipeline import discover_csv_headers


def run_adversarial_import_tests() -> dict[str, Any]:
    results = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1) Valid-looking MT5 deals CSV (synthetic labeled) — temp only
        good = root / "good.csv"
        good.write_text(
            "Deal,Order,Position,Symbol,Direction,Volume,Price,Time,Commission,Swap,Profit,Fee\n"
            "7001,8001,9001,XAUUSD,buy,0.01,2650.50,2026.03.01 10:00:00,,,1.2,\n"
            "7002,8001,9001,XAUUSD,sell,0.01,2651.00,2026.03.01 11:00:00,,,0.5,\n",
            encoding="utf-8",
        )
        disc = discover_csv_headers(good)
        results.append({"name": "header_discovery", "pass": disc["mappable"] and "Deal" in disc["headers"]})

        store = ExecutionStore(root=root / "s1")
        s1 = import_csv(store, good, platform="MT5")
        s2 = import_csv(store, good, platform="MT5")
        results.append({"name": "idempotent_reimport", "pass": s1["ingested"] >= 2 and s2["duplicates"] >= 2})
        # Empty commission preserved null
        rows = store.all_normalized()
        results.append({"name": "missing_commission_null", "pass": any(r.get("commission") is None for r in rows)})

        # 2) Corrupt CSV
        bad = root / "bad.csv"
        bad.write_text("Deal,Symbol,Price,Time\nnot-a-number,XAUUSD,abc,not-a-date\n", encoding="utf-8")
        store2 = ExecutionStore(root=root / "s2")
        sb = import_csv(store2, bad, platform="MT5")
        results.append({"name": "corrupt_quarantine", "pass": sb["quarantined"] >= 1 and sb["ingested"] == 0})

        # 3) Wrong symbol
        wrong = root / "wrong.csv"
        wrong.write_text(
            "Deal,Order,Symbol,Direction,Volume,Price,Time\n"
            "1,2,EURUSD,buy,0.01,1.1,2026-03-01 10:00:00\n",
            encoding="utf-8",
        )
        store3 = ExecutionStore(root=root / "s3")
        import_csv(store3, wrong, platform="MT5")
        # Phase63 post-filter style check
        wrong_rows = [r for r in store3.all_normalized() if r.get("symbol") != "XAUUSD"]
        results.append({"name": "wrong_symbol_detectable", "pass": len(wrong_rows) == 1})

        # 4) Synthetic JSON blocked
        syn = root / "syn.json"
        syn.write_text(
            '{"synthetic": true, "records": [{"deal_id": "X", "record_kind": "DEAL", '
            '"actual_fill_price": 1, "synthetic": true, "source_provenance": "t"}]}',
            encoding="utf-8",
        )
        store4 = ExecutionStore(root=root / "s4")
        sj = import_json_records(store4, syn, allow_synthetic=False)
        results.append({"name": "synthetic_blocked", "pass": sj["ingested"] == 0 and sj["quarantined"] >= 1})

        # 5) Live environment quarantine
        store5 = ExecutionStore(root=root / "s5")
        r = store5.ingest_normalized(
            {
                "broker": "Exness",
                "environment": "LIVE",
                "deal_id": "L",
                "record_kind": "DEAL",
                "actual_fill_price": 1.0,
                "source_provenance": "t",
                "synthetic": False,
            }
        )
        results.append({"name": "live_rejected", "pass": r["status"] == "QUARANTINED"})

        # 6) Conflict quarantine
        store6 = ExecutionStore(root=root / "s6")
        a = {
            "broker": "Exness",
            "environment": "DEMO",
            "deal_id": "C1",
            "record_kind": "DEAL",
            "actual_fill_price": 1.0,
            "volume": 0.01,
            "side": "BUY",
            "fill_timestamp_utc": "2026-01-01 00:00:00",
            "source_provenance": "t",
            "synthetic": False,
        }
        store6.ingest_normalized(a)
        c = store6.ingest_normalized({**a, "actual_fill_price": 9.0})
        results.append({"name": "conflict_quarantine", "pass": c["status"] == "QUARANTINED"})

    out = {
        "results": results,
        "n": len(results),
        "n_pass": sum(1 for r in results if r.get("pass")),
        "pass": all(r.get("pass") for r in results),
        "label": "TEMP_ADVERSARIAL_ONLY_NOT_GENUINE_EVIDENCE",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
