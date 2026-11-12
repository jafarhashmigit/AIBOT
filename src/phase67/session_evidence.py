"""Asia/London session completeness for independent live research dates.

Does NOT mix HISTORICAL_BACKFILL with BROKER_OBSERVED_LIVE_BAR to manufacture completeness.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase64_5.journal import BrokerEvidenceJournal
from phase67.constants import ACTIVE_SYMBOL, JOURNAL_ROOT
from phase69.accounting import build_live_evidence_accounting
from phase69.constants import BROKER_OBSERVED_LIVE_BAR, HISTORICAL_BACKFILL
from phase69.provenance import classify_record

ASIA_TZ = "Asia/Tokyo"
LONDON_TZ = "Europe/London"
ASIA_START = (9, 0)
ASIA_END = (15, 0)
LONDON_START = (8, 0)
LONDON_END = (12, 0)

# Expected M5 bars in a full session window (exclusive end)
ASIA_EXPECTED_BARS = 72  # 6h
LONDON_EXPECTED_BARS = 48  # 4h
# Completeness threshold: allow small weekend/gap tolerance but do not claim complete if sparse
MIN_ASIA_LIVE_FRAC = 0.90
MIN_LONDON_LIVE_FRAC = 0.90


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _session_bar_timestamps(day: str, tz_name: str, start_hm: tuple[int, int], end_hm: tuple[int, int]) -> list[str]:
    """Expected M5 open timestamps (UTC Z) for a local session on calendar day."""
    tz = ZoneInfo(tz_name)
    y, m, d = map(int, day.split("-"))
    start_local = datetime(y, m, d, start_hm[0], start_hm[1], tzinfo=tz)
    end_local = datetime(y, m, d, end_hm[0], end_hm[1], tzinfo=tz)
    out: list[str] = []
    cur = start_local
    while cur < end_local:
        out.append(cur.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        cur += timedelta(minutes=5)
    return out


def _local_day(ts: datetime, tz_name: str) -> str:
    return ts.astimezone(ZoneInfo(tz_name)).date().isoformat()


def build_session_evidence_report(
    *,
    journal_root: Any | None = None,
    collector_started_utc: str | None = None,
    collector_ended_utc: str | None = None,
) -> dict[str, Any]:
    root = journal_root or JOURNAL_ROOT
    acc = build_live_evidence_accounting()
    started = collector_started_utc or acc.get("collector_started_utc")
    ended = collector_ended_utc or acc.get("collector_ended_utc")

    journal = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
    rows = journal.all_events() if root.exists() else []

    live_by_ts: dict[str, dict[str, Any]] = {}
    backfill_by_ts: dict[str, dict[str, Any]] = {}
    dup_estimate = 0
    conflict_n = len(journal.incidents()) if root.exists() else 0
    invalid_n = 0
    prov_counts: dict[str, int] = defaultdict(int)

    # Detect duplicate market identities in journal (legacy inflation)
    seen_mid: dict[str, int] = defaultdict(int)
    for r in rows:
        mid = BrokerEvidenceJournal.market_identity_key(r)
        if mid:
            seen_mid[mid] += 1
        if r.get("validation_status") not in (None, "OK"):
            invalid_n += 1
        prov = classify_record(r, collector_started_utc=started, collector_ended_utc=ended)
        prov_counts[prov] += 1
        if r.get("kind") != "M5_BAR":
            continue
        if r.get("symbol") not in (ACTIVE_SYMBOL, None):
            continue
        ts = str(r.get("server_timestamp_utc") or "")
        if not ts:
            continue
        if prov == BROKER_OBSERVED_LIVE_BAR:
            live_by_ts.setdefault(ts, r)
        elif prov == HISTORICAL_BACKFILL:
            backfill_by_ts.setdefault(ts, r)
    dup_estimate = sum(c - 1 for c in seen_mid.values() if c > 1)

    # Candidate dates from live bars (Tokyo calendar for Asia pairing; also London day)
    candidate_days: set[str] = set()
    for ts in live_by_ts:
        dt = _parse(ts)
        if not dt:
            continue
        candidate_days.add(_local_day(dt, ASIA_TZ))
        candidate_days.add(_local_day(dt, LONDON_TZ))

    dates_out: list[dict[str, Any]] = []
    complete: list[str] = []
    incomplete: list[str] = []

    for day in sorted(candidate_days):
        asia_exp = _session_bar_timestamps(day, ASIA_TZ, ASIA_START, ASIA_END)
        london_exp = _session_bar_timestamps(day, LONDON_TZ, LONDON_START, LONDON_END)
        asia_live = [t for t in asia_exp if t in live_by_ts]
        london_live = [t for t in london_exp if t in live_by_ts]
        asia_bf = [t for t in asia_exp if t in backfill_by_ts]
        london_bf = [t for t in london_exp if t in backfill_by_ts]
        asia_missing = [t for t in asia_exp if t not in live_by_ts]
        london_missing = [t for t in london_exp if t not in live_by_ts]

        # Source purity: complete live date cannot use backfill to fill gaps
        mixed = bool(asia_bf or london_bf) and bool(asia_live or london_live)
        asia_ok = len(asia_live) >= int(ASIA_EXPECTED_BARS * MIN_ASIA_LIVE_FRAC)
        london_ok = len(london_live) >= int(LONDON_EXPECTED_BARS * MIN_LONDON_LIVE_FRAC)
        pure = (len(asia_bf) == 0 and len(london_bf) == 0) or (not mixed and asia_ok and london_ok)
        # Strict: no backfill contribution toward completeness
        qualifies = asia_ok and london_ok and len(asia_bf) == 0 and len(london_bf) == 0 and conflict_n == 0

        rec = {
            "trading_date": day,
            "asia_expected_bars": len(asia_exp),
            "asia_observed_live_bars": len(asia_live),
            "asia_backfill_bars_same_window": len(asia_bf),
            "asia_missing_timestamps_sample": asia_missing[:10],
            "asia_missing_count": len(asia_missing),
            "london_expected_bars": len(london_exp),
            "london_observed_live_bars": len(london_live),
            "london_backfill_bars_same_window": len(london_bf),
            "london_missing_timestamps_sample": london_missing[:10],
            "london_missing_count": len(london_missing),
            "duplicate_market_identity_extras": dup_estimate,
            "conflict_incidents": conflict_n,
            "invalid_count": invalid_n,
            "session_completeness": {
                "asia": asia_ok,
                "london": london_ok,
            },
            "source_purity": "LIVE_ONLY" if (len(asia_bf) == 0 and len(london_bf) == 0) else "MIXED_OR_BACKFILL_PRESENT",
            "mixed_backfill_and_live": mixed,
            "qualification": "INDEPENDENT_COMPLETE_LIVE_DATE" if qualifies else "INCOMPLETE_OR_IMPURE",
            "qualifies_independent_complete": qualifies,
        }
        dates_out.append(rec)
        if qualifies:
            complete.append(day)
        else:
            incomplete.append(day)

    return {
        "symbol": ACTIVE_SYMBOL,
        "asia_tz": ASIA_TZ,
        "london_tz": LONDON_TZ,
        "asia_window_local": "09:00-15:00",
        "london_window_local": "08:00-12:00",
        "asia_expected_bars": ASIA_EXPECTED_BARS,
        "london_expected_bars": LONDON_EXPECTED_BARS,
        "min_asia_live_frac": MIN_ASIA_LIVE_FRAC,
        "min_london_live_frac": MIN_LONDON_LIVE_FRAC,
        "provenance_counts": dict(prov_counts),
        "unique_live_m5": len(live_by_ts),
        "unique_backfill_m5": len(backfill_by_ts),
        "duplicate_market_identity_extras": dup_estimate,
        "conflict_incidents": conflict_n,
        "invalid_count": invalid_n,
        "independent_complete_live_dates": complete,
        "n_independent_complete_live_dates": len(complete),
        "incomplete_dates": incomplete,
        "n_incomplete_dates": len(incomplete),
        "dates": dates_out,
        "future_target_complete_dates": 20,
        "target_met": len(complete) >= 20,
        "note": "Backfill never contributes to independent complete live dates. Phase58 holdout not accessed.",
    }
