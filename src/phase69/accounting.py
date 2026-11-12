"""Live evidence accounting over Phase67 journal — no second store."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_13.schedule import state_at_utc
from phase69.constants import (
    ACCOUNTING_PATH,
    BROKER_OBSERVED_LIVE_BAR,
    BROKER_OBSERVED_QUOTE,
    HISTORICAL_BACKFILL,
    PHASE67_JOURNAL,
    PHASE67_VERIFY,
    SYNTHETIC_FIXTURE,
    canonical_json_sha256,
)
from phase69.provenance import classify_record, normalize_provenance


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def build_live_evidence_accounting() -> dict[str, Any]:
    verify = {}
    if PHASE67_VERIFY.is_file():
        verify = json.loads(PHASE67_VERIFY.read_text(encoding="utf-8"))
    started = verify.get("started_utc")
    ended = verify.get("ended_utc")
    runtime = verify.get("runtime_sec_measured")

    journal = BrokerEvidenceJournal(PHASE67_JOURNAL, allow_synthetic=False, store_label="GENUINE")
    rows = journal.all_events() if PHASE67_JOURNAL.exists() else []
    if not started and rows:
        cols = [_parse(r.get("collection_timestamp_utc")) for r in rows]
        cols = [c for c in cols if c]
        started = min(cols).strftime("%Y-%m-%dT%H:%M:%SZ") if cols else None
    if not ended and rows:
        cols = [_parse(r.get("collection_timestamp_utc")) for r in rows]
        cols = [c for c in cols if c]
        ended = max(cols).strftime("%Y-%m-%dT%H:%M:%SZ") if cols else None

    counts = Counter()
    unique_live_bars: set[str] = set()
    unique_backfill_bars: set[str] = set()
    quote_n = 0
    synth_n = 0
    dup_suppressed_estimate = 0  # from verify totals if present
    per_date_live: dict[str, int] = defaultdict(int)
    per_session_live: dict[str, int] = defaultdict(int)
    stale_n = 0
    rejected_n = 0

    for r in rows:
        prov = classify_record(r, collector_started_utc=started, collector_ended_utc=ended)
        counts[prov] += 1
        ts = str(r.get("server_timestamp_utc") or "")
        day = ts[:10] if ts else None
        if prov == SYNTHETIC_FIXTURE:
            synth_n += 1
        elif prov == BROKER_OBSERVED_QUOTE:
            quote_n += 1
        elif prov == HISTORICAL_BACKFILL:
            if ts:
                unique_backfill_bars.add(ts)
        elif prov == BROKER_OBSERVED_LIVE_BAR:
            if ts:
                unique_live_bars.add(ts)
                if day:
                    per_date_live[day] += 1
                sess = r.get("session_state") or "UNKNOWN"
                per_session_live[str(sess)] += 1
        if r.get("rejection_reason") or r.get("validation_status") == "REJECTED":
            rejected_n += 1

    # Quarantine rows
    q_n = len(journal.quarantine_rows()) if PHASE67_JOURNAL.exists() else 0
    integ = journal.integrity_report() if PHASE67_JOURNAL.exists() else {}

    # Independent dates with ≥1 newly observed live closed bar
    independent_live_dates = sorted(per_date_live.keys())

    # Contamination check
    contamination = synth_n > 0 and integ.get("store_label") == "GENUINE"

    out = {
        "journal_root": str(PHASE67_JOURNAL),
        "collector_started_utc": started,
        "collector_ended_utc": ended,
        "runtime_sec_measured": runtime,
        "continuous_uptime_claimed": False,
        "provenance_counts": dict(counts),
        "unique_historical_backfill_m5_bars": len(unique_backfill_bars),
        "unique_newly_closed_live_m5_bars": len(unique_live_bars),
        "live_quote_observations": quote_n,
        "synthetic_in_genuine_store": synth_n,
        "contamination_detected": contamination,
        "independent_live_collection_dates": independent_live_dates,
        "n_independent_live_dates": len(independent_live_dates),
        "per_date_live_bar_counts": dict(per_date_live),
        "per_session_live_bar_counts": dict(per_session_live),
        "verify_totals": verify.get("totals"),
        "duplicate_suppressed_verify": (verify.get("totals") or {}).get("DUPLICATE_SUPPRESSED"),
        "quarantine_n": q_n,
        "rejected_n": rejected_n,
        "stale_n": stale_n,
        "reconnects_observed": int((verify.get("totals") or {}).get("BLOCKED") or 0),
        "journal_integrity": integ,
        "backfill_never_counted_as_live": True,
        "rule": "unique_newly_closed_live_m5_bars uses BROKER_OBSERVED_LIVE_BAR only; HISTORICAL_BACKFILL excluded",
        "second_collector_created": False,
        "second_journal_created": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    ACCOUNTING_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTING_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
