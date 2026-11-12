"""Phase 29 historical 500-candle diagnostic (HISTORICAL_HYPOTHETICAL only).

NOT forward validation. Does not touch AGENT_SHADOW, Discord, or production.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from phase3.nplib import read_csv_dicts
from phase14.constants import FEATURES_PATH, H1_PATH
from phase14.h1_trend import build_h1_series, h1_trend_at
from phase14.strategy import decide_h13c
from phase16a.constants import FROZEN_CUTS
from phase18.constants import HORIZONS
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome
from phase26.features import compute_orthogonal_features
from phase28.frozen_vol import feature_vector_at_index, load_frozen_vol_artifact, predict_vol_and_regime
from phase28.observers import apply_high_only_policy
from phase29.constants import (
    HOLDOUT_NAME,
    OBSERVER_A,
    OBSERVER_B,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    REPORTS_DIR,
    RESEARCH_CUTOFF_UTC,
    SOURCE_HISTORICAL,
    STRATEGY_ID,
    SYMBOL,
)
from phase29.levels import planned_shadow_levels

DIAG_N = 500
DIAG_LABEL = "HISTORICAL_DIAGNOSTIC_ONLY"
NOT_FORWARD = "NOT_FORWARD_VALIDATION"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _assert_no_holdout(path: Path) -> None:
    if HOLDOUT_NAME in str(path):
        raise RuntimeError("HARD FAILURE: holdout path referenced")


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        if math.isnan(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def load_approved_m5(*, cutoff: str = RESEARCH_CUTOFF_UTC) -> dict[str, Any]:
    """Load approved feature store bars with time <= cutoff. Never opens holdout."""
    _assert_no_holdout(FEATURES_PATH)
    times: list[str] = []
    rows: list[dict] = []
    excluded = {"post_cutoff": 0, "missing_ohlc": 0}
    for row in read_csv_dicts(FEATURES_PATH):
        t = row["time"]
        if t > cutoff:
            excluded["post_cutoff"] += 1
            continue
        try:
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
        except (TypeError, ValueError, KeyError):
            excluded["missing_ohlc"] += 1
            continue
        times.append(t)
        rows.append(
            {
                "time": t,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "spread": float(row.get("spread") or 15),
                "atr_14": float(row["atr_14"]) if row.get("atr_14") not in (None, "") else float("nan"),
                "close_to_ema_20": float(row["close_to_ema_20"]),
                "ema_9_20_spread": float(row["ema_9_20_spread"]),
                "minutes_since_prev_bar": float(row.get("minutes_since_prev_bar") or 5),
                "is_after_gap": float(row.get("is_after_gap") or 0),
            }
        )
    return {
        "times": times,
        "rows": rows,
        "index": {t: i for i, t in enumerate(times)},
        "cutoff": cutoff,
        "excluded": excluded,
        "holdout_opened": False,
        "source_path": str(FEATURES_PATH),
    }


def load_approved_h1(*, cutoff: str = RESEARCH_CUTOFF_UTC) -> list[dict]:
    _assert_no_holdout(H1_PATH)
    out = []
    for row in read_csv_dicts(H1_PATH):
        t = row["time"]
        if t > cutoff:
            continue
        out.append(
            {
                "time": t,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )
    out.sort(key=lambda r: r["time"])
    return out


def select_last_n_window(m5: dict[str, Any], *, n: int = DIAG_N) -> dict[str, Any]:
    times = m5["times"]
    if len(times) < n:
        raise RuntimeError(f"insufficient approved bars for {n}-candle window: n={len(times)}")
    start_i = len(times) - n
    window_times = times[start_i:]
    assert len(window_times) == n
    assert all(t <= m5["cutoff"] for t in window_times)
    assert window_times[-1] <= m5["cutoff"]
    return {
        "n": n,
        "start_index": start_i,
        "first_candle_utc": window_times[0],
        "last_candle_utc": window_times[-1],
        "times": window_times,
    }


def _rows_as_phase18_bars(rows: list[dict]) -> list[dict]:
    """Map feature-store rows to Phase 18 bar schema (feature time = bar open)."""
    bars = []
    for r in rows:
        open_ts = r["time"]
        close_ts = _fmt(_parse(open_ts) + timedelta(minutes=5))
        bars.append(
            {
                "bar_open_timestamp_utc": open_ts,
                "bar_close_timestamp_utc": close_ts,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "spread": r.get("spread", 15),
            }
        )
    return bars


def _perf(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {
            "n": 0,
            "mean_r": None,
            "median_r": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown_r": None,
        }
    xs_s = sorted(xs)
    n = len(xs)
    mean = sum(xs) / n
    mid = n // 2
    median = xs_s[mid] if n % 2 else 0.5 * (xs_s[mid - 1] + xs_s[mid])
    wins = sum(1 for x in xs if x > 0)
    gains = sum(x for x in xs if x > 0)
    losses = sum(-x for x in xs if x < 0)
    if losses <= 0 and gains > 0:
        pf: Any = "inf"
    elif losses <= 0:
        pf = None
    else:
        pf = gains / losses
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in xs:
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return {
        "n": n,
        "mean_r": mean,
        "median_r": median,
        "win_rate": wins / n,
        "profit_factor": pf,
        "max_drawdown_r": max_dd,
    }


def _outcome_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_h: dict[str, dict[str, int]] = {
        hid: {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0, "other": 0} for hid in HORIZONS
    }
    for r in rows:
        hid = r.get("horizon_id")
        if hid not in by_h:
            continue
        st = str(r.get("status", "")).upper()
        if st in by_h[hid]:
            by_h[hid][st] += 1
        else:
            by_h[hid]["other"] += 1
    h12 = [r for r in rows if r.get("horizon_id") == "H12" and r.get("status") not in {None, "PENDING", ""}]
    rs: list[float] = []
    for r in h12:
        try:
            rs.append(float(r["realized_r"]))
        except (TypeError, ValueError, KeyError):
            continue
    return {"by_horizon": by_h, "h12": _perf(rs), "n_matured_h12": len(rs)}


def _counts(decs: list[dict]) -> dict[str, int]:
    return {
        "BUY": sum(1 for d in decs if d.get("experimental_action") == "BUY"),
        "SELL": sum(1 for d in decs if d.get("experimental_action") == "SELL"),
        "WAIT": sum(1 for d in decs if d.get("experimental_action") == "WAIT"),
        "n": len(decs),
    }


def _eval_outcomes_for_signal(
    *,
    decision: dict[str, Any],
    action: str,
    atr_val: float,
    levels: dict[str, Any],
    signal_bar_open_utc: str,
    all_bars: list[dict],
    as_of_eval: str,
) -> list[dict[str, Any]]:
    pending = create_pending_outcomes(
        {
            "decision_id": decision["decision_id"],
            "decision_timestamp_utc": decision["decision_timestamp_utc"],
            "experimental_action": action,
            "symbol": SYMBOL,
        },
        atr=float(atr_val),
        tp_level=float(levels["tp_level"]),
        sl_level=float(levels["sl_level"]),
    )
    out_rows: list[dict[str, Any]] = []
    for p in pending:
        p["experience_source"] = SOURCE_HISTORICAL
        p["signal_bar_open_utc"] = signal_bar_open_utc
        updated = evaluate_horizon_outcome(
            p,
            bars=all_bars,
            signal_bar_open_utc=signal_bar_open_utc,
            atr=float(atr_val),
            as_of_utc=as_of_eval,
        )
        updated["experience_source"] = SOURCE_HISTORICAL
        out_rows.append(updated)
    return out_rows


def run_historical_500_diagnostic(
    *,
    n: int = DIAG_N,
    cutoff: str = RESEARCH_CUTOFF_UTC,
    include_high_only: bool = True,
) -> dict[str, Any]:
    m5 = load_approved_m5(cutoff=cutoff)
    h1 = load_approved_h1(cutoff=cutoff)
    window = select_last_n_window(m5, n=n)
    start_i = window["start_index"]

    lookback = max(40, 30)
    bar_slice_start = max(0, start_i - lookback)
    all_rows = m5["rows"][bar_slice_start:]
    all_bars = _rows_as_phase18_bars(all_rows)
    abs_to_local = {bar_slice_start + j: j for j in range(len(all_bars))}

    h1_series = build_h1_series(h1)
    cuts = dict(FROZEN_CUTS)
    as_of_eval = _fmt(_parse(m5["times"][-1]) + timedelta(minutes=5) + timedelta(seconds=1))

    vol_by_abs: dict[int, dict[str, Any]] = {}
    high_only_blocker: str | None = None
    high_only_enabled = include_high_only
    if include_high_only:
        try:
            artifact = load_frozen_vol_artifact()
            feats = compute_orthogonal_features(
                {"times": m5["times"], "rows": m5["rows"]},
                h1,
            )
            for abs_i in range(start_i, len(m5["times"])):
                vec = feature_vector_at_index(feats, abs_i)
                if vec is None:
                    vol_by_abs[abs_i] = {"ok": False, "reason": "feature_nan"}
                    continue
                pred = predict_vol_and_regime(vec, artifact)
                vol_by_abs[abs_i] = {"ok": True, **pred}
        except Exception as exc:  # noqa: BLE001 — diagnostic must still produce baseline
            high_only_blocker = f"{type(exc).__name__}:{exc}"
            high_only_enabled = False

    baseline_decisions: list[dict[str, Any]] = []
    high_decisions: list[dict[str, Any]] = []
    baseline_outcomes: list[dict[str, Any]] = []
    high_outcomes: list[dict[str, Any]] = []
    buy_r: list[float] = []
    sell_r: list[float] = []
    high_buy_r: list[float] = []
    high_sell_r: list[float] = []

    for abs_i in range(start_i, len(m5["times"])):
        row = m5["rows"][abs_i]
        open_ts = row["time"]
        close_ts = _fmt(_parse(open_ts) + timedelta(minutes=5))
        # Features are as-of completed bar; H1 context at bar close (Phase 16A/28 style).
        feat = {
            "close_to_ema_20": row["close_to_ema_20"],
            "ema_9_20_spread": row["ema_9_20_spread"],
        }
        h1_ctx = h1_trend_at(h1_series, close_ts, strict_gt=True)
        action, reason = decide_h13c(feat, h1_ctx, cuts)
        local_i = abs_to_local[abs_i]
        bar = all_bars[local_i]

        levels = None
        atr_val = None
        if action in {"BUY", "SELL"}:
            try:
                atr_val = atr_at_signal(all_bars, local_i)
                levels = planned_shadow_levels(
                    side=action,
                    reference_price=float(row["close"]),
                    atr=float(atr_val),
                    spread_points=row.get("spread"),
                )
            except Exception:  # noqa: BLE001
                levels = None
                atr_val = None

        base_id = f"p29_hist_{OBSERVER_A}_{open_ts.replace(' ', 'T')}"
        baseline = {
            "decision_id": base_id,
            "event_id": base_id,
            "experience_source": SOURCE_HISTORICAL,
            "label": DIAG_LABEL,
            "not_forward_validation": True,
            "observer_id": OBSERVER_A,
            "strategy": STRATEGY_ID,
            "symbol": SYMBOL,
            "decision_timestamp_utc": close_ts,
            "signal_bar_open_utc": open_ts,
            "experimental_action": action,
            "h13c_reason": reason,
            "production_action": PRODUCTION_FINAL_ACTION,
            "final_action": PRODUCTION_FINAL_ACTION,
            "accepted": action in {"BUY", "SELL"} and levels is not None,
            "entry": None if not levels else levels["entry"],
            "tp_level": None if not levels else levels["tp_level"],
            "sl_level": None if not levels else levels["sl_level"],
            "atr": None if not levels else levels["atr"],
            "frozen_cuts_source": cuts.get("source"),
            "discord_sent": False,
            "broker_order": False,
        }
        baseline_decisions.append(baseline)

        high_dec = None
        if high_only_enabled:
            vol = vol_by_abs.get(abs_i, {"ok": False, "reason": "missing"})
            policy = apply_high_only_policy(
                h13c_action=action,
                pred_vol_regime=vol.get("pred_vol_regime"),
                vol_ok=bool(vol.get("ok")),
                vol_reason=vol.get("reason"),
            )
            high_id = f"p29_hist_{OBSERVER_B}_{open_ts.replace(' ', 'T')}"
            high_action = policy["experimental_action"]
            high_levels = levels if policy["accepted"] and levels is not None else None
            high_dec = {
                "decision_id": high_id,
                "event_id": high_id,
                "experience_source": SOURCE_HISTORICAL,
                "label": DIAG_LABEL,
                "not_forward_validation": True,
                "observer_id": OBSERVER_B,
                "strategy": STRATEGY_ID,
                "symbol": SYMBOL,
                "decision_timestamp_utc": close_ts,
                "signal_bar_open_utc": open_ts,
                "h13c_experimental_action": action,
                "experimental_action": high_action,
                "accepted": bool(policy["accepted"] and high_levels is not None),
                "reason_code": policy["reason_code"],
                "pred_vol_regime": vol.get("pred_vol_regime"),
                "pred_fwd_vol_12": vol.get("pred_fwd_vol_12"),
                "production_action": PRODUCTION_FINAL_ACTION,
                "final_action": PRODUCTION_FINAL_ACTION,
                "entry": None if not high_levels else high_levels["entry"],
                "tp_level": None if not high_levels else high_levels["tp_level"],
                "sl_level": None if not high_levels else high_levels["sl_level"],
                "atr": None if not high_levels else high_levels["atr"],
                "discord_sent": False,
                "broker_order": False,
            }
            high_decisions.append(high_dec)

        if baseline["accepted"] and levels is not None and atr_val is not None:
            rows_out = _eval_outcomes_for_signal(
                decision=baseline,
                action=action,
                atr_val=float(atr_val),
                levels=levels,
                signal_bar_open_utc=open_ts,
                all_bars=all_bars,
                as_of_eval=as_of_eval,
            )
            baseline_outcomes.extend(rows_out)
            for updated in rows_out:
                if updated.get("horizon_id") != "H12":
                    continue
                if updated.get("status") in {None, "PENDING", ""}:
                    continue
                try:
                    rr = float(updated["realized_r"])
                except (TypeError, ValueError):
                    continue
                if action == "BUY":
                    buy_r.append(rr)
                else:
                    sell_r.append(rr)

        if high_dec is not None and high_dec["accepted"] and levels is not None and atr_val is not None:
            rows_out = _eval_outcomes_for_signal(
                decision=high_dec,
                action=high_dec["experimental_action"],
                atr_val=float(atr_val),
                levels=levels,
                signal_bar_open_utc=open_ts,
                all_bars=all_bars,
                as_of_eval=as_of_eval,
            )
            high_outcomes.extend(rows_out)
            for updated in rows_out:
                if updated.get("horizon_id") != "H12":
                    continue
                if updated.get("status") in {None, "PENDING", ""}:
                    continue
                try:
                    rr = float(updated["realized_r"])
                except (TypeError, ValueError):
                    continue
                if high_dec["experimental_action"] == "BUY":
                    high_buy_r.append(rr)
                else:
                    high_sell_r.append(rr)

    base_counts = _counts(baseline_decisions)
    high_counts = _counts(high_decisions) if high_only_enabled else {"BUY": 0, "SELL": 0, "WAIT": 0, "n": 0}
    combined_r = buy_r + sell_r
    high_combined = high_buy_r + high_sell_r

    report: dict[str, Any] = {
        "label": DIAG_LABEL,
        "not_forward_validation": NOT_FORWARD,
        "verdict_channels": {
            "HISTORICAL_DIAGNOSTIC_RESULT": "computed below; not an edge claim",
            "FORWARD_EVIDENCE": {
                "phase28": {
                    "candles": 100,
                    "BUY": 0,
                    "SELL": 0,
                    "WAIT": 100,
                    "status": "INSUFFICIENT_FORWARD_EVIDENCE",
                },
                "phase29_live": "separate live campaign; not mixed into this diagnostic",
            },
            "PRODUCTION_STATUS": PRODUCTION_FINAL_ACTION,
        },
        "window": {
            "n_requested": n,
            "n_candles": window["n"],
            "first_candle_utc": window["first_candle_utc"],
            "last_candle_utc": window["last_candle_utc"],
            "research_cutoff_utc": cutoff,
            "excluded": m5["excluded"],
            "note": "Last N approved completed M5 feature rows with time <= research cutoff.",
        },
        "holdout": {
            "accessed": False,
            "holdout_name": HOLDOUT_NAME,
            "source_path": m5["source_path"],
        },
        "safety": {
            "discord_sent": False,
            "broker_orders": 0,
            "production_final_action": PRODUCTION_FINAL_ACTION,
            "agent_shadow_written": False,
            "experience_source": SOURCE_HISTORICAL,
            "frozen_cuts": {
                "q_low": cuts["q_low"],
                "q_high": cuts["q_high"],
                "close_ema_low": cuts["close_ema_low"],
                "close_ema_high": cuts["close_ema_high"],
                "source": cuts["source"],
            },
        },
        "baseline_h13c": {
            "counts": base_counts,
            "signal_rate": (base_counts["BUY"] + base_counts["SELL"]) / base_counts["n"] if base_counts["n"] else 0.0,
            "outcomes": _outcome_summary(baseline_outcomes),
            "performance_h12": {
                "combined": _perf(combined_r),
                "BUY": _perf(buy_r),
                "SELL": _perf(sell_r),
            },
        },
        "high_only_research": {
            "enabled": high_only_enabled,
            "blocker": high_only_blocker,
            "counts": high_counts,
            "signal_rate": (high_counts["BUY"] + high_counts["SELL"]) / high_counts["n"] if high_counts["n"] else 0.0,
            "outcomes": _outcome_summary(high_outcomes) if high_only_enabled else None,
            "performance_h12": {
                "combined": _perf(high_combined),
                "BUY": _perf(high_buy_r),
                "SELL": _perf(high_sell_r),
            },
            "note": "Research observer only; not promoted; separate from baseline.",
        },
        "comparison_phase28_forward": {
            "phase28_forward_candles": 100,
            "phase28_buy": 0,
            "phase28_sell": 0,
            "phase28_wait": 100,
            "historical_buy": base_counts["BUY"],
            "historical_sell": base_counts["SELL"],
            "historical_wait": base_counts["WAIT"],
            "mixed_into_one_performance_number": False,
            "note": "Historical diagnostic and forward evidence are separate sources.",
        },
        "edge_claim": False,
        "note": (
            "HISTORICAL_DIAGNOSTIC_ONLY / NOT_FORWARD_VALIDATION. "
            "Do not claim a trading edge from this diagnostic alone."
        ),
        "baseline_signal_samples": [
            d for d in baseline_decisions if d["experimental_action"] in {"BUY", "SELL"}
        ],
        "outcome_horizons_frozen_phase18": list(HORIZONS.keys()),
        "n_baseline_decisions_recorded": len(baseline_decisions),
        "n_baseline_outcomes_recorded": len(baseline_outcomes),
        "n_high_decisions_recorded": len(high_decisions),
        "n_high_outcomes_recorded": len(high_outcomes),
    }
    return _jsonable(report)


def write_historical_reports(report: dict[str, Any]) -> dict[str, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "historical_500_candle_diagnostic.json"
    md_path = DOCS_DIR / "PHASE_29_HISTORICAL_500_CANDLE_DIAGNOSTIC.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    base = report["baseline_h13c"]
    perf = base["performance_h12"]["combined"]
    buy = base["performance_h12"]["BUY"]
    sell = base["performance_h12"]["SELL"]
    high = report["high_only_research"]
    w = report["window"]
    lines = [
        "# PHASE 29 — Historical 500-Candle Diagnostic",
        "",
        f"**{DIAG_LABEL}**",
        f"**{NOT_FORWARD}**",
        "",
        "Do **not** claim a trading edge from this diagnostic alone.",
        "",
        "## Window",
        "",
        f"- First candle UTC: `{w['first_candle_utc']}`",
        f"- Last candle UTC: `{w['last_candle_utc']}`",
        f"- Candles: **{w['n_candles']}**",
        f"- Research cutoff UTC: `{w['research_cutoff_utc']}`",
        f"- Excluded post-cutoff rows: {w['excluded'].get('post_cutoff', 0)}",
        f"- Holdout accessed: **{report['holdout']['accessed']}**",
        "",
        "## Baseline H13_C counts",
        "",
        f"- BUY: {base['counts']['BUY']}",
        f"- SELL: {base['counts']['SELL']}",
        f"- WAIT: {base['counts']['WAIT']}",
        f"- Signal rate: {base['signal_rate']:.6f}",
        "",
        "## Outcome horizons (frozen Phase 18)",
        "",
        f"- Horizons: {', '.join(report.get('outcome_horizons_frozen_phase18') or list(HORIZONS.keys()))}",
        f"- H12 matured: {base['outcomes'].get('n_matured_h12')}",
        f"- H12 by status: {base['outcomes']['by_horizon'].get('H12')}",
        "",
        "## H12 performance (baseline)",
        "",
        f"- Combined n={perf['n']} mean_r={perf['mean_r']} median_r={perf['median_r']} "
        f"win_rate={perf['win_rate']} PF={perf['profit_factor']} maxDD={perf['max_drawdown_r']}",
        f"- BUY n={buy['n']} mean_r={buy['mean_r']} win_rate={buy['win_rate']} PF={buy['profit_factor']}",
        f"- SELL n={sell['n']} mean_r={sell['mean_r']} win_rate={sell['win_rate']} PF={sell['profit_factor']}",
        "",
        "## High-only research (separate)",
        "",
        f"- Enabled: {high['enabled']}",
        f"- BUY/SELL/WAIT: {high['counts']}",
        f"- Combined H12: {high['performance_h12']['combined']}",
        "- Not promoted.",
        "",
        "## Comparison vs Phase 28 forward (separate evidence)",
        "",
        "- Phase28 forward: 100 candles / 0 BUY / 0 SELL / 100 WAIT / INSUFFICIENT_FORWARD_EVIDENCE",
        f"- Historical diagnostic: {base['counts']['BUY']} BUY / {base['counts']['SELL']} SELL / {base['counts']['WAIT']} WAIT",
        "- Not mixed into one performance number.",
        "",
        "## Verdict channels",
        "",
        "- `HISTORICAL_DIAGNOSTIC_RESULT`: see metrics above (not an edge claim)",
        "- `FORWARD_EVIDENCE`: Phase 28 = 100 candles / 0 BUY / 0 SELL / INSUFFICIENT (not mixed)",
        "- `PRODUCTION_STATUS`: WAIT",
        "",
        "## Safety",
        "",
        "- Discord: not sent",
        "- Broker orders: 0",
        "- AGENT_SHADOW written: false",
        "- Experience source: HISTORICAL_HYPOTHETICAL",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path}
