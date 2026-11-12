"""Deep audit for previously unaudited union days — never silently repair sources."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from phase60.adapters import inventory, m5_bars, root_for_day, tick_paths
from phase60.constants import SYMBOL, canonical_json_sha256
from phase60.sessions import session_label_utc_ts, session_stats


def _ohlc_errors(bar: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    try:
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    except Exception:
        return ["non_numeric_ohlc"]
    for name, v in (("open", o), ("high", h), ("low", l), ("close", c)):
        if v <= 0:
            errs.append(f"non_positive_{name}")
    if h < l:
        errs.append("high_lt_low")
    if h < max(o, c) or l > min(o, c):
        errs.append("ohlc_inconsistent")
    return errs


def _iter_ticks(day: str) -> Iterator[dict[str, Any]]:
    for p in tick_paths(day):
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    yield {"_parse_error": True, "raw": line[:80]}


def audit_day_deep(day: str) -> dict[str, Any]:
    root = root_for_day(day)
    excluded: list[dict[str, Any]] = []
    if root is None:
        return {
            "day": day,
            "ok": False,
            "pass_defined_audit": False,
            "excluded_reason": "missing_archive_root",
            "excluded_observations": [{"reason": "missing_archive_root"}],
            "source_silently_repaired": False,
        }

    m5 = m5_bars(day)
    ts_list = [str(b.get("timestamp_utc")) for b in m5]
    dup_ts = [t for t, n in Counter(ts_list).items() if n > 1]
    ohlc_bad = []
    for i, b in enumerate(m5):
        e = _ohlc_errors(b)
        if e:
            ohlc_bad.append({"idx": i, "ts": b.get("timestamp_utc"), "errors": e})
    if dup_ts:
        excluded.append({"reason": "duplicate_timestamps", "n": len(dup_ts), "sample": dup_ts[:5]})
    if ohlc_bad:
        excluded.append({"reason": "invalid_ohlc", "n": len(ohlc_bad), "sample": ohlc_bad[:5]})

    gaps = []
    for a, b in zip(m5, m5[1:]):
        ta, tb = str(a.get("timestamp_utc")), str(b.get("timestamp_utc"))
        try:
            da = datetime.strptime(ta[:19], "%Y-%m-%d %H:%M:%S")
            db = datetime.strptime(tb[:19], "%Y-%m-%d %H:%M:%S")
            delta = (db - da).total_seconds() / 60.0
            if delta > 5.5:
                gaps.append({"from": ta, "to": tb, "gap_minutes": delta})
        except Exception:
            gaps.append({"from": ta, "to": tb, "gap_minutes": None, "parse_error": True})

    # Tick stream quality
    ticks_n = 0
    missing_ba = 0
    crossed = 0
    zero_neg_spread = 0
    parse_errors = 0
    unordered = 0
    dup_tick_ts = 0
    prev_ts: str | None = None
    seen_ts: set[str] = set()
    tick_hours: set[int] = set()
    spreads_by_bar: dict[str, float] = {}
    stale_gaps_gt_5m = 0
    last_tick_dt: datetime | None = None
    session_ts_sample: list[str] = []

    for t in _iter_ticks(day):
        if t.get("_parse_error"):
            parse_errors += 1
            continue
        ticks_n += 1
        ts = str(t.get("timestamp_utc") or "")
        if ts:
            if len(session_ts_sample) < 5000:
                session_ts_sample.append(ts)
            try:
                tick_hours.add(int(ts[11:13]))
            except Exception:
                pass
            if ts in seen_ts:
                dup_tick_ts += 1
            else:
                seen_ts.add(ts)
            if prev_ts and ts < prev_ts:
                unordered += 1
            prev_ts = ts
            try:
                cur_dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                if last_tick_dt is not None:
                    gap_m = (cur_dt - last_tick_dt).total_seconds() / 60.0
                    if gap_m > 5.5:
                        stale_gaps_gt_5m += 1
                last_tick_dt = cur_dt
            except Exception:
                pass

        bid, ask = t.get("bid"), t.get("ask")
        if bid is None or ask is None:
            missing_ba += 1
            continue
        try:
            fb, fa = float(bid), float(ask)
        except Exception:
            missing_ba += 1
            continue
        if fa < fb:
            crossed += 1
        sp = fa - fb
        if sp <= 0:
            zero_neg_spread += 1
        # first spread per M5 bar key (floor to 5m by string minute)
        if ts and len(ts) >= 16:
            try:
                minute = int(ts[14:16])
                bar_min = minute - (minute % 5)
                bar_key = f"{ts[:14]}{bar_min:02d}:00"
                if bar_key not in spreads_by_bar:
                    spreads_by_bar[bar_key] = sp
            except Exception:
                pass

    bars_without_ticks = [t for t in ts_list if t not in spreads_by_bar]
    # Also try exact timestamp match from M5
    if bars_without_ticks and spreads_by_bar:
        # rebuild with exact m5 timestamps via minute floor of m5 ts
        remapped = {}
        for bar_ts in ts_list:
            try:
                minute = int(str(bar_ts)[14:16])
                bar_min = minute - (minute % 5)
                key = f"{str(bar_ts)[:14]}{bar_min:02d}:00"
                if key in spreads_by_bar:
                    remapped[bar_ts] = spreads_by_bar[key]
            except Exception:
                pass
        bars_without_ticks = [t for t in ts_list if t not in remapped]
        spreads_by_bar = remapped or spreads_by_bar

    if ticks_n == 0:
        excluded.append({"reason": "no_ticks", "n": 1})
    if missing_ba:
        excluded.append({"reason": "missing_bid_ask_ticks", "n": missing_ba})
    if crossed:
        excluded.append({"reason": "crossed_quotes", "n": crossed})
    if parse_errors:
        excluded.append({"reason": "tick_parse_errors", "n": parse_errors})

    sessions = session_stats(ts_list)
    # pass criteria: m5 present, no dup ts, no ohlc errors, ticks present, bid/ask mostly valid
    pass_audit = (
        len(m5) > 0
        and len(dup_ts) == 0
        and len(ohlc_bad) == 0
        and ticks_n > 0
        and missing_ba == 0
        and crossed == 0
        and parse_errors == 0
    )

    return {
        "day": day,
        "source_root": str(root),
        "m5_n": len(m5),
        "ticks_n": ticks_n,
        "tick_hours_present": sorted(tick_hours),
        "n_tick_hour_files": len(tick_paths(day)),
        "n_duplicate_m5_timestamps": len(dup_ts),
        "n_ohlc_errors": len(ohlc_bad),
        "ohlc_errors_sample": ohlc_bad[:5],
        "n_gaps_gt_5m_m5": len(gaps),
        "gaps_sample": gaps[:10],
        "missing_ba": missing_ba,
        "crossed": crossed,
        "zero_or_negative_spreads": zero_neg_spread,
        "tick_parse_errors": parse_errors,
        "unordered_tick_timestamps": unordered,
        "duplicate_tick_timestamps": dup_tick_ts,
        "stale_or_abnormal_tick_gaps_gt_5m": stale_gaps_gt_5m,
        "bars_without_aligned_ticks_n": len(bars_without_ticks),
        "bars_without_aligned_ticks_sample": bars_without_ticks[:10],
        "observable_spread_bars": len(spreads_by_bar),
        "sessions_pkt": sessions,
        "session_label_sample": {
            "ASIA": sum(1 for t in ts_list if session_label_utc_ts(t) == "ASIA"),
            "LONDON": sum(1 for t in ts_list if session_label_utc_ts(t) == "LONDON"),
            "NY": sum(1 for t in ts_list if session_label_utc_ts(t) == "NY"),
            "OFF_HOURS": sum(1 for t in ts_list if session_label_utc_ts(t) == "OFF_HOURS"),
        },
        "excluded_observations": excluded,
        "ok": pass_audit and len(bars_without_ticks) == 0,
        "pass_defined_audit": pass_audit,
        "bidask_observable": ticks_n > 0 and missing_ba == 0,
        "source_silently_repaired": False,
        "limitations": [
            "Deep audit reports issues; does not mutate JSONL sources",
            "M5–tick alignment uses timestamp floor to 5m; residual misalignment recorded",
        ],
    }


def audit_remaining_days(days: list[str]) -> dict[str, Any]:
    rows = [audit_day_deep(d) for d in days]
    out = {
        "n_days": len(days),
        "days": days,
        "rows": rows,
        "n_pass_defined_audit": sum(1 for r in rows if r.get("pass_defined_audit")),
        "n_ok_strict": sum(1 for r in rows if r.get("ok")),
        "n_fail": sum(1 for r in rows if not r.get("pass_defined_audit")),
        "total_m5_bars": sum(int(r.get("m5_n") or 0) for r in rows),
        "total_ticks": sum(int(r.get("ticks_n") or 0) for r in rows),
        "failed_days": [r["day"] for r in rows if not r.get("pass_defined_audit")],
        "source_silently_repaired": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def build_updated_coverage(
    *,
    phase59_deep_days: list[str],
    remaining_audit: dict[str, Any],
    union_days: list[str],
) -> dict[str, Any]:
    newly = [r["day"] for r in remaining_audit.get("rows") or [] if r.get("pass_defined_audit")]
    newly_fail = [r["day"] for r in remaining_audit.get("rows") or [] if not r.get("pass_defined_audit")]
    final_deep = sorted(set(phase59_deep_days) | set(newly))
    still_missing = sorted(set(union_days) - set(final_deep))
    claim_100 = len(final_deep) == len(union_days) == 100 and not still_missing and not newly_fail
    out = {
        "original_phase59_deep_audit_n": len(phase59_deep_days),
        "newly_deep_audited_pass_n": len(newly),
        "newly_deep_audited_pass_days": newly,
        "newly_failed_or_incomplete": newly_fail,
        "final_verified_deep_audit_n": len(final_deep),
        "final_verified_deep_audit_days": final_deep,
        "union_n_days": len(union_days),
        "still_not_verified_deep": still_missing,
        "hundred_day_coverage_claim_permitted": claim_100,
        "source_silently_repaired": False,
        "note": (
            "100-day coverage claim permitted only if all 100 dates pass defined audit"
            if not claim_100
            else "All 100 union dates passed defined deep audit"
        ),
    }
    out["coverage_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "coverage_sha256"})
    return out


def build_integrity_summary(
    *,
    phase59_integrity: dict[str, Any],
    remaining_audit: dict[str, Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    rows = remaining_audit.get("rows") or []
    out = {
        "phase59_original": {
            "n_days": phase59_integrity.get("n_days"),
            "n_ok": phase59_integrity.get("n_ok"),
            "total_m5_bars": phase59_integrity.get("total_m5_bars"),
            "total_ticks": phase59_integrity.get("total_ticks"),
            "n_gap_days": phase59_integrity.get("n_gap_days"),
        },
        "phase60_remaining_10": {
            "n_days": remaining_audit.get("n_days"),
            "n_pass": remaining_audit.get("n_pass_defined_audit"),
            "n_fail": remaining_audit.get("n_fail"),
            "total_m5_bars": remaining_audit.get("total_m5_bars"),
            "total_ticks": remaining_audit.get("total_ticks"),
            "gap_days": [r["day"] for r in rows if int(r.get("n_gaps_gt_5m_m5") or 0) > 0],
            "failed_days": remaining_audit.get("failed_days"),
        },
        "combined_verified_deep_n": coverage.get("final_verified_deep_audit_n"),
        "hundred_day_claim": coverage.get("hundred_day_coverage_claim_permitted"),
        "source_silently_repaired": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
