"""Adversarial checks for Phase 69."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase65.consumption import build_consumption_registry
from phase66.collector import collect_once
from phase69.accounting import build_live_evidence_accounting
from phase69.constants import (
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_OBSERVED_LIVE_BAR,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    HISTORICAL_BACKFILL,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    REGISTRY_PATH,
    canonical_json_sha256,
)
from phase69.integrity import audit_integrity
from phase69.provenance import classify_record
from phase69.registry import build_and_freeze_registry, load_registry
from phase69.security import security_audit
from phase69.sufficiency import build_sufficiency_report


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    cons = build_consumption_registry()
    add("holdout_sealed", cons["phase58_holdout_opened"] is False and len(cons["phase58_holdout_sealed"]) == 10)

    # Backfill vs live classification
    started = "2026-11-12T12:00:00Z"
    backfill_rec = {
        "kind": "M5_BAR",
        "server_timestamp_utc": "2026-11-12T10:00:00Z",
        "collection_timestamp_utc": "2026-11-12T12:00:05Z",
        "synthetic": False,
        "source_classification": "BROKER_OBSERVED",
    }
    live_rec = {
        "kind": "M5_BAR",
        "server_timestamp_utc": "2026-11-12T12:00:00Z",
        "collection_timestamp_utc": "2026-11-12T12:05:10Z",
        "synthetic": False,
        "source_classification": "BROKER_OBSERVED",
    }
    add(
        "backfill_never_counted_as_live",
        classify_record(backfill_rec, collector_started_utc=started, collector_ended_utc="2026-11-12T12:10:00Z")
        == HISTORICAL_BACKFILL,
    )
    add(
        "newly_closed_live_bar",
        classify_record(live_rec, collector_started_utc=started, collector_ended_utc="2026-11-12T12:10:00Z")
        == BROKER_OBSERVED_LIVE_BAR,
    )

    # Duplicate idempotency + synthetic isolation
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        j = BrokerEvidenceJournal(root / "g", allow_synthetic=False, store_label="GENUINE")
        backend = FakeMt5Backend()
        now = int(datetime.now(timezone.utc).timestamp())
        backend.symbol = {
            **(backend.symbol or {}),
            "name": "XAUUSDm",
            "bid": 2650.1,
            "ask": 2650.35,
            "time": now,
            "point": 0.001,
            "trade_tick_size": 0.001,
        }
        # Old bar = backfill
        old = now - 3600
        backend.rates = [
            {
                "time": old,
                "open": 2649.0,
                "high": 2651.0,
                "low": 2648.5,
                "close": 2650.0,
                "tick_volume": 100,
                "spread": 25,
                "timestamp_utc": datetime.fromtimestamp(old, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
        started_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r1 = collect_once(
            backend, j, synthetic=False, watermark_path=root / "w.json", m5_count=1, collector_started_utc=started_utc, collector_cycle=1
        )
        r2 = collect_once(
            backend, j, synthetic=False, watermark_path=root / "w.json", m5_count=1, collector_started_utc=started_utc, collector_cycle=2
        )
        add("collect_ok", r1.get("status") == "OK")
        add("duplicate_idempotent", (r2.get("stats") or {}).get("DUPLICATE_SUPPRESSED", 0) > 0)
        events = j.all_events()
        m5s = [e for e in events if e.get("kind") == "M5_BAR"]
        add("m5_stamped_backfill", all(e.get("evidence_provenance") == HISTORICAL_BACKFILL for e in m5s) if m5s else False)
        quotes = [e for e in events if e.get("kind") == "QUOTE_SNAPSHOT"]
        add("quote_bar_separation", len(quotes) >= 1 and len(m5s) >= 1)
        # synthetic into genuine
        from phase66.schema import build_quote_record
        from phase66.constants import SYNTHETIC_TEST_FIXTURE

        q = build_quote_record(
            bid=1.0,
            ask=1.1,
            server_time_utc="2026-01-01T00:00:00Z",
            collection_time_utc="2026-01-01T00:00:01Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class=SYNTHETIC_TEST_FIXTURE,
            raw_payload={},
        )
        b = j.begin_batch(source_file="t", source_sha256="x", parser_version="t")
        add("synthetic_blocked", j.append_event(q, import_batch_id=b)["status"] == "QUARANTINED")

    acc = build_live_evidence_accounting()
    add("accounting_excludes_backfill_from_live_unique", acc["backfill_never_counted_as_live"] is True)
    add("no_second_journal", acc["second_journal_created"] is False)
    suf = build_sufficiency_report(acc)
    add("not_edge_validated", suf["trading_edge_validated"] is False)

    reg = build_and_freeze_registry()
    reg2 = load_registry()
    add("registry_frozen", reg.get("frozen_before_evaluation") is True)
    add("registry_immutable_hash", reg.get("registry_sha256") == reg2.get("registry_sha256"))
    add("registry_file_exists", REGISTRY_PATH.is_file())
    add("hypotheses_unvalidated", all(h["status"].startswith("PREREGISTERED_UNVALIDATED") for h in reg["hypotheses"]))

    add("security", security_audit()["pass"])
    add("integrity", audit_integrity()["checks_pass"])
    add("champion", CHAMPION_STATUS == "NO_MODEL")
    add("wait", PRODUCTION_FINAL_ACTION == "WAIT")
    add("order_send", ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API)
    add("auth_blocked", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
