"""Phase 4 orchestrator: coverage, quality, predeclared regime slices.

Does not open the holdout. Does not train a new trading model. Does not send orders.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from phase3.baselines import baseline_e1
from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    col,
    fmt_time,
    holdout_status,
    install_guards,
    save,
    wrap,
)
from phase3.walk_forward import fold_public, nested_folds
from phase4.constants import (
    FDR_Q,
    GATE,
    HISTORY_PROBE_PATH,
    RECIPE_ID,
    REGIME_FAMILIES,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
    SIDE_OUTCOMES_VERIFY_PATH,
    SIDES,
    SPREAD_STRESS,
)
from phase4.dataset import load_phase4_frame
from phase4.evaluate import bh_fdr, gate_slice, slice_unconditional, stress_mean_r
from phase4.regimes import attach_regimes, tercile_cuts


def _probe_summary() -> dict:
    if not HISTORY_PROBE_PATH.exists():
        return {"status": "missing", "path": str(HISTORY_PROBE_PATH)}
    payload = json.loads(HISTORY_PROBE_PATH.read_text(encoding="utf-8"))
    result = payload.get("result", {})
    earliest_real = None
    quirk_ones = 0

    def walk(obj) -> None:
        nonlocal earliest_real, quirk_ones
        if isinstance(obj, dict):
            n = obj.get("n")
            first = obj.get("first")
            if isinstance(n, int) and isinstance(first, str) and first not in ("", "None"):
                if n == 1:
                    quirk_ones += 1
                elif n >= 100:
                    if earliest_real is None or first < earliest_real:
                        earliest_real = first
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(result)
    return {
        "status": result.get("status"),
        "existing_m5_start": result.get("existing_m5_start"),
        "broker_earliest_window_with_n_ge_100": earliest_real,
        "mt5_single_bar_quirk_count": quirk_ones,
        "note": "Windows with n=1 are the known MT5 quirk (same first bar). Phase 4 does not download additional bars.",
    }


def _outcomes_summary() -> dict:
    if not SIDE_OUTCOMES_VERIFY_PATH.exists():
        return {"status": "missing"}
    payload = json.loads(SIDE_OUTCOMES_VERIFY_PATH.read_text(encoding="utf-8"))
    r = payload.get("result", {})
    return {
        "eligible_decision_timestamps": r.get("eligible_decision_timestamps"),
        "ineligible_rows": r.get("ineligible_rows"),
        "unmatched_gap_crossing_backtest_trades": (r.get("backtest_intersection") or {}).get("unmatched_gap_or_missing"),
        "exit_reason_counts_buy": r.get("exit_reason_counts_buy"),
        "exit_reason_counts_sell": r.get("exit_reason_counts_sell"),
    }


def _quality(rows: list[dict]) -> dict:
    minutes = col(rows, "minutes_since_prev_bar")
    atr = col(rows, "atr_14_pct")
    hours = [int(r["corrected_hour_utc"]) for r in rows]
    sessions = {}
    for r in rows:
        sessions[r["regime_session"]] = sessions.get(r["regime_session"], 0) + 1
    return {
        "n_timestamps": len(rows),
        "min_decision": fmt_time(rows[0]["decision_time"]),
        "max_decision": fmt_time(rows[-1]["decision_time"]),
        "n_calendar_days": len({fmt_time(r["decision_time"])[:10] for r in rows}),
        "gap_bars_minutes_gt_5": int(np.nansum(minutes > 5)),
        "first_bar_nan_minutes": int(np.isnan(minutes).sum()),
        "atr_14_pct_mean": float(np.nanmean(atr)),
        "atr_14_pct_p10": float(np.nanquantile(atr, 0.10)),
        "atr_14_pct_p90": float(np.nanquantile(atr, 0.90)),
        "hour_utc_min": min(hours),
        "hour_utc_max": max(hours),
        "session_counts": sessions,
        "note": "Features are from the closed decision bar. No price after the cutoff is read.",
    }


def _catalogue() -> list[tuple[str, str]]:
    """Finite confirmatory slices. Not searched."""
    items = []
    for level in ("off_hours", "asia", "london", "london_ny_overlap", "new_york"):
        items.append(("regime_session", level))
    for level in ("utc_00_07", "utc_08_12", "utc_13_16", "utc_17_23"):
        items.append(("regime_hour", level))
    for level in ("Mon", "Tue", "Wed", "Thu", "Fri"):
        items.append(("regime_weekday", level))
    for level in ("low", "mid", "high"):
        items.append(("regime_atr", level))
    for level in ("ema_up", "ema_down"):
        items.append(("regime_trend", level))
    return items


def _e1_by_session(rows: list[dict]) -> dict:
    actions = baseline_e1(rows)
    out = {}
    for session in ("off_hours", "asia", "london", "london_ny_overlap", "new_york"):
        r, pnl, times = [], [], []
        n_wait = 0
        for rec, act in zip(rows, actions):
            if rec["regime_session"] != session:
                continue
            if act == "WAIT":
                n_wait += 1
                continue
            r.append(rec[f"actual_net_r_{act}"])
            pnl.append(rec[f"actual_net_pnl_{act}"])
            times.append(rec["decision_time"])
        rr = np.array(r, dtype=float)
        pp = np.array(pnl, dtype=float)
        from phase4.evaluate import _metrics
        rec = _metrics(rr, pp, times)
        rec["n_wait"] = n_wait
        rec["note"] = "Diagnostic only. Not in the confirmatory FDR family. E1 is the Phase 2 frozen readout."
        out[session] = rec
    return out


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    long_rows, wide, load_info = load_phase4_frame()
    # Temporary session labels so quality can count; atr terciles assigned per nested fold.
    labeled_all = attach_regimes(wide, atr_cuts=None)
    quality = _quality(labeled_all)

    folds = nested_folds(wide)
    fold_pub = [fold_public(f) for f in folds]
    outer_labeled = []
    atr_cut_report = []
    for fold in folds:
        inner_atr = np.array([r["atr_14_pct"] for r in fold["inner"]], dtype=float)
        cuts = tercile_cuts(inner_atr)
        atr_cut_report.append({
            "nested_id": fold["nested_id"],
            "atr_lo": cuts[0],
            "atr_hi": cuts[1],
            "inner_n": len(fold["inner"]),
            "outer_n": len(fold["outer"]),
        })
        outer_labeled.extend(attach_regimes(fold["outer"], cuts))

    catalogue = _catalogue()
    slices = []
    for key, level in catalogue:
        for side in SIDES:
            rec = slice_unconditional(outer_labeled, side, key, level)
            rec["stress_mean_r_x1_5"] = stress_mean_r(outer_labeled, side, key, level, 1.5)
            rec["stress_mean_r_x2_0"] = stress_mean_r(outer_labeled, side, key, level, 2.0)
            slices.append(rec)
    slices = bh_fdr(slices, FDR_Q)
    for rec in slices:
        rec["gate"] = gate_slice(rec)

    passed = [s for s in slices if s["gate"]["passed"]]
    promising = [s for s in slices if s["gate"].get("promising") and not s["gate"]["passed"]]
    e1_session = _e1_by_session(outer_labeled)

    if passed:
        conclusion = "CREDIBLE CONDITIONAL EDGE ESTABLISHED"
    elif promising:
        conclusion = "PROMISING BUT UNCONFIRMED"
    else:
        conclusion = "NO CREDIBLE CONDITIONAL EDGE"

    results = {
        "load": load_info,
        "coverage": {
            "research_window": {"start": quality["min_decision"], "stop": quality["max_decision"]},
            "n_oos_timestamps_phase2": quality["n_timestamps"],
            "n_outer_timestamps": len(outer_labeled),
            "n_calendar_days_oos": quality["n_calendar_days"],
            "history_probe": _probe_summary(),
            "limitation": (
                "Approved research features begin 2026-02-16. Broker M5 history in the "
                "Phase 1 probe reaches 2025-06-02 but was not downloaded or appended. "
                "Phase 4 does not extend the dataset."
            ),
        },
        "data_quality": {
            **quality,
            "phase1_outcomes": _outcomes_summary(),
            "clock": "Corrected UTC session/hour columns are used. Original hour_utc is not.",
        },
        "walk_forward": fold_pub,
        "atr_tercile_cuts_inner_only": atr_cut_report,
        "predeclared_families": list(REGIME_FAMILIES),
        "gate": GATE,
        "n_confirmatory_slices": len(slices),
        "slices": slices,
        "passed_slices": [s["slice_id"] for s in passed],
        "promising_slices": [s["slice_id"] for s in promising],
        "e1_by_session_diagnostic": e1_session,
        "permutation_a_phase1": {
            "status": "not_run",
            "note": "Phase 1 permutation A remains incomplete. Phase 4 does not mark it passed.",
        },
        "conclusion": conclusion,
        "production_ready": False,
        "live_ready": False,
        "finding_class": "exploratory",
    }
    save(REPORTS_DIR / "regime_results.json",
         wrap("phase4_regime_results", "exploratory", {"recipe": RECIPE_ID, "gate": GATE}, results, SEED))
    save(REPORTS_DIR / "walk_forward_design.json",
         wrap("phase4_walk_forward_design", "confirmatory", {"recipe": RECIPE_ID},
              {"folds": fold_pub, "atr_cuts": atr_cut_report,
               "note": "Outer folds are Phase 2 WF2 and WF3. Same nested structure as Phase 3."},
              SEED))

    assert_holdout_untouched()
    print("holdout", holdout_status())
    print("outer_ts", len(outer_labeled), "slices", len(slices),
          "passed", len(passed), "promising", len(promising))
    print("CONCLUSION", conclusion)
    # Compact leaderboard for the log only (not used to select).
    ranked = sorted(slices, key=lambda s: (s["mean_r"] if np.isfinite(s["mean_r"]) else -9), reverse=True)[:8]
    for s in ranked:
        print(s["slice_id"], "n", s["n"], "mean_r", s["mean_r"],
              "ci", s["bootstrap"].get("ci_low"), s["bootstrap"].get("ci_high"),
              "fdr", s.get("fdr_pass"), "gate", s["gate"]["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
