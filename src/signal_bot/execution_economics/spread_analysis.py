"""Live Exness XAUUSDm spread measurement from journal quotes only."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase64_5.journal import BrokerEvidenceJournal
from phase67.constants import JOURNAL_ROOT

from signal_bot.execution_economics.constants import (
    ACTIVE_SYMBOL,
    ASIA_TZ,
    EXPECTED_SERVER,
    LONDON_TZ,
    SPREAD_ANALYSIS_VERSION,
    USER_TZ,
    VERIFIED_POINT,
    VERIFIED_TICK_SIZE,
    canonical_json_sha256,
)
from signal_bot.execution_economics.quote_validation import validate_quote_record

PKT = ZoneInfo(USER_TZ)
ASIA = ZoneInfo(ASIA_TZ)
LONDON = ZoneInfo(LONDON_TZ)
UTC = ZoneInfo("UTC")


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return s[i]


def _session_bucket(dt: datetime) -> str:
    """Coarse research buckets — not H70 trading windows."""
    asia_h = dt.astimezone(ASIA).hour
    lon_h = dt.astimezone(LONDON).hour
    if 9 <= asia_h < 15:
        return "ASIA_TOKYO_09_15"
    if 8 <= lon_h < 12:
        return "LONDON_08_12"
    if lon_h in (7, 8) or asia_h in (15, 16):
        return "SESSION_TRANSITION_NEAR"
    return "OTHER"


def analyze_live_spreads(
    *,
    journal_root: Any | None = None,
    point: float = VERIFIED_POINT,
    tick_size: float = VERIFIED_TICK_SIZE,
) -> dict[str, Any]:
    root = journal_root or JOURNAL_ROOT
    journal = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
    rows = journal.all_events() if root.exists() else []

    usable_rows: list[dict[str, Any]] = []
    rejected: dict[str, int] = defaultdict(int)
    by_pkt_hour: dict[str, list[float]] = defaultdict(list)
    by_session: dict[str, list[float]] = defaultdict(list)
    preserved: list[dict[str, Any]] = []

    for r in rows:
        if r.get("kind") != "QUOTE_SNAPSHOT":
            continue
        # Quotes are live broker observations; exclude synthetic
        if r.get("synthetic") or r.get("store_label") not in (None, "GENUINE"):
            rejected["synthetic_or_bad_store"] += 1
            continue
        v = validate_quote_record(r, point=point, tick_size=tick_size)
        if not v["usable"] or v["spread_price"] is None:
            for f in v["quality_flags"] or ["unusable"]:
                rejected[f] += 1
            continue

        dt = _parse_utc(r.get("server_timestamp_utc"))
        if not dt:
            rejected["invalid_server_timestamp"] += 1
            continue

        sp = float(v["spread_price"])
        usable_rows.append(r)
        by_pkt_hour[f"{dt.astimezone(PKT).hour:02d}"].append(sp)
        sess = _session_bucket(dt)
        by_session[sess].append(sp)

        prov = r.get("evidence_provenance") or r.get("source_classification") or "BROKER_OBSERVED_QUOTE"
        preserved.append(
            {
                "broker_server": r.get("source_server") or EXPECTED_SERVER,
                "symbol": r.get("symbol") or ACTIVE_SYMBOL,
                "bid": v["bid"],
                "ask": v["ask"],
                "spread_price": sp,
                "spread_ticks": v["spread_ticks"],
                "spread_points": v["spread_points"],
                "quote_timestamp_utc": r.get("server_timestamp_utc"),
                "collection_timestamp_utc": r.get("collection_timestamp_utc"),
                "data_provenance": prov,
                "quality_flags": [],
                "session_bucket": sess,
                "pkt_hour": dt.astimezone(PKT).hour,
            }
        )

    spreads = [float(p["spread_price"]) for p in preserved]
    points = [float(p["spread_points"]) for p in preserved if p.get("spread_points") is not None]

    def _dist(xs: list[float]) -> dict[str, Any]:
        return {
            "n": len(xs),
            "mean": (sum(xs) / len(xs)) if xs else None,
            "median": _pct(xs, 0.5),
            "p75": _pct(xs, 0.75),
            "p90": _pct(xs, 0.90),
            "p95": _pct(xs, 0.95),
            "p99": _pct(xs, 0.99),
            "maximum": max(xs) if xs else None,
            "minimum": min(xs) if xs else None,
        }

    # High-vol classification only when M5 ranges support it AND spreads vary
    high_vol_note = (
        "NOT_CLASSIFIED — current usable quote sample has essentially constant spread; "
        "cannot attribute high-volatility spread regimes from this evidence alone."
    )
    unique_rounded = sorted({round(s, 6) for s in spreads})

    out = {
        "analysis_version": SPREAD_ANALYSIS_VERSION,
        "symbol": ACTIVE_SYMBOL,
        "point_definition": point,
        "tick_size": tick_size,
        "n_journal_quote_snapshots": sum(1 for r in rows if r.get("kind") == "QUOTE_SNAPSHOT"),
        "n_usable_quotes": len(preserved),
        "n_rejected": sum(rejected.values()),
        "rejection_counts": dict(rejected),
        "distribution_price_units": _dist(spreads),
        "distribution_points": _dist(points),
        "by_pkt_hour_median_price": {
            h: _pct(vs, 0.5) for h, vs in sorted(by_pkt_hour.items())
        },
        "by_pkt_hour_n": {h: len(vs) for h, vs in sorted(by_pkt_hour.items())},
        "by_session_bucket": {
            k: _dist(vs) for k, vs in sorted(by_session.items())
        },
        "session_transition": by_session.get("SESSION_TRANSITION_NEAR")
        and _dist(by_session["SESSION_TRANSITION_NEAR"])
        or {"n": 0, "note": "No quotes classified in transition bucket"},
        "high_volatility_periods": {
            "classified": False,
            "note": high_vol_note,
            "unique_spread_values_rounded": unique_rounded,
        },
        "limitations": [
            "Sample is single-calendar-day / short runtime — does not represent all market conditions",
            "Do not infer historical spreads from today's observations",
            "Journal spread field is price units (ask-bid); points = price/point",
            "Floating spread; snapshot cadence ≠ tick stream",
        ],
        "sample_preserved_head": preserved[:5],
        "sample_preserved_tail": preserved[-5:] if preserved else [],
        "sha256": None,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
