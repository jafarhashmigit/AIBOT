"""Deterministic adversarial checks for Phase 66."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase64_13.schedule import state_at_utc
from phase66.collector import collect_fixture_cycle, collect_once
from phase66.constants import (
    ACTIVE_SYMBOL,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_OBSERVED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    SUPERSEDED_SYMBOL,
    SYNTHETIC_TEST_FIXTURE,
    canonical_json_sha256,
)
from phase66.eligibility import build_eligibility_registry
from phase66.integrity import audit_integrity
from phase66.quality import validate_m5_bar, validate_quote
from phase66.schema import build_quote_record, stable_evidence_id, to_pkt
from phase66.security import security_audit
from phase66.watermark import load_watermark, save_watermark


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    # Stable identity
    a = stable_evidence_id(kind="quote", symbol=ACTIVE_SYMBOL, server_ts="2026-01-01T00:00:00Z", payload_key="1|2|1")
    b = stable_evidence_id(kind="quote", symbol=ACTIVE_SYMBOL, server_ts="2026-01-01T00:00:00Z", payload_key="1|2|1")
    add("stable_evidence_identity", a == b and a.startswith("ev_"))

    # UTC/PKT
    pkt = to_pkt("2026-11-12T06:00:00Z")
    add("utc_pkt_conversion", "+05:00" in pkt or "05:00" in pkt)

    # Quality gates
    bad = validate_quote(
        symbol=ACTIVE_SYMBOL,
        bid=10.0,
        ask=9.0,
        server_time_utc="2026-01-01T00:00:00Z",
        collection_time_utc="2026-01-01T00:00:01Z",
    )
    add("invalid_bid_ask_rejected", bad["validation_status"] == "REJECTED" and "bid_greater_than_ask" in bad["rejection_reasons"])

    stale = validate_quote(
        symbol=ACTIVE_SYMBOL,
        bid=2650.0,
        ask=2650.2,
        server_time_utc="2020-01-01T00:00:00Z",
        collection_time_utc="2026-01-01T00:00:00Z",
    )
    add("stale_observation_rejected", "stale_observation" in stale["rejection_reasons"])

    inc = validate_m5_bar({"open": 1, "high": 2, "low": 0.5, "close": 3, "timestamp_utc": "2026-01-01T00:00:00Z"})
    add("incomplete_or_inconsistent_candle", inc["validation_status"] == "REJECTED")

    # Fixture collection + duplicate + watermark
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "fixture_j"
        fx = collect_fixture_cycle(journal_root=root, rounds=2)
        add("fixture_collection_ok", fx["rounds"][0]["status"] == "OK" and fx["n_events"] >= 1)
        add("duplicate_ingestion_suppressed", bool(fx.get("idempotent_second_round_duplicates")))
        wm = load_watermark(root / "watermark.json")
        add("watermark_persisted", wm.get("last_quote_server_ts") is not None or wm.get("last_m5_server_ts") is not None)

        # Synthetic blocked from genuine store
        genuine = BrokerEvidenceJournal(Path(td) / "genuine", allow_synthetic=False, store_label="GENUINE")
        q = build_quote_record(
            bid=2650.0,
            ask=2650.2,
            server_time_utc="2026-01-01T00:00:00Z",
            collection_time_utc="2026-01-01T00:00:01Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class=SYNTHETIC_TEST_FIXTURE,
            raw_payload={},
        )
        batch = genuine.begin_batch(source_file="adv", source_sha256="x", parser_version="t")
        res = genuine.append_event(q, import_batch_id=batch)
        add("synthetic_blocked_from_genuine", res.get("status") == "QUARANTINED")

        # Wrong symbol fail-closed
        backend = FakeMt5Backend()
        j = BrokerEvidenceJournal(Path(td) / "j2", allow_synthetic=True, store_label="FIXTURE")
        blocked = collect_once(backend, j, symbol=SUPERSEDED_SYMBOL, synthetic=True, watermark_path=Path(td) / "wm2.json")
        add("wrong_symbol_fail_closed", blocked.get("status") == "BLOCKED")

        # Disconnect
        backend2 = FakeMt5Backend()
        backend2.connected = False
        disc = collect_once(backend2, j, synthetic=True, watermark_path=Path(td) / "wm3.json")
        add("disconnect_suspends_collection", disc.get("status") == "BLOCKED")

        # Wrong server
        backend3 = FakeMt5Backend()
        backend3.account = {**backend3.account, "server": "Wrong-Server"}
        ws = collect_once(backend3, j, synthetic=True, watermark_path=Path(td) / "wm4.json")
        add("wrong_server_fail_closed", ws.get("status") == "BLOCKED")

    # Session distinctions
    co = state_at_utc(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
    add("session_close_only_distinct", co["state"] == "CLOSE_ONLY")

    elig = build_eligibility_registry()
    add("sealed_holdout_protection", elig["phase58_holdout_accessed"] is False and len(elig["phase58_holdout_sealed"]) == 10)
    add("independent_evidence_not_claimed_sufficient", elig["independent_research_evidence_sufficient"] is False)

    integ = audit_integrity()
    add("integrity_checks", integ["checks_pass"])
    add("champion_NO_MODEL", CHAMPION_STATUS == "NO_MODEL" == integ["champion"])
    add("production_WAIT", PRODUCTION_FINAL_ACTION == "WAIT")

    sec = security_audit()
    add("security_audit_pass", sec["pass"])
    add("order_send_prohibited", ORDER_SEND == "PROHIBITED" and "order_send" in PROHIBITED_MT5_API)
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False and BROKER_EXECUTION_AUTHORIZED is False)

    # Classes never mixed in builders
    add("evidence_classes_distinct", BROKER_OBSERVED != SYNTHETIC_TEST_FIXTURE)

    # Watermark save/load roundtrip
    with tempfile.TemporaryDirectory() as td2:
        p = Path(td2) / "wm.json"
        save_watermark({"last_quote_server_ts": "2026-01-01T00:00:00Z", "n_quotes": 1}, p)
        add("watermark_roundtrip", load_watermark(p).get("n_quotes") == 1)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
