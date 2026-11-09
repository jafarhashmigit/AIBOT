"""Frozen-tolerance MT5 vs Dukascopy historical parity."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from phase14.h1_trend import build_h1_series, h1_trend_at
from phase14.strategy import decide_h13c
from phase16a.constants import FROZEN_CUTS
from phase16a.features import features_at_index
from phase24.parity import run_algospecial_parity
from phase25.candles import build_and_validate_day
from phase25.constants import (
    FROZEN_TOLERANCES,
    HOLDOUT_NAME,
    MT5_FEATURES_PATH,
    OHLC_RECOMPUTE_FEATURES,
    PARITY_DAYS,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
)
from phase25.features_recompute import recompute_row_features


def assert_no_holdout(path: Path | None = None) -> None:
    p = path or MT5_FEATURES_PATH
    if HOLDOUT_NAME in str(p) or p.name == HOLDOUT_NAME:
        raise RuntimeError(f"holdout refused: {p}")


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round((len(ys) - 1) * q))))
    return ys[i]


def _dist(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0}
    return {
        "n": len(xs),
        "min": min(xs),
        "median": _pct(xs, 0.5),
        "p95": _pct(xs, 0.95),
        "max": max(xs),
        "mean": sum(xs) / len(xs),
    }


def load_mt5_days(days: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    assert_no_holdout()
    wanted = set(days)
    out: dict[str, dict[str, dict[str, float]]] = {d: {} for d in days}
    with MT5_FEATURES_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            t = row["time"]
            if t > RESEARCH_CUTOFF_UTC:
                break
            day = t[:10]
            if day not in wanted:
                continue
            out[day][t] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "spread": float(row["spread"]) if row.get("spread") not in (None, "") else float("nan"),
                "atr_14": float(row["atr_14"]) if row.get("atr_14") not in (None, "") else float("nan"),
                "close_to_ema_20": float(row["close_to_ema_20"])
                if row.get("close_to_ema_20") not in (None, "")
                else float("nan"),
                "ema_9_20_spread": float(row["ema_9_20_spread"])
                if row.get("ema_9_20_spread") not in (None, "")
                else float("nan"),
            }
            # stash all OHLC-recompute source fields from MT5 row when present
            for k in OHLC_RECOMPUTE_FEATURES:
                if k in row and row[k] not in (None, ""):
                    try:
                        out[day][t][k] = float(row[k])
                    except ValueError:
                        pass
    return out


def load_mt5_h1() -> list[dict]:
    path = MT5_FEATURES_PATH.parent / "xauusd_h1_mt5.csv"
    assert_no_holdout(path)
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            t = row["time"]
            if t > RESEARCH_CUTOFF_UTC:
                break
            rows.append({"time": t, "close": float(row["close"])})
    return rows


def load_day_ticks(day: str) -> list[dict[str, Any]]:
    path = RAW_DIR / day / "ticks_decoded.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compare_day(
    day: str,
    mt5_map: dict[str, dict[str, float]],
    dukas_candles: list[Any],
    *,
    h1_series: list[dict],
) -> dict[str, Any]:
    dukas_map = {c.timestamp_utc: c.to_dict() for c in dukas_candles}
    common = sorted(set(mt5_map) & set(dukas_map))
    only_mt5 = sorted(set(mt5_map) - set(dukas_map))
    only_dk = sorted(set(dukas_map) - set(mt5_map))

    close_abs = [abs(mt5_map[t]["close"] - dukas_map[t]["close"]) for t in common]
    open_abs = [abs(mt5_map[t]["open"] - dukas_map[t]["open"]) for t in common]
    high_abs = [abs(mt5_map[t]["high"] - dukas_map[t]["high"]) for t in common]
    low_abs = [abs(mt5_map[t]["low"] - dukas_map[t]["low"]) for t in common]
    spread_abs = []
    for t in common:
        ms = mt5_map[t].get("spread")
        ds = dukas_map[t].get("spread")
        if ms is None or ds is None or (isinstance(ms, float) and math.isnan(ms)):
            continue
        # MT5 spread field is broker points; Dukascopy spread is price diff — report both raw
        spread_abs.append({"mt5_spread_field": ms, "dukas_ask_bid": ds})

    # Recompute features on contiguous dukas day bars (and MT5 day bars) for OHLC-derived set
    mt5_bars = [{"timestamp_utc": t, **mt5_map[t]} for t in sorted(mt5_map)]
    dk_bars = [{"timestamp_utc": t, **dukas_map[t]} for t in sorted(dukas_map)]
    mt5_feat = {r["time"]: r for r in recompute_row_features(mt5_bars)}
    dk_feat = {r["time"]: r for r in recompute_row_features(dk_bars)}
    feat_common = sorted(set(mt5_feat) & set(dk_feat))
    feature_diffs: dict[str, dict[str, Any]] = {}
    for name in OHLC_RECOMPUTE_FEATURES:
        diffs = []
        for t in feat_common:
            a = mt5_feat[t].get(name)
            b = dk_feat[t].get(name)
            if a is None or b is None:
                continue
            diffs.append(abs(float(a) - float(b)))
        feature_diffs[name] = _dist(diffs)

    # ATR from recomputed
    atr_diffs = []
    for t in feat_common:
        a = mt5_feat[t].get("atr_14")
        b = dk_feat[t].get("atr_14")
        if a is None or b is None:
            continue
        atr_diffs.append(abs(float(a) - float(b)))

    # H13_C parity: features from each source; shared MT5 H1 context
    cuts = dict(FROZEN_CUTS)
    agree = 0
    compared = 0
    disagree_examples = []
    # Need sequential closes for features_at_index
    mt5_times = sorted(mt5_map)
    dk_times = sorted(dukas_map)
    mt5_closes = [mt5_map[t]["close"] for t in mt5_times]
    dk_closes = [dukas_map[t]["close"] for t in dk_times]
    mt5_idx = {t: i for i, t in enumerate(mt5_times)}
    dk_idx = {t: i for i, t in enumerate(dk_times)}
    for t in common:
        decision_time = t  # bar open; strategy historically uses decision at close — use open+5m
        # Match shadow convention: decision at bar close
        # close = open + 5m
        from datetime import datetime, timedelta

        dec = (datetime.strptime(t, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        h1 = h1_trend_at(h1_series, dec)
        fm = features_at_index(mt5_closes, mt5_idx[t])
        fd = features_at_index(dk_closes, dk_idx[t])
        if not fm or not fd or not h1:
            continue
        am, _ = decide_h13c(fm, h1, cuts)
        ad, _ = decide_h13c(fd, h1, cuts)
        compared += 1
        if am == ad:
            agree += 1
        elif len(disagree_examples) < 5:
            disagree_examples.append({"time": t, "mt5_action": am, "dukas_action": ad})

    coverage = len(common) / max(1, len(mt5_map))
    close_dist = _dist(close_abs)
    tol = FROZEN_TOLERANCES
    gates = {
        "coverage_ok": coverage >= tol["min_common_coverage_of_mt5"],
        "median_close_ok": close_dist.get("n", 0) > 0 and close_dist["median"] <= tol["median_abs_close_usd"],
        "p95_close_ok": close_dist.get("n", 0) > 0 and close_dist["p95"] <= tol["p95_abs_close_usd"],
        "max_close_ok": close_dist.get("n", 0) > 0 and close_dist["max"] <= tol["max_abs_close_usd"],
        "atr_median_ok": (not atr_diffs)
        or _pct(atr_diffs, 0.5) <= tol["median_abs_atr14_usd"],
        "h13c_ok": compared == 0
        or (agree / compared) >= tol["h13c_action_agreement_min"],
    }
    day_pass = all(gates.values())

    return {
        "day": day,
        "mt5_bars": len(mt5_map),
        "dukas_bars": len(dukas_map),
        "common": len(common),
        "only_mt5": len(only_mt5),
        "only_dukas": len(only_dk),
        "coverage_of_mt5": coverage,
        "duplicates_dukas": 0,
        "ohlc_abs_diff_usd": {
            "open": _dist(open_abs),
            "high": _dist(high_abs),
            "low": _dist(low_abs),
            "close": close_dist,
        },
        "spread_note": {
            "n_pairs": len(spread_abs),
            "mt5_spread_field_median": _pct([p["mt5_spread_field"] for p in spread_abs], 0.5)
            if spread_abs
            else None,
            "dukas_ask_minus_bid_median": _pct([p["dukas_ask_bid"] for p in spread_abs], 0.5)
            if spread_abs
            else None,
            "note": "MT5 spread column is broker points; Dukascopy spread is ask-bid price — not directly comparable.",
        },
        "atr14_abs_diff": _dist(atr_diffs),
        "ohlc_recompute_feature_abs_diff": feature_diffs,
        "feature_columns_compared": len(OHLC_RECOMPUTE_FEATURES),
        "csv_total_columns_reference": 75,
        "h13c": {
            "compared": compared,
            "agree": agree,
            "agreement_rate": (agree / compared) if compared else None,
            "disagree_examples": disagree_examples,
            "shared_h1_context": "mt5_h1",
            "thresholds_recalibrated": False,
        },
        "gates": gates,
        "day_pass": day_pass,
        "missing_examples_mt5": only_mt5[:5],
        "missing_examples_dukas": only_dk[:5],
    }


def evaluate_historical_parity(*, sides: tuple[str, ...] = ("mid", "bid", "ask")) -> dict[str, Any]:
    """Evaluate using FROZEN_TOLERANCES declared before this run."""
    assert_no_holdout()
    tol = dict(FROZEN_TOLERANCES)
    h1_series = build_h1_series(load_mt5_h1())
    mt5_by_day = load_mt5_days(PARITY_DAYS)
    primary_side = tol["price_side_for_primary"]
    per_side: dict[str, Any] = {}

    for side in sides:
        day_reports = []
        for day in PARITY_DAYS:
            ticks = load_day_ticks(day)
            built = build_and_validate_day(ticks, day=day, side=side)  # type: ignore[arg-type]
            day_reports.append(
                compare_day(day, mt5_by_day.get(day, {}), built["candles"], h1_series=h1_series)
                | {"build": {k: built[k] for k in ("n_ticks", "n_m5", "accepted", "rejected", "issue_codes")}}
            )
        # Aggregate primary metrics across days
        all_close_med = [d["ohlc_abs_diff_usd"]["close"].get("median") for d in day_reports if d["ohlc_abs_diff_usd"]["close"].get("n")]
        all_close_p95 = [d["ohlc_abs_diff_usd"]["close"].get("p95") for d in day_reports if d["ohlc_abs_diff_usd"]["close"].get("n")]
        all_close_max = [d["ohlc_abs_diff_usd"]["close"].get("max") for d in day_reports if d["ohlc_abs_diff_usd"]["close"].get("n")]
        coverages = [d["coverage_of_mt5"] for d in day_reports]
        side_pass = all(d["day_pass"] for d in day_reports) and len(day_reports) == len(PARITY_DAYS)
        per_side[side] = {
            "days": day_reports,
            "aggregate": {
                "min_coverage": min(coverages) if coverages else 0,
                "median_of_daily_median_abs_close": _pct(all_close_med, 0.5) if all_close_med else None,
                "max_of_daily_p95_abs_close": max(all_close_p95) if all_close_p95 else None,
                "max_of_daily_max_abs_close": max(all_close_max) if all_close_max else None,
            },
            "side_pass": side_pass,
        }

    primary = per_side.get(primary_side, {})
    # Status determination
    if not any((RAW_DIR / d / "ticks_decoded.jsonl").is_file() for d in PARITY_DAYS):
        hist_status = "DUKASCOPY_HISTORICAL_INCONCLUSIVE"
        reason = "No Dukascopy tick files present for parity days."
    elif primary.get("side_pass"):
        hist_status = "DUKASCOPY_HISTORICAL_PASS"
        reason = "All frozen gates passed on primary side across parity days."
    else:
        # Distinguish incomplete download vs clear fail
        total_ticks = sum(
            (json.loads((RAW_DIR / d / "manifest.json").read_text(encoding="utf-8")).get("tick_count", 0)
             if (RAW_DIR / d / "manifest.json").is_file()
             else 0)
            for d in PARITY_DAYS
        )
        failed_hours = 0
        for d in PARITY_DAYS:
            mp = RAW_DIR / d / "manifest.json"
            if mp.is_file():
                man = json.loads(mp.read_text(encoding="utf-8"))
                failed_hours += len(man.get("errors") or [])
        if total_ticks == 0 or failed_hours > 10:
            hist_status = "DUKASCOPY_HISTORICAL_INCONCLUSIVE"
            reason = f"Insufficient/failed downloads (ticks={total_ticks}, failed_hours={failed_hours})."
        else:
            hist_status = "DUKASCOPY_HISTORICAL_FAIL"
            reason = "Downloads present but frozen OHLC/ATR/H13_C gates not met."

    algo_ref = run_algospecial_parity()

    return {
        "frozen_tolerances": tol,
        "parity_days": PARITY_DAYS,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "holdout_accessed": False,
        "thresholds_recalibrated": False,
        "primary_side": primary_side,
        "per_side": per_side,
        "algospecial_reference": {
            "parity_result": algo_ref.get("parity_result"),
            "close_abs_diff": (algo_ref.get("ohlc_abs_diff") or {}).get("close"),
            "note": "Phase 24 failed AlgoSpecial comparison retained as reference.",
        },
        "historical_status": hist_status,
        "reason": reason,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": "WAIT",
    }
