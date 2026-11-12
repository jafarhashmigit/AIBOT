"""Deterministic adversarial checks for Phase 64.12."""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_12.applicability import build_applicability_matrix
from phase64_12.constants import (
    ACTIVE_SYMBOL,
    BASE_INSTRUMENT,
    BREAK,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSED,
    OPEN,
    ORDER_SEND,
    UNKNOWN,
    canonical_json_sha256,
)
from phase64_12.freshness import evaluate_conflict, freshness_policy, is_evidence_expired
from phase64_12.journal_ingest import ingest_conflicting_payload, ingest_session_evidence
from phase64_12.schedule import HOLIDAYS_2026, state_at_utc, us_dst_season
from phase64_12.session_model import build_session_model, lookup_session, session_aware_preflight
from phase64_12.sources import official_source_inventory


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    inv = official_source_inventory()
    add("official_source_provenance", inv["n_sources"] >= 4 and inv["third_party_used"] is False)
    add(
        "primary_sources_present",
        inv["primary_hour_source"] == "exness_dst_update_2026_11_01"
        and inv["primary_applicability_source"] == "exness_account_type_suffixes",
    )

    appl = build_applicability_matrix()
    add("exact_symbol_applicability", appl["applicability_justified"] is True)
    add(
        "generic_xauusd_vs_xauusdm",
        appl["published_hour_instrument"] == BASE_INSTRUMENT
        and appl["target_symbol"] == ACTIVE_SYMBOL
        and appl["not_xauusd247"] is True,
    )

    # Weekday / break / weekend — winter UTC (2026-11-10 Tue)
    tue_open = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
    add("weekday_schedule_open", tue_open["state"] == OPEN)
    tue_break = state_at_utc(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
    add("intraday_break_close_only", tue_break["state"] == BREAK)
    tue_gap = state_at_utc(datetime(2026, 11, 10, 22, 30, 0, tzinfo=timezone.utc))
    add("intraday_closed_gap", tue_gap["state"] == CLOSED)
    sat = state_at_utc(datetime(2026, 11, 14, 15, 0, 0, tzinfo=timezone.utc))
    add("weekend_closure", sat["state"] == CLOSED)

    # Midnight-crossing: Sun 23:10 open → Mon continues; Fri 22:00 closed
    sun_open = state_at_utc(datetime(2026, 11, 15, 23, 10, 0, tzinfo=timezone.utc))
    add("midnight_crossing_sunday_open", sun_open["state"] == OPEN)
    fri_closed = state_at_utc(datetime(2026, 11, 13, 22, 0, 0, tzinfo=timezone.utc))
    add("friday_evening_closed", fri_closed["state"] == CLOSED)

    # UTC / PKT
    pkt = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
    add("utc_conversion", "T12:00:00" in pkt["utc"] or pkt["utc"].endswith("+00:00"))
    add("pkt_conversion", "+05:00" in pkt["pkt"] or "T17:00:00" in pkt["pkt"])

    # DST transitions
    add("dst_winter_after_nov1", us_dst_season(date(2026, 11, 2)) == "WINTER")
    add("dst_summer_july", us_dst_season(date(2026, 7, 15)) == "SUMMER")
    summer_gap = state_at_utc(datetime(2026, 7, 14, 21, 30, 0, tzinfo=timezone.utc))  # Tue summer closed window
    add("dst_summer_break_window", summer_gap["state"] == CLOSED)
    winter_open_at_same = state_at_utc(datetime(2026, 11, 10, 21, 30, 0, tzinfo=timezone.utc))
    add("dst_winter_still_open_2130", winter_open_at_same["state"] == OPEN)

    # Holidays
    hol = state_at_utc(datetime(2026, 12, 25, 12, 0, 0, tzinfo=timezone.utc))
    add("holiday_exceptions_unknown", hol["state"] == UNKNOWN and date(2026, 12, 25) in HOLIDAYS_2026)

    # Unknown / missing / expired / conflict
    missing = build_session_model(missing_schedule=True)
    add("unknown_schedule_behavior", lookup_session(datetime(2026, 11, 10, 12, tzinfo=timezone.utc), model=missing)["state"] == UNKNOWN)
    expired = freshness_policy(retrieved_on="2025-01-01", as_of=date(2026, 11, 12))
    add("expired_evidence", expired["status"] == "EXPIRED" and expired["usable"] is False)
    add("is_evidence_expired_helper", is_evidence_expired(retrieved_on="2020-01-01", as_of_utc=datetime(2026, 11, 12, tzinfo=timezone.utc)))
    conf = evaluate_conflict(
        source_a_segments=[{"start": "00:00:00", "end": "21:58:00", "state": OPEN}],
        source_b_segments=[{"start": "00:00:00", "end": "20:58:00", "state": OPEN}],
    )
    add("conflicting_source_behavior", conf["conflict"] is True and conf["effective_state"] == UNKNOWN)

    miss_pf = session_aware_preflight(
        now_utc=datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        model=missing,
    )
    add("missing_evidence_fail_closed", miss_pf["reject"] is True and miss_pf["allowed"] is False)

    # Journal idempotency + recovery + conflict
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "j"
        ing = ingest_session_evidence(root)
        add("evidence_journal_idempotency", ing["all_duplicate_on_replay"] is True)
        # crash recovery
        root2 = Path(td) / "j2"
        try:
            crash = ingest_session_evidence(root2, crash_after_wal=True)
            # first event may crash; recover path
            recovered = ingest_session_evidence(root2)
            add(
                "recovery_durability",
                recovered["integrity"]["n_events"] >= 1 or crash.get("status") == "CRASH_INJECTED_THEN_RECOVERABLE",
            )
        except Exception:
            recovered = ingest_session_evidence(root2)
            add("recovery_durability", recovered["n_events"] >= 1)

        conf_j = ingest_conflicting_payload(Path(td) / "jc")
        add("journal_conflict_preservation", conf_j["conflict_quarantined"] is True)

    # Preflight rejection when closed
    model = build_session_model()
    pf_closed = session_aware_preflight(
        now_utc=datetime(2026, 11, 14, 12, tzinfo=timezone.utc),  # Saturday
        model=model,
    )
    add("session_aware_preflight_rejection", pf_closed["reject"] is True and pf_closed["authorizes_execution"] is False)
    pf_open = session_aware_preflight(
        now_utc=datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        model=model,
    )
    add(
        "open_does_not_authorize",
        pf_open["session_state"] == OPEN
        and pf_open["authorizes_execution"] is False
        and BROKER_EXECUTION_AUTHORIZED is False,
    )

    add("no_order_invariant", "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED")
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
