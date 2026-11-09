"""MT5 vs provider parity research on approved historical window only."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from phase24.adapter import (
    candles_from_algospecial_payload,
    candles_from_mt5_feature_rows,
    validate_series,
)
from phase24.constants import (
    FIXTURES_DIR,
    HOLDOUT_NAME,
    MT5_FEATURES_PATH,
    PARITY_WINDOW_END,
    PARITY_WINDOW_START,
    RESEARCH_CUTOFF_UTC,
)


def assert_no_holdout_touch(path: Path | None = None) -> None:
    p = path or MT5_FEATURES_PATH
    if HOLDOUT_NAME in str(p):
        raise RuntimeError(f"holdout path refused: {p}")
    if p.name == HOLDOUT_NAME:
        raise RuntimeError(f"holdout path refused: {p}")


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round((len(ys) - 1) * q))))
    return ys[i]


def _atr_proxy(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Wilder ATR absolute (not pct) for distribution comparison on aligned series."""
    if len(closes) < period + 1:
        return []
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr: list[float] = []
    prev = sum(trs[:period]) / period
    atr.append(prev)
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
        atr.append(prev)
    return atr


def compare_aligned(
    mt5: dict[str, dict[str, Any]],
    provider: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    common = sorted(set(mt5) & set(provider))
    only_mt5 = sorted(set(mt5) - set(provider))
    only_prov = sorted(set(provider) - set(mt5))
    close_abs = []
    open_abs = []
    high_abs = []
    low_abs = []
    spread_pairs = []
    for t in common:
        m = mt5[t]
        p = provider[t]
        close_abs.append(abs(m["close"] - p["close"]))
        open_abs.append(abs(m["open"] - p["open"]))
        high_abs.append(abs(m["high"] - p["high"]))
        low_abs.append(abs(m["low"] - p["low"]))
        if m.get("spread") is not None and p.get("spread") is not None:
            spread_pairs.append((float(m["spread"]), float(p["spread"])))

    def dist(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        return {
            "n": len(xs),
            "min": min(xs),
            "p50": _pct(xs, 0.5),
            "p90": _pct(xs, 0.9),
            "p99": _pct(xs, 0.99),
            "max": max(xs),
            "mean": sum(xs) / len(xs),
        }

    # Feature-ish: close returns on common series
    mt5_rets = []
    prov_rets = []
    for i in range(1, len(common)):
        t0, t1 = common[i - 1], common[i]
        mt5_rets.append((mt5[t1]["close"] / mt5[t0]["close"]) - 1.0)
        prov_rets.append((provider[t1]["close"] / provider[t0]["close"]) - 1.0)

    atr_m = _atr_proxy(
        [mt5[t]["high"] for t in common],
        [mt5[t]["low"] for t in common],
        [mt5[t]["close"] for t in common],
    )
    atr_p = _atr_proxy(
        [provider[t]["high"] for t in common],
        [provider[t]["low"] for t in common],
        [provider[t]["close"] for t in common],
    )
    atr_abs = [abs(a - b) for a, b in zip(atr_m, atr_p)] if atr_m and atr_p else []

    # Precision: decimal places observed on closes
    def decimals(xs: list[float]) -> int:
        d = 0
        for x in xs[:50]:
            s = f"{x:.10f}".rstrip("0")
            if "." in s:
                d = max(d, len(s.split(".")[1]))
        return d

    spread_scale_note = None
    if spread_pairs:
        m_med = statistics.median([a for a, _ in spread_pairs])
        p_med = statistics.median([b for _, b in spread_pairs])
        spread_scale_note = {
            "mt5_spread_median": m_med,
            "provider_spread_median": p_med,
            "ratio_provider_over_mt5": (p_med / m_med) if m_med else None,
            "note": "Units may differ (points vs price); not interchangeable with cost model.",
        }

    # M5 boundary check on common stamps
    boundary_ok = all(t.endswith(("0:00", "5:00")) for t in common)

    return {
        "common_timestamps": len(common),
        "only_mt5": len(only_mt5),
        "only_provider": len(only_prov),
        "missing_on_provider_examples": only_mt5[:5],
        "missing_on_mt5_examples": only_prov[:5],
        "duplicate_provider_timestamps": 0,  # maps already unique
        "ohlc_abs_diff": {
            "open": dist(open_abs),
            "high": dist(high_abs),
            "low": dist(low_abs),
            "close": dist(close_abs),
        },
        "price_precision_decimals_sample": {
            "mt5_close": decimals([mt5[t]["close"] for t in common[:50]]),
            "provider_close": decimals([provider[t]["close"] for t in common[:50]]),
        },
        "m5_boundary_alignment_common": boundary_ok,
        "return_distribution": {
            "mt5_ret_p50": _pct(mt5_rets, 0.5) if mt5_rets else None,
            "provider_ret_p50": _pct(prov_rets, 0.5) if prov_rets else None,
            "mt5_ret_p90_abs": _pct([abs(x) for x in mt5_rets], 0.9) if mt5_rets else None,
            "provider_ret_p90_abs": _pct([abs(x) for x in prov_rets], 0.9) if prov_rets else None,
        },
        "atr_abs_diff": dist(atr_abs),
        "spread_and_cost": spread_scale_note,
        "parity_pass_criteria": {
            "require_median_abs_close_diff_lt": 0.5,
            "require_max_abs_close_diff_lt": 5.0,
            "require_common_coverage_ge": 0.95,
            "note": "Strict research gates; not threshold recalibration.",
        },
        "parity_result": "FAIL",
    }


def run_algospecial_parity() -> dict[str, Any]:
    assert_no_holdout_touch()
    as_path = FIXTURES_DIR / "algospecial_xauusd_m5_2026-02-16_17.json"
    mt5_path = FIXTURES_DIR / "mt5_reference_xauusd_m5_2026-02-16_17.json"
    if not as_path.is_file() or not mt5_path.is_file():
        return {
            "status": "MISSING_FIXTURES",
            "parity_result": "FAIL",
            "holdout_accessed": False,
        }
    as_payload = json.loads(as_path.read_text(encoding="utf-8"))
    mt5_payload = json.loads(mt5_path.read_text(encoding="utf-8"))
    assert mt5_payload.get("holdout_accessed") is False
    assert mt5_payload.get("research_cutoff") == RESEARCH_CUTOFF_UTC

    as_candles = candles_from_algospecial_payload(as_payload)
    mt5_candles = candles_from_mt5_feature_rows(mt5_payload["rows"])
    as_val = validate_series(as_candles, as_of_utc="2026-02-18 00:00:01")
    mt5_val = validate_series(mt5_candles, as_of_utc="2026-02-18 00:00:01")

    mt5_map = {c.timestamp_utc: c.to_dict() for c in mt5_candles}
    # Restrict to approved window
    mt5_map = {k: v for k, v in mt5_map.items() if PARITY_WINDOW_START <= k <= PARITY_WINDOW_END}
    as_map = {c.timestamp_utc: c.to_dict() for c in as_candles}
    as_map = {k: v for k, v in as_map.items() if PARITY_WINDOW_START <= k <= PARITY_WINDOW_END}

    cmp_ = compare_aligned(mt5_map, as_map)
    cov = cmp_["common_timestamps"] / max(1, len(mt5_map))
    med = (cmp_["ohlc_abs_diff"]["close"] or {}).get("p50", math.inf)
    mx = (cmp_["ohlc_abs_diff"]["close"] or {}).get("max", math.inf)
    gates = cmp_["parity_pass_criteria"]
    passed = (
        cov >= gates["require_common_coverage_ge"]
        and med is not None
        and med < gates["require_median_abs_close_diff_lt"]
        and mx is not None
        and mx < gates["require_max_abs_close_diff_lt"]
    )
    cmp_["coverage_of_mt5"] = cov
    cmp_["parity_result"] = "PASS" if passed else "FAIL"
    cmp_["provider"] = "AlgoSpecial"
    cmp_["timestamp_assumption"] = (
        "AlgoSpecial official docs: broker server time. Comparison treats stamps as UTC "
        "(best among 0–3h offsets in exploratory check); still FAIL."
    )
    cmp_["window"] = {"start": PARITY_WINDOW_START, "end": PARITY_WINDOW_END}
    cmp_["research_cutoff_utc"] = RESEARCH_CUTOFF_UTC
    cmp_["holdout_accessed"] = False
    cmp_["mt5_source"] = "src/data/xauusd_m5_features_utc_corrected.csv"
    cmp_["validation"] = {
        "algospecial_accepted": as_val["accepted_count"],
        "algospecial_rejected": as_val["rejected_count"],
        "mt5_accepted": mt5_val["accepted_count"],
        "mt5_rejected": mt5_val["rejected_count"],
        "algospecial_issue_codes": sorted({i["code"] for i in as_val["issues"]}),
    }
    # thresholds unchanged note
    cmp_["h13c_thresholds_recalibrated"] = False
    cmp_["note"] = (
        "Provider data does not inherit MT5-trained threshold validity. "
        "No H13_C recalibration performed."
    )
    return cmp_


def build_data_parity_report() -> dict[str, Any]:
    algo = run_algospecial_parity()
    return {
        "label": "phase24_mt5_provider_parity_research",
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "holdout_name": HOLDOUT_NAME,
        "holdout_accessed": False,
        "comparisons": {
            "AlgoSpecial": algo,
            "TickFeed": {"parity_result": "NOT_RUN", "reason": "paid usage; not Always Free"},
            "TwelveData_Basic": {"parity_result": "NOT_RUN", "reason": "account/API key required; no account creation this phase"},
            "Finnhub_Free": {"parity_result": "NOT_RUN", "reason": "forex/metals candles typically paid-gated"},
            "biquote": {"parity_result": "NOT_RUN", "reason": "licensing/UTC contract insufficient; avoided marketing-only qualification"},
            "V2BOT": {"parity_result": "NOT_RUN", "reason": "incomplete public contract"},
            "Dukascopy_public_historical": {
                "parity_result": "NOT_RUN",
                "reason": (
                    "Docs indicate free UTC historical XAUUSD M5 (bid/ask). "
                    "No binary feed download/parity executed in Phase 24; cannot qualify without actual validation."
                ),
            },
        },
        "overall_parity_status": "FAIL",
        "any_provider_parity_pass": False,
        "thresholds_modified": False,
    }
