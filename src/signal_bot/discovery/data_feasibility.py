"""Independent vs exploratory data feasibility — never treat backfill as live confirmation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_bot.asia_london_mss.challenge import build_data_inventory
from signal_bot.discovery.constants import EVIDENCE_CLASS, PROJECT_ROOT


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _live_from_modules() -> tuple[dict[str, Any], dict[str, Any], str | None]:
    try:
        from phase67.session_evidence import build_session_evidence_report
        from phase69.accounting import build_live_evidence_accounting

        return build_live_evidence_accounting(), build_session_evidence_report(), None
    except Exception as exc:  # noqa: BLE001
        return {}, {}, str(exc)


def _live_from_snapshots() -> dict[str, Any]:
    """Fallback when live accounting import fails (e.g. system Python missing tzdata)."""
    snap = _load_json(PROJECT_ROOT / "reports" / "completion" / "PROMPT_05_SNAPSHOT.json")
    ev = snap.get("evidence") or (snap.get("health") or {}).get("evidence") or {}
    acc_file = _load_json(PROJECT_ROOT / "reports" / "phase69" / "live_evidence_accounting.json")
    sess_file = _load_json(PROJECT_ROOT / "reports" / "phase67" / "session_evidence.json")
    if not sess_file:
        sess_file = _load_json(PROJECT_ROOT / "reports" / "completion" / "PROMPT_05_SESSION_EVIDENCE.json")

    live_m5 = ev.get("unique_newly_closed_live_m5_bars")
    if live_m5 is None:
        live_m5 = acc_file.get("unique_newly_closed_live_m5_bars")
    quotes = ev.get("unique_broker_observed_quotes")
    if quotes is None:
        quotes = acc_file.get("live_quote_observations")
    n_dates = ev.get("independent_live_dates")
    if n_dates is None:
        n_dates = acc_file.get("n_independent_live_dates")
    complete = ev.get("n_independent_complete_asia_london_dates")
    if complete is None:
        complete = sess_file.get("n_independent_complete_live_dates")
    incomplete = ev.get("incomplete_session_dates") or sess_file.get("incomplete_dates")
    backfill = ev.get("unique_historical_backfill_m5_bars")
    if backfill is None:
        backfill = acc_file.get("unique_historical_backfill_m5_bars")

    return {
        "unique_newly_closed_live_m5_bars": int(live_m5 or 0),
        "live_quote_observations": quotes,
        "n_independent_live_dates": int(n_dates or 0),
        "n_independent_complete_live_dates": int(complete or 0),
        "incomplete_dates": incomplete,
        "unique_historical_backfill_m5_bars": backfill,
        "journal_root": ev.get("journal_root") or acc_file.get("journal_root"),
        "source": "PROMPT_05_SNAPSHOT_AND_OR_PHASE69_ACCOUNTING_FALLBACK",
        "collector_status": (snap.get("health") or {}).get("service_status"),
        "mt5_connection_state": (snap.get("health") or {}).get("mt5_connection_state"),
    }


def build_data_feasibility() -> dict[str, Any]:
    inv = build_data_inventory()
    live_inv = inv.get("live_broker_observed") or {}
    acc, sess, err = _live_from_modules()
    fallback_used = False
    if err or not acc:
        snap_live = _live_from_snapshots()
        fallback_used = True
        live_m5 = int(snap_live.get("unique_newly_closed_live_m5_bars") or 0)
        quotes = snap_live.get("live_quote_observations")
        n_dates = int(snap_live.get("n_independent_live_dates") or 0)
        complete = int(snap_live.get("n_independent_complete_live_dates") or 0)
        incomplete = snap_live.get("incomplete_dates")
        backfill = snap_live.get("unique_historical_backfill_m5_bars")
        journal = snap_live.get("journal_root") or live_inv.get("path")
        collector_meta = {
            "service_status": snap_live.get("collector_status"),
            "mt5_connection_state": snap_live.get("mt5_connection_state"),
            "accounting_error": err,
            "fallback_source": snap_live.get("source"),
        }
    else:
        live_m5 = int(acc.get("unique_newly_closed_live_m5_bars") or 0)
        quotes = acc.get("live_quote_observations")
        n_dates = int(acc.get("n_independent_live_dates") or 0)
        complete = int(sess.get("n_independent_complete_live_dates") or 0)
        incomplete = sess.get("incomplete_dates")
        backfill = acc.get("unique_historical_backfill_m5_bars")
        journal = live_inv.get("path") or acc.get("journal_root")
        collector_meta = {"accounting_error": None, "fallback_source": None}

    # Confirmatory floor: complete Asia+London live dates dominate; tiny partial days do not qualify.
    sufficient_independent = complete >= 20 and live_m5 >= 500

    return {
        "evidence_class_for_discovery": (
            "INDEPENDENT_LIVE_ELIGIBLE" if sufficient_independent else EVIDENCE_CLASS
        ),
        "sufficient_for_independent_validation": sufficient_independent,
        "genuine_live_exness_xauusdm": {
            "unique_newly_closed_live_m5_bars": live_m5,
            "quotes": quotes,
            "independent_live_dates_any_live_bar": n_dates,
            "independent_complete_asia_london_dates": complete,
            "incomplete_dates": incomplete,
            "symbol": "XAUUSDm",
            "note": "Partial single calendar day ≠ independent validation dataset",
            "collector_meta": collector_meta,
            "fallback_snapshot_used": fallback_used,
        },
        "historical_exness_backfill_in_journal": {
            "unique_historical_backfill_m5": backfill,
            "never_count_as_live": True,
        },
        "metaquotes_xauusd_archives": {
            "phase53_eligible_consumed_days": inv.get("eligible_phase53_dates"),
            "n_eligible_consumed": inv.get("n_eligible_consumed_phase53_days"),
            "symbol": "XAUUSD",
            "provenance": "HISTORICAL_BACKFILL_METAQUOTES_DEMO_ARCHIVE",
            "previously_consumed": True,
            "independent_confirmation": False,
        },
        "phase38_secondary_archives": "Inventoried in Prompt4; MetaQuotes consumed exploratory only",
        "sealed_inaccessible": {
            "phase58_holdout": inv.get("phase58_holdout_sealed_not_accessed"),
            "accessed": False,
        },
        "phase44_49_forbidden": inv.get("phase44_49_forbidden"),
        "collector_note": "Prompt5 collector must remain operational; do not stop for discovery",
        "limitation": (
            f"Independent complete Asia+London live dates = {complete}; "
            f"unique live M5 bars = {live_m5}. "
            "Any archive screening is EXPLORATORY_RETROSPECTIVE_ONLY and cannot confirm edge."
        ),
        "live_journal_path": journal,
    }
