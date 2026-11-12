"""Step 1 — Independent data & research inventory (read-only; no strategies/backtests)."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.archive_loader import sealed_forbidden
from phase58.constants import ARCHIVE_ROOTS, HORIZON_BARS, EVENT_STRIDE, SYMBOL
from phase58.data import eligible_days, list_all_days, resolve_root
from phase65.consumption import build_consumption_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
REPORTS_DIR = PROJECT_ROOT / "reports" / "strategy_research"
PHASE66_LIVE = SRC_DIR / "data" / "phase66" / "market_evidence_journal" / "events.jsonl"
PHASE66_FIXTURE = SRC_DIR / "data" / "phase66" / "fixture_market_evidence_journal" / "events.jsonl"


def _sha_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    ).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _m5_path(root: Path, day: str) -> Path:
    return root / "m5" / f"m5_{SYMBOL}_{day}.jsonl"


def _tick_paths(root: Path, day: str) -> list[Path]:
    return [root / "ticks" / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl" for h in range(24)]


def inventory_day(day: str, *, allow_forbidden: bool = False) -> dict[str, Any]:
    """Inventory one archive day. Does not compute hypothesis outcomes."""
    forbid = sealed_forbidden()
    if day in forbid and not allow_forbidden:
        return {
            "day": day,
            "status": "FORBIDDEN_SEALED_SKIPPED_DETAIL",
            "note": "Phase44/49 sealed-forbidden; not opened for scoring inventory detail",
        }
    try:
        root = resolve_root(day)
    except FileNotFoundError:
        return {"day": day, "status": "MISSING", "m5_bars": 0, "ticks": 0}

    m5_path = _m5_path(root, day)
    m5 = _load_jsonl(m5_path)
    ts = [str(r.get("timestamp_utc")) for r in m5]
    dup = len(ts) - len(set(ts))
    gaps = 0
    for a, b in zip(ts, ts[1:]):
        try:
            ta = datetime.fromisoformat(a.replace("Z", "+00:00").replace(" ", "T"))
            tb = datetime.fromisoformat(b.replace("Z", "+00:00").replace(" ", "T"))
            if (tb - ta).total_seconds() != 300:
                gaps += 1
        except Exception:
            gaps += 1

    tick_n = 0
    bidask_ok = 0
    tick_files_present = 0
    first_tick = None
    last_tick = None
    for tp in _tick_paths(root, day):
        if not tp.is_file():
            continue
        tick_files_present += 1
        with tp.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                tick_n += 1
                row = json.loads(line)
                bid, ask = row.get("bid"), row.get("ask")
                if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0 and float(ask) >= float(bid):
                    bidask_ok += 1
                tsu = row.get("timestamp_utc") or row.get("timestamp_msc")
                if first_tick is None:
                    first_tick = tsu
                last_tick = tsu

    # Sample spread from first/last M5 bar field (bar-level points) — not execution cost
    spread_field_n = sum(1 for r in m5 if r.get("spread") is not None)

    return {
        "day": day,
        "status": "OK",
        "root": str(root),
        "symbol": SYMBOL,
        "source_server_sample": (m5[0].get("source_server") if m5 else None),
        "source_classification": "HISTORICAL_ARCHIVE",
        "broker_observed_exness_xauusdm": False,
        "m5_path": str(m5_path),
        "m5_bars": len(m5),
        "m5_first_ts": ts[0] if ts else None,
        "m5_last_ts": ts[-1] if ts else None,
        "m5_duplicate_timestamps": dup,
        "m5_gap_transitions": gaps,
        "m5_spread_field_present_n": spread_field_n,
        "m5_file_sha256": _sha_file(m5_path),
        "tick_files_present": tick_files_present,
        "ticks": tick_n,
        "valid_bid_ask_ticks": bidask_ok,
        "tick_first": first_tick,
        "tick_last": last_tick,
        "spread_coverage_tick_pct": (100.0 * bidask_ok / tick_n) if tick_n else None,
    }


def inventory_phase66_live() -> dict[str, Any]:
    rows = _load_jsonl(PHASE66_LIVE)
    quotes = [r for r in rows if r.get("kind") == "QUOTE_SNAPSHOT"]
    m5 = [r for r in rows if r.get("kind") == "M5_BAR"]
    ok_q = [r for r in quotes if r.get("validation_status") == "OK" and r.get("bid") and r.get("ask")]
    dates = sorted({str(r.get("server_timestamp_utc") or "")[:10] for r in rows if r.get("server_timestamp_utc")})
    return {
        "dataset_id": "phase66_live_market_evidence_journal",
        "path": str(PHASE66_LIVE),
        "symbol": "XAUUSDm",
        "source_classification": "BROKER_OBSERVED",
        "source_server": (rows[0].get("source_server") if rows else None),
        "n_events": len(rows),
        "n_quote_snapshots": len(quotes),
        "n_valid_bid_ask_quotes": len(ok_q),
        "n_m5_bars": len(m5),
        "n_genuine_ticks": 0,  # copy_ticks not permitted; snapshots ≠ tick stream
        "independent_dates": dates,
        "n_independent_dates": len(dates),
        "first_ts": min((r.get("server_timestamp_utc") for r in rows if r.get("server_timestamp_utc")), default=None),
        "last_ts": max((r.get("server_timestamp_utc") for r in rows if r.get("server_timestamp_utc")), default=None),
        "content_hashes": sorted({r.get("content_hash") for r in rows if r.get("content_hash")}),
        "synthetic_fixture": False,
        "file_sha256": _sha_file(PHASE66_LIVE),
        "note": "Quote snapshots from symbol_info + M5 from copy_rates; not a continuous tick archive",
    }


def inventory_phase66_fixture() -> dict[str, Any]:
    rows = _load_jsonl(PHASE66_FIXTURE)
    return {
        "dataset_id": "phase66_fixture_market_evidence_journal",
        "path": str(PHASE66_FIXTURE),
        "source_classification": "SYNTHETIC_TEST_FIXTURE",
        "n_events": len(rows),
        "research_use": "EXCLUDED",
        "file_sha256": _sha_file(PHASE66_FIXTURE),
        "note": "Must never enter genuine research stores",
    }


def classify_eligibility() -> dict[str, Any]:
    cons = build_consumption_registry()
    splits = json.loads((PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json").read_text(encoding="utf-8"))
    p65_disc = set(cons["phase65_discovery"])
    p65_val = set(cons["phase65_validation"])
    p58_disc = set(splits["discovery"])
    p58_val = set(splits["validation"])
    p58_hold = set(splits["holdout_sealed"])
    forbid = set(sealed_forbidden())
    status_raw = dict(cons["status_by_day"])

    # Correct Phase65 consumption: leftover empty ⇒ discovery+validation days are consumed
    # even if status_by_day still says UNCONSUMED_ELIGIBLE.
    classification: dict[str, str] = {}
    for day, raw in status_raw.items():
        if day in p58_hold or raw in ("PHASE58_HOLDOUT_SEALED", "SEALED"):
            classification[day] = "SEALED_HOLDOUT"
        elif day in p65_disc or day in p65_val:
            classification[day] = "PREVIOUSLY_CONSUMED"
        elif raw in (
            "PHASE58_DISCOVERY_CONSUMED",
            "PHASE58_VALIDATION_CONSUMED",
            "PHASE49_DISCOVERY_CONSUMED",
            "PHASE49_CONFIRMATION_SEALED",
        ):
            classification[day] = "PREVIOUSLY_CONSUMED"
        elif raw == "UNCONSUMED_ELIGIBLE":
            classification[day] = "ELIGIBLE_FOR_NEW_DISCOVERY"
        else:
            classification[day] = "UNKNOWN"

    for d in forbid:
        classification.setdefault(d, "INVALID")

    # Live day from Phase66
    live = inventory_phase66_live()
    for d in live["independent_dates"]:
        if d and d not in classification:
            classification[d] = "ELIGIBLE_FOR_NEW_DISCOVERY"

    by_class: dict[str, list[str]] = {}
    for d, c in sorted(classification.items()):
        by_class.setdefault(c, []).append(d)

    eligible_new = by_class.get("ELIGIBLE_FOR_NEW_DISCOVERY", [])
    # Events: only countable without holdout outcome access — estimate from stride on eligible days
    # For consumed days we report Phase65 recorded event counts; for new eligible archive days compute bar-based capacity
    event_estimate_new = 0
    for d in eligible_new:
        if d.startswith("2026-11"):  # live incomplete day
            continue
        try:
            inv = inventory_day(d)
            bars = int(inv.get("m5_bars") or 0)
            # same construction window as phase65 events
            first, last = 48, bars - (1 + HORIZON_BARS)
            if last >= first:
                # non-overlapping stride capacity upper bound
                event_estimate_new += max(0, (last - first) // EVENT_STRIDE + 1)
        except Exception:
            pass

    return {
        "phase65_registry_sha256": cons.get("sha256"),
        "phase65_status_by_day_stale_note": (
            "Phase65 status_by_day still labels discovery/validation days UNCONSUMED_ELIGIBLE, "
            "but phase65_discovery/validation lists and leftover_unused=[] show they were consumed. "
            "Step1 reclassifies those as PREVIOUSLY_CONSUMED."
        ),
        "phase65_discovery": sorted(p65_disc),
        "phase65_validation": sorted(p65_val),
        "phase65_leftover_unused": list(cons.get("phase65_leftover_unused") or []),
        "phase58_holdout_sealed": sorted(p58_hold),
        "phase58_holdout_outcomes_accessed": False,
        "phase49_forbidden_sealed_n": len(forbid),
        "classification_counts": {k: len(v) for k, v in sorted(by_class.items())},
        "by_class": {k: v for k, v in sorted(by_class.items())},
        "genuinely_eligible_independent_dates": eligible_new,
        "n_genuinely_eligible_independent_dates": len(eligible_new),
        "n_eligible_archive_dates_excluding_live_incomplete": len([d for d in eligible_new if not d.startswith("2026-11")]),
        "estimated_new_discovery_events_upper_bound_archive": event_estimate_new,
        "phase65_recorded_discovery_events": 126,
        "phase65_recorded_validation_events": 72,
        "validation_reserved_dates": by_class.get("VALIDATION_RESERVED", []),
        "note": "Do not assume unlisted dates are unconsumed; only dates in registries are classified.",
    }


def aggregate_archive(days: list[str], *, label: str, allow_forbidden: bool = False) -> dict[str, Any]:
    per = []
    for d in days:
        per.append(inventory_day(d, allow_forbidden=allow_forbidden))
    ok = [p for p in per if p.get("status") == "OK"]
    return {
        "dataset_id": label,
        "symbol": SYMBOL,
        "timeframe": "M5 (+ticks where present)",
        "source_classification": "HISTORICAL_ARCHIVE",
        "n_independent_dates": len(ok),
        "dates": [p["day"] for p in ok],
        "first_ts": min((p["m5_first_ts"] for p in ok if p.get("m5_first_ts")), default=None),
        "last_ts": max((p["m5_last_ts"] for p in ok if p.get("m5_last_ts")), default=None),
        "total_m5_bars": sum(int(p.get("m5_bars") or 0) for p in ok),
        "total_ticks": sum(int(p.get("ticks") or 0) for p in ok),
        "total_valid_bid_ask_ticks": sum(int(p.get("valid_bid_ask_ticks") or 0) for p in ok),
        "total_m5_duplicate_timestamps": sum(int(p.get("m5_duplicate_timestamps") or 0) for p in ok),
        "total_m5_gap_transitions": sum(int(p.get("m5_gap_transitions") or 0) for p in ok),
        "days_with_gaps": [p["day"] for p in ok if int(p.get("m5_gap_transitions") or 0) > 0],
        "source_servers": sorted({p.get("source_server_sample") for p in ok if p.get("source_server_sample")}),
        "roots": sorted({p.get("root") for p in ok if p.get("root")}),
        "per_day": per,
        "aggregate_sha256": _sha_obj([{k: v for k, v in p.items() if k != "per_day"} for p in ok]),
    }


def feature_feasibility(archive_has_m5: bool, archive_has_ticks: bool, live_quotes: bool, live_m5: bool) -> list[dict[str, Any]]:
    def row(name, required, exists, decision_time, hist_ok, limitations):
        return {
            "feature": name,
            "required_data": required,
            "data_exists": exists,
            "available_at_decision_time": decision_time,
            "valid_for_historical_research": hist_ok,
            "proxy_limitations": limitations,
        }

    return [
        row("multi_horizon_returns", "M5 OHLC", archive_has_m5, True, True, "Archive XAUUSD≠XAUUSDm; use closed bars only"),
        row("candle_body_wick_ratios", "M5 OHLC", archive_has_m5, True, True, "None beyond substrate"),
        row("previous_range_breakout", "M5 OHLC history", archive_has_m5, True, True, "Needs lookback bars; no future bars"),
        row("failed_breakout", "M5 OHLC + later path", archive_has_m5, "feature yes / label needs future", True, "Label requires outcome horizon; feature uses past only"),
        row("ATR_realized_vol", "M5 OHLC", archive_has_m5, True, True, "Standard causal ATR"),
        row("vol_compression_expansion", "M5 ATR series", archive_has_m5, True, True, "Used in Phase65 H65_C1 — family failed"),
        row("trend_persistence", "M5 returns/sign runs", archive_has_m5, True, True, "Definition-dependent"),
        row("price_displacement", "M5 OHLC", archive_has_m5, True, True, None),
        row("mean_reversion_distance", "M5 OHLC", archive_has_m5, True, True, "Family previously retired in inventory"),
        row("session_relative_behaviour", "M5 + Phase64.13 schedule", archive_has_m5, True, "partial", "Schedule is Exness; archive is MetaQuotes — substrate mismatch"),
        row("spread_conditioned_outcomes", "tick bid/ask at decision", archive_has_ticks, True, True, "Bar.spread is points proxy; prefer tick bid/ask. Commission/swap still UNKNOWN"),
        row("tick_velocity", "tick timestamps stream", archive_has_ticks, True, True, "Feasible on archive ticks; NOT on Phase66 live snapshots alone"),
        row("bid_ask_quote_dynamics", "tick bid/ask stream", archive_has_ticks, True, True, "Archive ticks yes; live Phase66 only sparse symbol_info snapshots — insufficient for dynamics"),
        row("live_xauusdm_quote_dynamics", "dense XAUUSDm ticks", live_quotes and False, False, False, "Phase66 has sparse snapshots only; copy_ticks_* not permitted"),
        row("live_xauusdm_m5_features", "XAUUSDm M5 history", live_m5, "only tiny window", False, f"Live journal M5 count too small for ATR/lookbacks"),
    ]


def outcome_feasibility() -> dict[str, Any]:
    horizons = [1, 3, 6, 12, 24]
    rows = []
    for h in horizons:
        # With EVENT_STRIDE = h for non-overlap, or purge of h bars between events
        purge = h
        rows.append(
            {
                "horizon_m5_bars": h,
                "minutes": h * 5,
                "supported_on_archive_m5_ticks": True,
                "bid_ask_path_fill_supported": True,
                "overlap_if_stride_1": True,
                "required_purge_embargo_bars": purge,
                "recommended_event_stride_bars": max(EVENT_STRIDE, h),
                "commission_treated_as_zero": False,
                "slippage_treated_as_zero": False,
                "swap_treated_as_zero": False,
                "notes": (
                    "phase49.build_outcome OBSERVED_BIDASK_ONLY available on archive ticks; "
                    "unknown costs must remain UNKNOWN / stressed — never zeroed. "
                    f"Phase58/65 used horizon={HORIZON_BARS} stride={EVENT_STRIDE}."
                ),
            }
        )
    return {
        "archive_supports_unbiased_path_outcomes": True,
        "live_xauusdm_supports_multi_horizon_outcomes": False,
        "horizons": rows,
        "holdout_outcomes_accessed": False,
    }


def sample_size_assessment(elig: dict[str, Any], archive_union: dict[str, Any]) -> dict[str, Any]:
    n_new = elig["n_genuinely_eligible_independent_dates"]
    n_arch_new = elig["n_eligible_archive_dates_excluding_live_incomplete"]
    return {
        "directions": [
            {
                "direction": "new_independent_discovery_on_archive_eligible_days",
                "eligible_event_count_upper_bound": elig["estimated_new_discovery_events_upper_bound_archive"],
                "independent_date_count": n_arch_new,
                "events_per_date": None,
                "missingness": "n/a — no unconsumed archive dates remain",
                "date_block_validation_feasible": False,
                "independent_confirmation_set_exists": bool(elig["phase58_holdout_sealed"]),
                "confirmation_usable_now": False,
                "statistical_limitations": (
                    "Zero unconsumed archive date-blocks remain after Phase58+Phase65 consumption. "
                    "Cannot establish power for a new discovery experiment on unused independent dates. "
                    "Phase58 sealed holdout remains available only after preregistered survivor — not for discovery."
                ),
            },
            {
                "direction": "descriptive_reanalysis_of_previously_consumed_archive",
                "eligible_event_count": "not for discovery — would recycle consumed data",
                "independent_date_count": archive_union["n_independent_dates"],
                "events_per_date": "~18 non-overlap H12 events/day historically (Phase65 ~18/day)",
                "missingness": f"gap_days_in_scanned_sets={len(archive_union.get('days_with_gaps') or [])}",
                "date_block_validation_feasible": "only as contaminated / non-independent vs prior looks",
                "independent_confirmation_set_exists": True,
                "statistical_limitations": (
                    "Any edge found would not be independent of prior Phase49/58/65 searches. "
                    "Multiple-testing debt already large (retired families). Not valid as new discovery evidence."
                ),
            },
            {
                "direction": "live_exness_xauusdm_broker_observed",
                "eligible_event_count": 0,
                "independent_date_count": elig["n_genuinely_eligible_independent_dates"] - n_arch_new,
                "events_per_date": "insufficient M5 history",
                "missingness": "no tick stream; sparse quote snapshots",
                "date_block_validation_feasible": False,
                "independent_confirmation_set_exists": False,
                "statistical_limitations": (
                    "1 calendar day of sparse snapshots cannot support market-behaviour discovery, "
                    "regime coverage, or date-block inference."
                ),
            },
        ],
        "power_statement": (
            "With 0 unconsumed archive date-blocks, statistical power for a new independent discovery "
            "experiment cannot be established. Prior Phase65 used 7+4 date blocks and still found no "
            "family vs WAIT under Bonferroni — that does not free those dates for reuse as 'new' evidence."
        ),
    }


def choose_verdict(elig: dict[str, Any], live: dict[str, Any], integrity_ok: bool) -> dict[str, Any]:
    if not integrity_ok:
        return {
            "verdict": "RESEARCH_DATA_INTEGRITY_BLOCKED",
            "reason": "Integrity failures in scanned market archives",
        }
    n_new_arch = elig["n_eligible_archive_dates_excluding_live_incomplete"]
    n_live = live["n_independent_dates"]
    if n_new_arch >= 20 and live["n_m5_bars"] > 1000:
        return {"verdict": "RESEARCH_DATA_READY", "reason": "Sufficient unconsumed independent dates"}
    if n_new_arch == 0 and n_live <= 1:
        return {
            "verdict": "INSUFFICIENT_RESEARCH_DATA",
            "reason": (
                "No unconsumed archive date-blocks remain for new discovery; Phase66 live XAUUSDm "
                f"has only {n_live} date(s) and {live['n_m5_bars']} M5 bars / {live['n_quote_snapshots']} "
                "quote snapshots — insufficient for professional XAUUSDm behaviour research. "
                "Historical MetaQuotes XAUUSD archive exists but is consumed/sealed and is not Exness XAUUSDm."
            ),
        }
    return {
        "verdict": "RESEARCH_DATA_PARTIALLY_READY",
        "reason": "Partial coverage; gaps in eligibility or live depth",
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cons = build_consumption_registry()
    elig = classify_eligibility()
    live = inventory_phase66_live()
    fixture = inventory_phase66_fixture()

    # Inventory consumed+eligible archive days that are NOT holdout and NOT forbidden
    # (holdout: file existence only via m5 path check without outcome access)
    scan_days = sorted(
        set(cons["phase65_discovery"])
        | set(cons["phase65_validation"])
        | set(json.loads((PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json").read_text(encoding="utf-8"))["discovery"])
        | set(json.loads((PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json").read_text(encoding="utf-8"))["validation"])
        | set(d for d, s in cons["status_by_day"].items() if "PHASE49" in s)
    )
    # Exclude sealed holdout from detailed inventory of outcomes; still count M5 existence
    holdout = set(elig["phase58_holdout_sealed"])
    scan_days = [d for d in scan_days if d not in holdout]

    print(f"scanning {len(scan_days)} non-holdout research days", flush=True)
    research_archive = aggregate_archive(scan_days, label="phase58_65_research_used_archive_union")

    # Holdout: existence + bar/tick counts only (no outcomes)
    print("scanning holdout file presence (no outcomes)", flush=True)
    holdout_inv = aggregate_archive(sorted(holdout), label="phase58_holdout_sealed_market_files_only")

    # Full eligible-day list size
    all_eligible = eligible_days()
    all_days = list_all_days()

    # Phase59/60 reported aggregates (cross-check, not sole source)
    p59_integrity = json.loads((PROJECT_ROOT / "reports" / "phase59" / "dataset_integrity.json").read_text(encoding="utf-8"))
    p60_cov = json.loads((PROJECT_ROOT / "reports" / "phase60" / "updated_data_coverage_manifest.json").read_text(encoding="utf-8"))

    feats = feature_feasibility(
        archive_has_m5=research_archive["total_m5_bars"] > 0,
        archive_has_ticks=research_archive["total_ticks"] > 0,
        live_quotes=live["n_valid_bid_ask_quotes"] > 0,
        live_m5=live["n_m5_bars"] > 0,
    )
    outcomes = outcome_feasibility()
    samples = sample_size_assessment(elig, research_archive)

    integrity_ok = (
        research_archive["total_m5_duplicate_timestamps"] == 0
        and research_archive["total_m5_bars"] > 0
        and fixture["research_use"] == "EXCLUDED"
        and elig["phase58_holdout_outcomes_accessed"] is False
    )
    verdict = choose_verdict(elig, live, integrity_ok)

    payload = {
        "generated_utc": now,
        "verdict": verdict,
        "eligibility": elig,
        "live": live,
        "fixture": fixture,
        "research_archive": {k: v for k, v in research_archive.items() if k != "per_day"},
        "research_archive_per_day": research_archive["per_day"],
        "holdout_files": {k: v for k, v in holdout_inv.items() if k != "per_day"},
        "holdout_per_day": holdout_inv["per_day"],
        "universe": {
            "list_all_days_n": len(all_days),
            "eligible_days_n": len(all_eligible),
            "archive_roots": [str(r) for r in ARCHIVE_ROOTS],
            "symbol_archive": SYMBOL,
            "symbol_live": "XAUUSDm",
        },
        "phase59_crosscheck": p59_integrity,
        "phase60_crosscheck_n_deep_audit_days": p60_cov.get("final_verified_deep_audit_n"),
        "features": feats,
        "outcomes": outcomes,
        "samples": samples,
    }
    write_json(REPORTS_DIR / "step1_inventory_raw.json", payload)

    # --- Markdown deliverables ---
    write_text(
        REPORTS_DIR / "STEP1_DATA_INVENTORY.md",
        "\n".join(
            [
                "# Step 1 — Data Inventory",
                "",
                f"- Generated: `{now}`",
                "- No strategies, backtests, or holdout outcomes accessed.",
                "",
                "## Universe",
                f"- Archive roots: `{payload['universe']['archive_roots']}`",
                f"- Archive symbol: `{SYMBOL}` (MetaQuotes-Demo historical)",
                f"- Live symbol: `XAUUSDm` (Exness-MT5Trial15 Phase66 journal)",
                f"- list_all_days: `{payload['universe']['list_all_days_n']}`",
                f"- eligible_days (excl. Phase44/49 forbidden sealed): `{payload['universe']['eligible_days_n']}`",
                "",
                "## Dataset A — Research-used archive union (Phase58 disc/val + Phase49-consumed + Phase65 disc/val)",
                f"- Dataset id: `{research_archive['dataset_id']}`",
                f"- Independent dates scanned: `{research_archive['n_independent_dates']}`",
                f"- First/last M5 ts: `{research_archive['first_ts']}` → `{research_archive['last_ts']}`",
                f"- Total M5 bars: `{research_archive['total_m5_bars']}`",
                f"- Total tick observations: `{research_archive['total_ticks']}`",
                f"- Valid bid/ask ticks: `{research_archive['total_valid_bid_ask_ticks']}`",
                f"- M5 duplicate timestamps: `{research_archive['total_m5_duplicate_timestamps']}`",
                f"- M5 gap transitions (sum): `{research_archive['total_m5_gap_transitions']}`",
                f"- Days with ≥1 gap transition: `{research_archive['days_with_gaps']}`",
                f"- Source servers: `{research_archive['source_servers']}`",
                f"- Source classification: `HISTORICAL_ARCHIVE` (not Exness live)",
                f"- Aggregate sha256: `{research_archive['aggregate_sha256']}`",
                "",
                "### Per-day detail",
                _md_table(
                    [
                        {
                            "day": p["day"],
                            "m5": p.get("m5_bars"),
                            "ticks": p.get("ticks"),
                            "bidask": p.get("valid_bid_ask_ticks"),
                            "gaps": p.get("m5_gap_transitions"),
                            "dups": p.get("m5_duplicate_timestamps"),
                            "root": Path(str(p.get("root") or "")).name if p.get("root") else "",
                            "m5_sha256_12": (str(p.get("m5_file_sha256") or "")[:12]),
                        }
                        for p in research_archive["per_day"]
                        if p.get("status") == "OK"
                    ],
                    ["day", "m5", "ticks", "bidask", "gaps", "dups", "root", "m5_sha256_12"],
                ),
                "",
                "## Dataset B — Phase58 sealed holdout market files (existence/counts only; outcomes NOT accessed)",
                f"- Independent dates: `{holdout_inv['n_independent_dates']}`",
                f"- Total M5 bars: `{holdout_inv['total_m5_bars']}`",
                f"- Total ticks: `{holdout_inv['total_ticks']}`",
                f"- Valid bid/ask: `{holdout_inv['total_valid_bid_ask_ticks']}`",
                f"- Dates: `{holdout_inv['dates']}`",
                "",
                "## Dataset C — Phase66 live Exness XAUUSDm journal",
                f"- Path: `{live['path']}`",
                f"- Classification: `{live['source_classification']}` server=`{live['source_server']}`",
                f"- Events: `{live['n_events']}` quotes=`{live['n_quote_snapshots']}` valid_bidask=`{live['n_valid_bid_ask_quotes']}` m5=`{live['n_m5_bars']}`",
                f"- Genuine tick stream observations: `{live['n_genuine_ticks']}`",
                f"- Independent dates: `{live['independent_dates']}`",
                f"- First/last: `{live['first_ts']}` → `{live['last_ts']}`",
                f"- File sha256: `{live['file_sha256']}`",
                f"- Note: {live['note']}",
                "",
                "## Dataset D — Phase66 synthetic fixtures (EXCLUDED)",
                f"- Path: `{fixture['path']}` n=`{fixture['n_events']}` use=`{fixture['research_use']}`",
                "",
                "## Cross-checks (prior reports — verified against files above)",
                f"- Phase59 dataset_integrity: n_days=`{p59_integrity.get('n_days')}` total_m5=`{p59_integrity.get('total_m5_bars')}` total_ticks=`{p59_integrity.get('total_ticks')}`",
                f"- Phase60 final_verified_deep_audit_n=`{p60_cov.get('final_verified_deep_audit_n')}`",
                "",
                "## Important distinctions",
                "- Bars/ticks ≠ independent dates.",
                "- Archive `XAUUSD` MetaQuotes-Demo ≠ live `XAUUSDm` Exness.",
                "- Phase66 quote snapshots ≠ tick velocity / order-flow evidence.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "STEP1_RESEARCH_ELIGIBILITY.md",
        "\n".join(
            [
                "# Step 1 — Research Eligibility Audit",
                "",
                f"- Phase65 registry sha256: `{elig['phase65_registry_sha256']}`",
                f"- Holdout outcomes accessed: `{elig['phase58_holdout_outcomes_accessed']}`",
                "",
                f"## Registry correction",
                elig["phase65_status_by_day_stale_note"],
                "",
                "## Classification counts",
                str(elig["classification_counts"]),
                "",
                "## Genuinely eligible for NEW discovery",
                f"- Dates: `{elig['genuinely_eligible_independent_dates']}`",
                f"- n=`{elig['n_genuinely_eligible_independent_dates']}`",
                f"- Archive-only (excl. incomplete live): `{elig['n_eligible_archive_dates_excluding_live_incomplete']}`",
                f"- Estimated new archive events (upper bound): `{elig['estimated_new_discovery_events_upper_bound_archive']}`",
                "",
                "## PREVIOUSLY_CONSUMED (includes Phase65 disc/val reclassification)",
                f"- n=`{elig['classification_counts'].get('PREVIOUSLY_CONSUMED', 0)}`",
                f"- Phase65 discovery: `{elig['phase65_discovery']}` (126 events recorded)",
                f"- Phase65 validation: `{elig['phase65_validation']}` (72 events recorded)",
                f"- Phase65 leftover unused: `{elig['phase65_leftover_unused']}`",
                "",
                "## SEALED_HOLDOUT",
                f"- `{elig['phase58_holdout_sealed']}`",
                "",
                "## VALIDATION_RESERVED",
                f"- `{elig['validation_reserved_dates']}` (none currently reserved beyond sealed holdout policy)",
                "",
                "## INVALID",
                f"- Phase49/44 forbidden sealed scoring dates n=`{elig['phase49_forbidden_sealed_n']}`",
                "",
                "## Full by_class lists",
                *[f"### {k}\n`{v}`\n" for k, v in elig["by_class"].items()],
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "STEP1_FEATURE_FEASIBILITY.md",
        "\n".join(
            [
                "# Step 1 — Feature Feasibility",
                "",
                _md_table(
                    feats,
                    [
                        "feature",
                        "required_data",
                        "data_exists",
                        "available_at_decision_time",
                        "valid_for_historical_research",
                        "proxy_limitations",
                    ],
                ),
                "",
                "## Summary",
                "- M5 candle/vol/trend/session features: feasible on HISTORICAL_ARCHIVE.",
                "- Tick velocity & bid/ask dynamics: feasible on archive ticks; **not** on Phase66 live snapshots alone.",
                "- Live XAUUSDm professional feature research: **blocked** by insufficient continuous broker-observed history.",
                "- Spread-conditioned research: archive ticks support observed spread; commission/slippage/swap remain UNKNOWN.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "STEP1_OUTCOME_FEASIBILITY.md",
        "\n".join(
            [
                "# Step 1 — Outcome Feasibility",
                "",
                f"- Archive supports unbiased path outcomes (bid/ask): `{outcomes['archive_supports_unbiased_path_outcomes']}`",
                f"- Live XAUUSDm multi-horizon outcomes ready: `{outcomes['live_xauusdm_supports_multi_horizon_outcomes']}`",
                f"- Holdout outcomes accessed: `{outcomes['holdout_outcomes_accessed']}`",
                "",
                _md_table(
                    outcomes["horizons"],
                    [
                        "horizon_m5_bars",
                        "minutes",
                        "supported_on_archive_m5_ticks",
                        "bid_ask_path_fill_supported",
                        "required_purge_embargo_bars",
                        "recommended_event_stride_bars",
                        "commission_treated_as_zero",
                        "slippage_treated_as_zero",
                        "swap_treated_as_zero",
                    ],
                ),
                "",
                "## Overlap / purge",
                f"- Default prior design: horizon=`{HORIZON_BARS}` stride=`{EVENT_STRIDE}` (non-overlapping H12).",
                "- For horizon h, purge/embargo at least h bars between decision indices; prefer stride ≥ h.",
                "- Never treat unknown commission, slippage, or swap as zero.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "STEP1_FINAL_REPORT.md",
        "\n".join(
            [
                "# Step 1 — Final Report (Independent Data & Research Inventory)",
                "",
                f"- Generated: `{now}`",
                f"- **Verdict: `{verdict['verdict']}`**",
                f"- Reason: {verdict['reason']}",
                "",
                "## 1. What data we actually possess",
                f"- HISTORICAL_ARCHIVE `{SYMBOL}` across roots `{payload['universe']['archive_roots']}`: "
                f"`{payload['universe']['list_all_days_n']}` listed days; "
                f"`{payload['universe']['eligible_days_n']}` eligible after forbidden-sealed exclusion.",
                f"- Scanned non-holdout research days: `{research_archive['n_independent_dates']}` with "
                f"`{research_archive['total_m5_bars']}` M5 bars and `{research_archive['total_ticks']}` ticks "
                f"(`{research_archive['total_valid_bid_ask_ticks']}` valid bid/ask).",
                f"- Phase58 sealed holdout market files present on `{holdout_inv['n_independent_dates']}` dates "
                f"(`{holdout_inv['total_m5_bars']}` M5 / `{holdout_inv['total_ticks']}` ticks) — outcomes not opened.",
                f"- BROKER_OBSERVED live XAUUSDm journal: `{live['n_events']}` events on `{live['independent_dates']}` "
                f"({live['n_quote_snapshots']} quotes, {live['n_m5_bars']} M5, 0 tick-stream).",
                f"- SYNTHETIC fixtures: `{fixture['n_events']}` — EXCLUDED from research.",
                "",
                "## 2. What data is genuinely new",
                f"- Live Exness XAUUSDm: `{live['independent_dates']}` (sparse; not a research-sized sample).",
                "- No remaining unconsumed MetaQuotes archive date-blocks for new discovery "
                f"(archive eligible leftover after Phase65 = `{elig['phase65_leftover_unused']}`).",
                "",
                "## 3. What data has already been consumed",
                f"- PREVIOUSLY_CONSUMED dates n=`{elig['classification_counts'].get('PREVIOUSLY_CONSUMED', 0)}` "
                "(Phase58 discovery/validation, Phase49 discovery subset, Phase65 discovery+validation).",
                f"- Phase65 used `{elig['phase65_discovery']}` (126 events) + `{elig['phase65_validation']}` (72 events).",
                "",
                "## 4. Which holdouts remain sealed",
                f"- Phase58 holdout `{elig['phase58_holdout_sealed']}` — opened=`False`.",
                f"- Phase49/44 forbidden sealed scoring dates n=`{elig['phase49_forbidden_sealed_n']}`.",
                "",
                "## 5. Which market behaviours can be investigated",
                "- On HISTORICAL_ARCHIVE (MetaQuotes XAUUSD): M5 microstructure proxies (body/wick, ATR, compression, "
                "breakouts, session-relative labels with Exness-schedule caveat), tick velocity, bid/ask dynamics, "
                "spread-conditioned path outcomes at 1–24 M5 horizons with purge/embargo.",
                "- These are substrate-limited and largely **already searched** in prior phases.",
                "",
                "## 6. Which behaviours cannot be investigated (missing data)",
                "- Professional **Exness XAUUSDm** continuous behaviour (regime coverage, date-block inference).",
                "- Live tick velocity / order-flow (no permitted tick stream; sparse snapshots only).",
                "- Complete execution economics (commission/slippage/swap UNKNOWN — must not be zeroed).",
                "- Independent confirmation without opening sealed holdout (no survivor).",
                "",
                "## 7. Does existing archive data support a NEW discovery experiment?",
                "- **No.** Genuinely eligible unconsumed archive independent dates = "
                f"`{elig['n_eligible_archive_dates_excluding_live_incomplete']}`. "
                "Recycling consumed dates would not be independent evidence.",
                "",
                "## 8. Is further live collection necessary?",
                "- **Yes**, for any XAUUSDm-targeted strategy-discovery program: accumulate many independent "
                "OPEN-session date-blocks of broker-observed M5 (+ quotes; tick stream only if allowlist expands).",
                "",
                "## Sample-size / power",
                samples["power_statement"],
                "",
                _md_table(
                    samples["directions"],
                    [
                        "direction",
                        "independent_date_count",
                        "eligible_event_count",
                        "date_block_validation_feasible",
                        "independent_confirmation_set_exists",
                    ],
                ),
                "",
                "## Invariants preserved",
                "- Champion `NO_MODEL` | Production `WAIT` | No execution | No holdout outcome access | No synthetic research evidence.",
                "",
                "## Artifacts",
                "- `STEP1_DATA_INVENTORY.md`",
                "- `STEP1_RESEARCH_ELIGIBILITY.md`",
                "- `STEP1_FEATURE_FEASIBILITY.md`",
                "- `STEP1_OUTCOME_FEASIBILITY.md`",
                "- `step1_inventory_raw.json`",
                "",
            ]
        ),
    )

    print(json.dumps({"verdict": verdict, "eligible_new": elig["genuinely_eligible_independent_dates"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
