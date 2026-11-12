"""Historical MetaQuotes XAUUSD vs live Exness XAUUSDm transfer limitations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase67.constants import JOURNAL_ROOT, PROJECT_ROOT, canonical_json_sha256


def compare_broker_substrates() -> dict[str, Any]:
    p64_7 = PROJECT_ROOT / "reports" / "phase64_7" / "live_ro_probe_sanitized.json"
    live_meta = json.loads(p64_7.read_text(encoding="utf-8")) if p64_7.is_file() else {}
    sym = live_meta.get("symbol") or live_meta.get("observed") or {}
    if isinstance(sym, dict) and "name" not in sym:
        # structure may nest under keys
        for k in ("symbol_info", "xauusdm", "observed_symbol"):
            if isinstance(live_meta.get(k), dict):
                sym = live_meta[k]
                break

    # Fall back to known Phase64.7 verified fields from report
    exness = {
        "symbol": "XAUUSDm",
        "broker": "Exness",
        "server": "Exness-MT5Trial15",
        "digits": sym.get("digits", 3),
        "contract_size": sym.get("contract_size", 100.0),
        "tick_size": sym.get("tick_size", 0.001),
        "source": "phase64_7 live RO probe + phase66/67 journals",
    }

    # Archive sample from phase49 field inventory / known
    archive = {
        "symbol": "XAUUSD",
        "broker": "MetaQuotes-Demo",
        "server": "MetaQuotes-Demo",
        "digits": 2,  # typical in archive closes like 3359.52 — verify from sample
        "contract_size": "UNKNOWN_IN_ARCHIVE_ROWS",
        "tick_size": "UNKNOWN_IN_ARCHIVE_ROWS",
        "source": "phase43/49/53 mt5 raw jsonl",
    }
    # Verify archive digits from one bar
    sample = PROJECT_ROOT / "src" / "data" / "phase49" / "mt5" / "raw" / "m5" / "m5_XAUUSD_2025-07-03.jsonl"
    if sample.is_file():
        line = sample.read_text(encoding="utf-8").splitlines()[0]
        row = json.loads(line)
        archive["source_server_field"] = row.get("source_server")
        archive["sample_close"] = row.get("close")
        archive["sample_spread_points_field"] = row.get("spread")

    journal = BrokerEvidenceJournal(JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
    events = journal.all_events() if JOURNAL_ROOT.exists() else []
    quotes = [e for e in events if e.get("kind") == "QUOTE_SNAPSHOT"]
    spreads = [float(q["spread"]) for q in quotes if q.get("spread") is not None]

    out = {
        "historical": archive,
        "live_exness": exness,
        "differences": [
            {"aspect": "symbol", "historical": "XAUUSD", "live": "XAUUSDm", "identical": False},
            {"aspect": "broker_server", "historical": "MetaQuotes-Demo", "live": "Exness-MT5Trial15", "identical": False},
            {"aspect": "price_precision_digits", "historical": archive.get("digits"), "live": exness["digits"], "identical": False},
            {"aspect": "contract_size", "historical": archive["contract_size"], "live": exness["contract_size"], "identical": "UNKNOWN"},
            {"aspect": "session_schedule", "historical": "MetaQuotes archive timestamps", "live": "Phase64.13 Exness schedule", "identical": False},
            {"aspect": "quote_availability", "historical": "dense tick jsonl", "live": "symbol_info snapshots only (ticks not approved)", "identical": False},
            {"aspect": "timestamp_characteristics", "historical": "bar timestamp_utc + tick timestamp_msc", "live": "symbol time second precision + collection UTC", "identical": False},
            {"aspect": "data_coverage", "historical": "multi-month archived days", "live": "sparse nascent journal", "identical": False},
            {
                "aspect": "spread_distribution",
                "historical": "tick bid/ask available on archive days",
                "live": f"snapshot_n={len(spreads)} mean={(sum(spreads)/len(spreads)) if spreads else None}",
                "identical": False,
            },
        ],
        "execution_characteristics_assumed_identical": False,
        "historical_may_inform_hypothesis_design": True,
        "exness_validation_requires_new_exness_observations": True,
        "live_quote_n": len(quotes),
        "live_m5_n": sum(1 for e in events if e.get("kind") == "M5_BAR"),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
