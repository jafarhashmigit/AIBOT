"""Finalize Phase36 from on-disk corpus only (no network). Bound: skip eval if <10 days."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase36.acquisition import rebuild_corpus_from_disk, validate_ticks
from phase36.bootstrap import day_block_bootstrap
from phase36.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MIN_COMPLETE_DAYS_FOR_REPLICATION,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    RAW_DIR,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF_UTC,
    TELEGRAM_MESSAGES_SENT,
    file_sha256,
)
from phase36.date_selection import select_independent_dates
from phase36.evaluate import evaluate_mean_reversion
from phase36.frozen_spec import register_frozen_experiment
from phase36.independent import compare_primary_vs_independent, independent_recompute
from phase36.progress import write_json
from phase36.qualification import apply_gates
from phase36.run_phase36 import _spread_stats, _write_docs

UTC = timezone.utc


def _missing_hours(day: str) -> list[int]:
    day_dir = RAW_DIR / day
    out: list[int] = []
    for hour in range(24):
        if f"{day} {hour:02d}:00:00" > RESEARCH_CUTOFF_UTC:
            continue
        if (day_dir / f"{hour:02d}h_ticks.bi5").is_file() or (
            day_dir / f"{hour:02d}h_ticks.empty"
        ).is_file():
            continue
        out.append(hour)
    return out


def _hour_failure_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    failed_hours: list[dict[str, Any]] = []
    timeout_dates: list[str] = []
    for day, rec in (manifest.get("days") or {}).items():
        if not isinstance(rec, dict):
            continue
        day_timeout = False
        for h in rec.get("hours") or []:
            if h.get("ok"):
                continue
            err = str(h.get("error") or "")
            failed_hours.append({"day": day, "hour": h.get("hour"), "error": err})
            if "timed out" in err.lower() or "timeout" in err.lower():
                day_timeout = True
        if day_timeout:
            timeout_dates.append(day)
        if rec.get("status") == "NOT_ATTEMPTED":
            failed_hours.append({"day": day, "hour": None, "error": rec.get("reason") or "NOT_ATTEMPTED"})
    return {"failed_hours": failed_hours, "timeout_dates": sorted(set(timeout_dates))}


def write_acquisition_bound_final(
    *,
    dates: dict[str, Any],
    manifest: dict[str, Any],
    ticks: list[dict[str, Any]],
    n_complete: int,
    n_m5_candles: int,
    final_verdict: str,
    runtime: dict[str, Any],
    evaluation_skipped: bool,
) -> dict[str, Any]:
    selected = list(dates.get("selected_dates") or [])
    complete = list(manifest.get("complete_trading_days") or [])
    incomplete = list(manifest.get("incomplete_trading_days") or [])
    missing_by_day = {d: _missing_hours(d) for d in selected if (RAW_DIR / d).exists() or d in incomplete or d in complete}
    for d in selected:
        if d not in missing_by_day and not (RAW_DIR / d).exists():
            missing_by_day[d] = list(range(24))  # never acquired locally
    fail_sum = _hour_failure_summary(manifest)
    gate_reached = n_complete >= MIN_COMPLETE_DAYS_FOR_REPLICATION
    reason = None
    if not gate_reached:
        reason = (
            f"Independently qualified complete dates={n_complete} "
            f"< required MIN_COMPLETE_DAYS_FOR_REPLICATION={MIN_COMPLETE_DAYS_FOR_REPLICATION}. "
            "Acquisition bounded per user order: no additional date fetch, no Phase34/35 eval-day reuse, "
            "no gate lowering, no strategy evaluation on insufficient sample."
        )
    report = {
        "phase": 36,
        "recipe_id": RECIPE_ID,
        "bound_mode": True,
        "allow_network": False,
        "final_verdict": final_verdict,
        "gate_min_10_complete_independent_dates_reached": gate_reached,
        "insufficient_data_reason": reason,
        "n_complete_independent_dates": n_complete,
        "complete_independent_dates": complete,
        "incomplete_dates": incomplete,
        "not_attempted_or_missing_local": [
            d for d in selected if d not in complete and d not in incomplete
        ]
        or [d for d in selected if not (RAW_DIR / d).exists()],
        "missing_hours_by_date": missing_by_day,
        "failed_hours": fail_sum["failed_hours"],
        "timeout_dates": fail_sum["timeout_dates"],
        "selected_dates": selected,
        "excluded_eval_days_blocked": sorted(dates.get("excluded_eval_days") or []),
        "total_valid_ticks_complete_days_only": len(ticks),
        "total_complete_m5_candles": n_m5_candles,
        "evaluation_skipped": evaluation_skipped,
        "acquisition_runtime": {
            "manifest_started_utc": manifest.get("started_utc"),
            "manifest_ended_utc": manifest.get("ended_utc"),
            "manifest_duration_seconds": manifest.get("duration_seconds"),
            "manifest_stop_reason": manifest.get("stop_reason"),
            "manifest_stopped_early": manifest.get("stopped_early"),
            "finalize_runtime": runtime,
        },
        "manifest_totals": manifest.get("totals"),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "mt5_used": False,
        "live_data_used": False,
        "phase34_35_eval_days_reused": False,
        "additional_dates_fetched_after_bound": False,
    }
    write_json("acquisition_bound_final.json", report)
    return report


def _write_bound_final_report(bound: dict[str, Any], final: dict[str, Any], runtime: dict[str, Any]) -> None:
    lines = [
        "# Phase 36 — Final Report",
        "",
        f"**Verdict:** `{final.get('final_verdict')}`",
        "",
        "## Acquisition bound (user order)",
        "",
        f"- Gate ≥10 complete independent dates reached: `{bound.get('gate_min_10_complete_independent_dates_reached')}`",
        f"- Complete independent dates (`{bound.get('n_complete_independent_dates')}`): `{bound.get('complete_independent_dates')}`",
        f"- Incomplete dates: `{bound.get('incomplete_dates')}`",
        f"- Total valid ticks (complete days only): `{bound.get('total_valid_ticks_complete_days_only')}`",
        f"- Total complete M5 candles: `{bound.get('total_complete_m5_candles')}`",
        f"- Evaluation skipped: `{bound.get('evaluation_skipped')}`",
        f"- Insufficient-data reason: `{bound.get('insufficient_data_reason')}`",
        f"- Manifest stop reason: `{bound.get('acquisition_runtime', {}).get('manifest_stop_reason')}`",
        "",
        "## Safety",
        "",
        f"- MT5 used: `{final.get('mt5_used')}`",
        f"- Broker orders: `{BROKER_ORDERS}`",
        f"- Discord/Telegram: `{DISCORD_MESSAGES_SENT}` / `{TELEGRAM_MESSAGES_SENT}`",
        f"- Packages installed: `{PACKAGES_INSTALLED}`",
        f"- Holdout accessed: `{HOLDOUT_ACCESSES > 0}`",
        f"- Commit/push: `{GIT_COMMIT}` / `{GIT_PUSH}`",
        f"- Production: `{PRODUCTION_FINAL_ACTION}` | Champion: `{CHAMPION_STATUS}`",
        "",
        f"## Runtime: `{runtime.get('DURATION')}` ({runtime.get('START_UTC')} → {runtime.get('END_UTC')})",
        "",
        "See `reports/phase36/acquisition_bound_final.json` and companion JSON artifacts.",
        "",
    ]
    (REPORTS_DIR / "PHASE_36_FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_36_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 36 — Results",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                f"**Final verdict:** `{final.get('final_verdict')}`",
                f"**Complete independent days:** `{bound.get('n_complete_independent_dates')}`",
                f"**Resolved trades:** `{final.get('n_resolved')}`",
                f"**Mean R (bid/ask):** `{final.get('mean_r')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}` | **Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- START_UTC: `{runtime.get('START_UTC')}`",
                f"- END_UTC: `{runtime.get('END_UTC')}`",
                f"- DURATION: `{runtime.get('DURATION')}`",
                "",
                "Acquisition bounded; strategy evaluation skipped when <10 complete independent dates.",
                "",
                "See `reports/phase36/` for full artifacts.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    protected_ok = all(file_sha256(PROJECT_ROOT / rel) == exp for rel, exp in PROTECTED_HASHES.items())
    frozen = register_frozen_experiment()
    dates = select_independent_dates()
    write_json(
        "preflight.json",
        {
            "protected_artifacts_intact": protected_ok,
            "frozen_registered": True,
            "selected_dates": dates["selected_dates"],
            "mt5": False,
            "production": PRODUCTION_FINAL_ACTION,
            "champion": CHAMPION_STATUS,
            "mode": "finalize_from_disk_bound",
            "allow_network": False,
        },
    )

    acq = rebuild_corpus_from_disk(dates["selected_dates"], allow_network=False)
    manifest = acq["manifest"]
    ticks = acq["ticks"]
    quality = validate_ticks(ticks) if ticks else {"pass": False, "reason": "no_ticks"}
    spreads = _spread_stats(ticks)
    write_json("data_quality.json", quality)
    write_json("spread_stats.json", spreads)

    n_complete = int(manifest.get("n_complete_trading_days") or 0)
    evaluation_skipped = n_complete < MIN_COMPLETE_DAYS_FOR_REPLICATION
    n_m5 = 0

    if evaluation_skipped:
        evaluation = {
            "view_a_bidask": {"n_resolved": 0, "mean_r": None},
            "trades": [],
            "n_buy_signals": 0,
            "n_sell_signals": 0,
            "n_m5_candles": 0,
            "skipped": True,
            "skip_reason": f"n_complete_days={n_complete} < {MIN_COMPLETE_DAYS_FOR_REPLICATION}",
        }
        bootstrap = {"ok": False, "skipped": True, "ci95_excludes_zero": False, "dependent_on_one_exceptional_day": False}
        indep = {"summary": {}, "n_buy_signals": 0, "n_sell_signals": 0, "skipped": True}
        indep_cmp = {"ok": False, "mismatches": ["evaluation_skipped_insufficient_complete_days"]}
        write_json(
            "evaluation_skipped.json",
            {
                "skipped": True,
                "reason": evaluation["skip_reason"],
                "n_complete_days": n_complete,
                "min_required": MIN_COMPLETE_DAYS_FOR_REPLICATION,
            },
        )
    else:
        evaluation = evaluate_mean_reversion(ticks) if ticks else {
            "view_a_bidask": {"n_resolved": 0, "mean_r": None},
            "trades": [],
            "n_buy_signals": 0,
            "n_sell_signals": 0,
        }
        bootstrap = day_block_bootstrap(evaluation.get("trades") or [])
        indep = independent_recompute(ticks) if ticks else {"summary": {}, "n_buy_signals": 0, "n_sell_signals": 0}
        indep_cmp = (
            compare_primary_vs_independent(evaluation, indep)
            if ticks
            else {"ok": False, "mismatches": ["no_ticks"]}
        )
        n_m5 = int(evaluation.get("n_m5_candles") or 0)

    gates = apply_gates(
        n_complete_days=n_complete,
        evaluation=evaluation,
        bootstrap=bootstrap,
        indep_cmp=indep_cmp,
    )
    if evaluation_skipped:
        # Force bound verdict — never REPLICATION_FAILED on insufficient sample.
        gates["final_verdict"] = "INSUFFICIENT_DATA"
        gates["failed_gates"] = ["min_10_complete_independent_dates"]
        write_json("qualification.json", gates)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        "mode": "finalize_from_disk_bound",
    }
    write_json("runtime.json", runtime)
    write_json("evaluation.json", evaluation)
    write_json("bootstrap.json", bootstrap)
    write_json("independent_recompute.json", {"summary": indep.get("summary"), "compare": indep_cmp})
    write_json("gates.json", gates)

    final_verdict = "INSUFFICIENT_DATA" if evaluation_skipped else gates["final_verdict"]
    final = {
        "phase": 36,
        "recipe_id": RECIPE_ID,
        "final_verdict": final_verdict,
        "failed_gates": gates["failed_gates"],
        "gates": gates.get("gates"),
        "n_complete_days": n_complete,
        "complete_trading_days": manifest.get("complete_trading_days"),
        "incomplete_trading_days": manifest.get("incomplete_trading_days"),
        "selected_dates": dates["selected_dates"],
        "n_ticks": len(ticks),
        "n_m5_candles": n_m5,
        "spread_stats": spreads,
        "n_buy_signals": evaluation.get("n_buy_signals") if not evaluation_skipped else 0,
        "n_sell_signals": evaluation.get("n_sell_signals") if not evaluation_skipped else 0,
        "n_resolved": 0 if evaluation_skipped else gates.get("n_resolved"),
        "n_unresolved": None if evaluation_skipped else (evaluation.get("view_a_bidask") or {}).get("n_unresolved"),
        "mean_r": None if evaluation_skipped else gates.get("mean_r"),
        "stress_mean_r": None if evaluation_skipped else gates.get("stress_mean_r"),
        "bootstrap_ci95": None if evaluation_skipped else gates.get("ci95"),
        "prob_mean_r_le_0": None if evaluation_skipped else bootstrap.get("prob_mean_r_le_0"),
        "positive_day_ratio": None if evaluation_skipped else bootstrap.get("positive_day_ratio"),
        "independent_recompute_ok": False if evaluation_skipped else indep_cmp.get("ok"),
        "evaluation_skipped": evaluation_skipped,
        "evaluation_skip_reason": evaluation.get("skip_reason") if evaluation_skipped else None,
        "frozen_source_hashes": frozen.get("source_hashes"),
        "acquisition_stopped_early": manifest.get("stopped_early"),
        "acquisition_stop_reason": manifest.get("stop_reason"),
        "mt5_used": False,
        "mt5_connections": MT5_CONNECTIONS,
        "live_data_used": False,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "broker_orders": BROKER_ORDERS,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "telegram_sent": TELEGRAM_MESSAGES_SENT > 0,
        "packages_installed": PACKAGES_INSTALLED,
        "protected_artifacts_intact": protected_ok,
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)

    bound = write_acquisition_bound_final(
        dates=dates,
        manifest=manifest,
        ticks=ticks,
        n_complete=n_complete,
        n_m5_candles=n_m5,
        final_verdict=final_verdict,
        runtime=runtime,
        evaluation_skipped=evaluation_skipped,
    )
    # Bound markdown last so it is not overwritten by the short docs helper.
    _write_docs(final, runtime)
    _write_bound_final_report(bound, final, runtime)
    print(json.dumps({"final_verdict": final_verdict, "n_complete": n_complete, "bound": {
        "gate_reached": bound["gate_min_10_complete_independent_dates_reached"],
        "complete": bound["complete_independent_dates"],
        "incomplete": bound["incomplete_dates"],
        "ticks": bound["total_valid_ticks_complete_days_only"],
        "m5": bound["total_complete_m5_candles"],
        "reason": bound["insufficient_data_reason"],
    }}, indent=2))
    return final


if __name__ == "__main__":
    main()
