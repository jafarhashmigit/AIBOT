"""Historical H13_C reachability analysis against frozen WF3 cuts."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from phase14.data import load_bundle, train_cutoff_for_fold
from phase14.h1_trend import build_h1_series, h1_trend_at
from phase14.strategy import decide_h13c, train_pullback_cuts
from phase16a.constants import FROZEN_CUTS
from phase21.constants import (
    FROZEN_WF3_CUTS,
    HOLDOUT_NAME,
    REPORTS_DIR,
    RESEARCH_CUTOFF_UTC,
    SENSITIVITY_Q_LOWS,
)
from phase21.stats import percentile_sorted, summarize_numeric

UTC_SESSIONS = (
    ("asia", range(0, 8)),
    ("london", range(8, 13)),
    ("ny", range(13, 21)),
    ("off", range(21, 24)),
)


def _session_utc(hour: int) -> str:
    for name, hours in UTC_SESSIONS:
        if hour in hours:
            return name
    return "off"


def _weekday(ts: str) -> str:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").strftime("%A")


def assert_no_holdout_touch() -> None:
    """Refuse if holdout filename appears as an open research input path."""
    # load_bundle uses FEATURES/H1/OOS/OUTCOMES only; holdout name must not match.
    from phase14.constants import FEATURES_PATH, H1_PATH, OOS_PATH, OUTCOMES_PATH

    for p in (FEATURES_PATH, H1_PATH, OOS_PATH, OUTCOMES_PATH):
        if p.name == HOLDOUT_NAME:
            raise RuntimeError(f"holdout path refused: {p}")


def evaluate_partial(feat: dict, h1_ctx: dict | None, cuts: dict) -> dict[str, Any]:
    if feat is None:
        return {
            "h1_up": False,
            "h1_down": False,
            "buy_pullback": False,
            "sell_extension": False,
            "spread_gt_0": False,
            "spread_lt_0": False,
            "buy_rule": False,
            "sell_rule": False,
        }
    c2e = float(feat["close_to_ema_20"])
    spread = float(feat["ema_9_20_spread"])
    h1_up = bool(h1_ctx and h1_ctx.get("h1_trend") == "up")
    h1_down = bool(h1_ctx and h1_ctx.get("h1_trend") == "down")
    buy_pullback = c2e <= float(cuts["close_ema_low"])
    sell_ext = c2e >= float(cuts["close_ema_high"])
    spread_gt = spread > 0
    spread_lt = spread < 0
    return {
        "h1_up": h1_up,
        "h1_down": h1_down,
        "buy_pullback": buy_pullback,
        "sell_extension": sell_ext,
        "spread_gt_0": spread_gt,
        "spread_lt_0": spread_lt,
        "buy_rule": h1_up and buy_pullback and spread_gt,
        "sell_rule": h1_down and sell_ext and spread_lt,
        "close_to_ema_20": c2e,
        "ema_9_20_spread": spread,
    }


def run_frozen_reachability(bundle: dict | None = None) -> dict[str, Any]:
    assert_no_holdout_touch()
    # Verify we use exact frozen cuts object values
    cuts = dict(FROZEN_WF3_CUTS)
    assert cuts["close_ema_low"] == FROZEN_CUTS["close_ema_low"]
    assert cuts["close_ema_high"] == FROZEN_CUTS["close_ema_high"]

    bundle = bundle or load_bundle()
    series = build_h1_series(bundle["h1_rows"])

    c2e_vals: list[float] = []
    spread_vals: list[float] = []
    atr_vals: list[float] = []
    h1_dir_counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    actions: Counter[str] = Counter()

    partial_counts = Counter()
    n_eligible = 0
    n_missing_feat = 0
    n_missing_h1 = 0

    # Regime accumulators: key -> Counter of buy_rule/sell_rule/wait
    by_session: dict[str, Counter[str]] = defaultdict(Counter)
    by_weekday: dict[str, Counter[str]] = defaultdict(Counter)
    by_trend: dict[str, Counter[str]] = defaultdict(Counter)
    atr_for_vol: list[tuple[str, float, str]] = []  # ts, atr, action

    for t in bundle["feature_times"]:
        if t > RESEARCH_CUTOFF_UTC:
            continue
        feat_row = bundle["features"].get(t)
        if feat_row is None:
            n_missing_feat += 1
            continue
        # Feature dict for decide_h13c
        try:
            feat = {
                "close_to_ema_20": float(feat_row["close_to_ema_20"]),
                "ema_9_20_spread": float(feat_row["ema_9_20_spread"]),
                "atr_14_pct": float(feat_row.get("atr_14_pct") or float("nan")),
            }
        except (TypeError, ValueError):
            n_missing_feat += 1
            continue
        h1_ctx = h1_trend_at(series, t, strict_gt=True)
        if h1_ctx is None:
            n_missing_h1 += 1
            action, reason = decide_h13c(feat, None, cuts)
        else:
            action, reason = decide_h13c(feat, h1_ctx, cuts)

        n_eligible += 1
        actions[action] += 1
        reasons[reason] += 1
        c2e_vals.append(feat["close_to_ema_20"])
        spread_vals.append(feat["ema_9_20_spread"])
        if feat["atr_14_pct"] == feat["atr_14_pct"]:  # not NaN
            atr_vals.append(feat["atr_14_pct"])

        part = evaluate_partial(feat, h1_ctx, cuts)
        for k in (
            "h1_up",
            "h1_down",
            "buy_pullback",
            "sell_extension",
            "spread_gt_0",
            "spread_lt_0",
            "buy_rule",
            "sell_rule",
        ):
            if part[k]:
                partial_counts[k] += 1

        trend = h1_ctx["h1_trend"] if h1_ctx else "missing"
        h1_dir_counts[trend] += 1

        hour = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").hour
        sess = _session_utc(hour)
        wd = _weekday(t)
        by_session[sess][action] += 1
        by_weekday[wd][action] += 1
        by_trend[trend][action] += 1
        if feat["atr_14_pct"] == feat["atr_14_pct"]:
            atr_for_vol.append((t, feat["atr_14_pct"], action))

    # Volatility regimes from contemporaneous atr_14_pct terciles (descriptive only)
    by_vol: dict[str, Counter[str]] = defaultdict(Counter)
    if atr_for_vol:
        atr_only = [a for _, a, _ in atr_for_vol]
        t1 = percentile_sorted(atr_only, 100 / 3)
        t2 = percentile_sorted(atr_only, 200 / 3)

        def vol_bucket(a: float) -> str:
            if a <= t1:
                return "low_vol"
            if a <= t2:
                return "mid_vol"
            return "high_vol"

        for _, a, action in atr_for_vol:
            by_vol[vol_bucket(a)][action] += 1
        vol_cuts = {"t1": t1, "t2": t2}
    else:
        vol_cuts = {}

    return {
        "frozen_cuts": {
            "q_low": cuts["q_low"],
            "q_high": cuts["q_high"],
            "close_ema_low": cuts["close_ema_low"],
            "close_ema_high": cuts["close_ema_high"],
            "source": cuts.get("source"),
            "n_train": cuts.get("n_train"),
            "train_cutoff": cuts.get("train_cutoff"),
        },
        "universe": {
            "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
            "n_feature_times_loaded": len(bundle["feature_times"]),
            "n_eligible_with_features": n_eligible,
            "n_missing_features": n_missing_feat,
            "n_missing_h1_context": n_missing_h1,
            "first_time": bundle["feature_times"][0] if bundle["feature_times"] else None,
            "last_time": bundle["feature_times"][-1] if bundle["feature_times"] else None,
            "holdout_accessed": False,
        },
        "feature_distributions": {
            "close_to_ema_20": summarize_numeric(c2e_vals),
            "ema_9_20_spread": summarize_numeric(spread_vals),
            "atr_14_pct": summarize_numeric(atr_vals),
            "h1_direction_counts": dict(h1_dir_counts),
        },
        "reachability_frozen": {
            "total_eligible_observations": n_eligible,
            "H1_up": partial_counts["h1_up"],
            "H1_down": partial_counts["h1_down"],
            "BUY_pullback_c2e_le_low": partial_counts["buy_pullback"],
            "SELL_extension_c2e_ge_high": partial_counts["sell_extension"],
            "spread_gt_0": partial_counts["spread_gt_0"],
            "spread_lt_0": partial_counts["spread_lt_0"],
            "complete_BUY_rule_matches": partial_counts["buy_rule"],
            "complete_SELL_rule_matches": partial_counts["sell_rule"],
            "action_counts": dict(actions),
            "BUY_rate": partial_counts["buy_rule"] / n_eligible if n_eligible else 0.0,
            "SELL_rate": partial_counts["sell_rule"] / n_eligible if n_eligible else 0.0,
            "reason_distribution_all": dict(reasons),
            "WAIT_reason_distribution": {
                k: v for k, v in reasons.items() if k != "selected"
            },
        },
        "regimes": {
            "by_utc_session": {k: dict(v) for k, v in sorted(by_session.items())},
            "by_weekday": {k: dict(v) for k, v in sorted(by_weekday.items())},
            "by_h1_trend": {k: dict(v) for k, v in sorted(by_trend.items())},
            "by_volatility_tercile": {k: dict(v) for k, v in sorted(by_vol.items())},
            "volatility_tercile_cuts_atr_14_pct": vol_cuts,
            "note": "Regime breakdowns are descriptive; not used to change thresholds.",
        },
    }


def run_sensitivity(bundle: dict | None = None) -> dict[str, Any]:
    """Research-only: recompute WF3 train percentile cuts at alternative q_low; q_high = 100-q_low."""
    assert_no_holdout_touch()
    bundle = bundle or load_bundle()
    series = build_h1_series(bundle["h1_rows"])
    rows = []
    for q_low in SENSITIVITY_Q_LOWS:
        q_high = 100 - q_low
        cuts = train_pullback_cuts(bundle, "WF3", q_low=q_low, q_high=q_high)
        buy = sell = wait = 0
        for t in bundle["feature_times"]:
            if t > RESEARCH_CUTOFF_UTC:
                continue
            feat_row = bundle["features"].get(t)
            if feat_row is None:
                continue
            feat = {
                "close_to_ema_20": float(feat_row["close_to_ema_20"]),
                "ema_9_20_spread": float(feat_row["ema_9_20_spread"]),
            }
            h1_ctx = h1_trend_at(series, t, strict_gt=True)
            action, _ = decide_h13c(feat, h1_ctx, cuts)
            if action == "BUY":
                buy += 1
            elif action == "SELL":
                sell += 1
            else:
                wait += 1
        total = buy + sell + wait
        rows.append(
            {
                "q_low": q_low,
                "q_high": q_high,
                "close_ema_low": cuts["close_ema_low"],
                "close_ema_high": cuts["close_ema_high"],
                "n_train": cuts["n_train"],
                "train_cutoff": cuts["train_cutoff"],
                "BUY": buy,
                "SELL": sell,
                "WAIT": wait,
                "total": total,
                "BUY_rate": buy / total if total else 0.0,
                "SELL_rate": sell / total if total else 0.0,
                "applied_to_agent": False,
                "note": "research_comparison_only",
            }
        )
    return {
        "frozen_reference_q25_q75": {
            "close_ema_low": FROZEN_WF3_CUTS["close_ema_low"],
            "close_ema_high": FROZEN_WF3_CUTS["close_ema_high"],
            "unchanged": True,
        },
        "wf3_train_cutoff": train_cutoff_for_fold("WF3"),
        "rows": rows,
        "disclaimer": (
            "Higher signal frequency is not evidence of better trading performance. "
            "No threshold selected for production or experimental agent use."
        ),
    }


def load_live_shadow_decisions(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compare_live_vs_historical(frozen_result: dict[str, Any]) -> dict[str, Any]:
    from phase21.constants import SRC_DIR

    p16 = load_live_shadow_decisions(SRC_DIR / "data" / "phase16a" / "shadow_decisions.csv")
    p20 = load_live_shadow_decisions(SRC_DIR / "data" / "phase20" / "shadow_decisions.csv")

    def live_summary(rows: list[dict], label: str) -> dict[str, Any]:
        reasons = Counter(r.get("decision_reason") for r in rows)
        actions = Counter(r.get("experimental_action") for r in rows)
        c2es = []
        spreads = []
        for r in rows:
            feat = json.loads(r.get("feature_snapshot_json") or "{}")
            if "close_to_ema_20" in feat:
                c2es.append(float(feat["close_to_ema_20"]))
            if "ema_9_20_spread" in feat:
                spreads.append(float(feat["ema_9_20_spread"]))
        return {
            "label": label,
            "n": len(rows),
            "experimental_actions": dict(actions),
            "reasons": dict(reasons),
            "close_to_ema_20": summarize_numeric(c2es),
            "ema_9_20_spread": summarize_numeric(spreads),
            "merged_into_historical": False,
        }

    hist = frozen_result["reachability_frozen"]
    return {
        "phase16a_live": live_summary(p16, "phase16a_live_shadow"),
        "phase20_live": live_summary(p20, "phase20_live_shadow"),
        "phase20a_diagnostic": {
            "root_cause": "h1_up_pullback_not_met; c2e never <= frozen close_ema_low on observed live bars",
            "source": "reports/phase20a/summary.json",
            "merged_into_historical": False,
        },
        "historical_frozen": {
            "n": hist["total_eligible_observations"],
            "BUY": hist["complete_BUY_rule_matches"],
            "SELL": hist["complete_SELL_rule_matches"],
            "BUY_rate": hist["BUY_rate"],
            "SELL_rate": hist["SELL_rate"],
            "WAIT_reasons": hist["WAIT_reason_distribution"],
        },
        "comparison_note": (
            "Live Phase 16A/20 samples are short H1-up windows with no frozen BUY matches. "
            "Historical research shows BUY/SELL are rare but non-zero under the same frozen cuts. "
            "Live scarcity is consistent with selectivity, not proof of a broken gate."
        ),
    }


def write_reports(payload: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "reachability_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    # CSV: sensitivity
    sens = payload.get("sensitivity", {}).get("rows", [])
    if sens:
        path = REPORTS_DIR / "sensitivity_research_only.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(sens[0].keys()))
            w.writeheader()
            for row in sens:
                w.writerow(row)
    # CSV: feature distribution flat
    dist = payload.get("frozen_reachability", {}).get("feature_distributions", {})
    flat_rows = []
    for name, stats in dist.items():
        if not isinstance(stats, dict) or "n" not in stats:
            continue
        flat_rows.append({"feature": name, **stats})
    if flat_rows:
        path = REPORTS_DIR / "feature_distributions.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
            w.writeheader()
            for row in flat_rows:
                w.writerow(row)


def run_full_research() -> dict[str, Any]:
    assert_no_holdout_touch()
    bundle = load_bundle()
    # Leakage guard: last feature time must not exceed cutoff
    if bundle["feature_times"] and bundle["feature_times"][-1] > RESEARCH_CUTOFF_UTC:
        raise RuntimeError("feature times exceed research cutoff")

    frozen = run_frozen_reachability(bundle)
    sensitivity = run_sensitivity(bundle)
    live = compare_live_vs_historical(frozen)

    buy_n = frozen["reachability_frozen"]["complete_BUY_rule_matches"]
    sell_n = frozen["reachability_frozen"]["complete_SELL_rule_matches"]
    total = frozen["reachability_frozen"]["total_eligible_observations"]
    # Qualitative judgment: selective if rates << 5% but non-zero
    buy_rate = frozen["reachability_frozen"]["BUY_rate"]
    sell_rate = frozen["reachability_frozen"]["SELL_rate"]
    if buy_n == 0 and sell_n == 0:
        restrictiveness = "unreachable_on_historical_sample"
    elif buy_rate < 0.01 and sell_rate < 0.01:
        restrictiveness = "highly_selective_but_reachable"
    elif buy_rate < 0.05 and sell_rate < 0.05:
        restrictiveness = "selective"
    else:
        restrictiveness = "moderately_frequent"

    payload = {
        "recipe_id": "phase21_h13c_threshold_reachability_v1",
        "mode": "research_only",
        "trading_logic_changed": False,
        "frozen_thresholds_modified": False,
        "mt5_started": False,
        "discord_sent": False,
        "broker_orders": 0,
        "holdout_access": 0,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "production_final_action": "WAIT",
        "frozen_reachability": frozen,
        "sensitivity": sensitivity,
        "live_comparison": live,
        "conclusion": {
            "BUY_reachability": {
                "matches": buy_n,
                "rate": buy_rate,
                "total": total,
            },
            "SELL_reachability": {
                "matches": sell_n,
                "rate": sell_rate,
                "total": total,
            },
            "restrictiveness_label": restrictiveness,
            "future_research_hypothesis_justified": restrictiveness
            in {"highly_selective_but_reachable", "selective", "unreachable_on_historical_sample"},
            "future_research_note": (
                "A separate future hypothesis may study whether live regimes differ from "
                "historical pullback frequency — without changing frozen thresholds or claiming edge."
            ),
            "explicit": "Research only — no trading edge established.",
        },
    }
    write_reports(payload)
    return payload
