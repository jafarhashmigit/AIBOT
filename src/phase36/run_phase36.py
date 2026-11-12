"""Phase 36 autonomous runner — mean_reversion independent replication."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase36.acquisition import acquire_selected_days, validate_ticks
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
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    file_sha256,
)
from phase36.date_selection import select_independent_dates
from phase36.evaluate import evaluate_mean_reversion
from phase36.frozen_spec import register_frozen_experiment
from phase36.independent import compare_primary_vs_independent, independent_recompute
from phase36.progress import write_json
from phase36.qualification import apply_gates

UTC = timezone.utc


def _spread_stats(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    if not ticks:
        return {"n": 0}
    spreads = sorted(float(t["ask"]) - float(t["bid"]) for t in ticks)

    def pct(p: float) -> float:
        k = (len(spreads) - 1) * (p / 100.0)
        import math

        f, c = math.floor(k), math.ceil(k)
        if f == c:
            return spreads[int(k)]
        return spreads[f] * (c - k) + spreads[c] * (k - f)

    return {
        "n": len(spreads),
        "median": pct(50),
        "mean": sum(spreads) / len(spreads),
        "p95": pct(95),
        "min": spreads[0],
        "max": spreads[-1],
    }


def _write_docs(final: dict[str, Any], runtime: dict[str, Any]) -> None:
    md = "\n".join(
        [
            "# Phase 36 — Results",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Final verdict:** `{final['final_verdict']}`",
            f"**Complete independent days:** `{final.get('n_complete_days')}`",
            f"**Resolved trades:** `{final.get('n_resolved')}`",
            f"**Mean R (bid/ask):** `{final.get('mean_r')}`",
            f"**Production:** `{PRODUCTION_FINAL_ACTION}` | **Champion:** `{CHAMPION_STATUS}`",
            "",
            f"- START_UTC: `{runtime['START_UTC']}`",
            f"- END_UTC: `{runtime['END_UTC']}`",
            f"- DURATION: `{runtime['DURATION']}`",
            "",
            "See `reports/phase36/` for full artifacts.",
            "",
        ]
    )
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_36_RESULTS.md").write_text(md + "\n", encoding="utf-8")
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_36_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 36 — Research Plan",
                "",
                "Independent replication of frozen Phase 35 `mean_reversion` on non-overlapping Dukascopy dates.",
                "No optimization. No MT5. No promotion.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (REPORTS_DIR / "PHASE_36_FINAL_REPORT.md").write_text(
        "\n".join(
            [
                "# Phase 36 — Final Report",
                "",
                f"**Verdict:** `{final['final_verdict']}`",
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
                f"## Runtime: `{runtime['DURATION']}` ({runtime['START_UTC']} → {runtime['END_UTC']})",
                "",
                "Full metrics in companion JSON reports under `reports/phase36/`.",
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

    # 1) Preflight / frozen registration
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
        },
    )

    # 2) Acquisition
    acq = acquire_selected_days(dates["selected_dates"])
    manifest = acq["manifest"]
    ticks = acq["ticks"]
    quality = validate_ticks(ticks) if ticks else {"pass": False, "reason": "no_ticks"}
    spreads = _spread_stats(ticks)
    write_json("data_quality.json", quality)
    write_json("spread_stats.json", spreads)

    n_complete = int(manifest.get("n_complete_trading_days") or 0)
    # Bound rule: do not evaluate / bootstrap / recompute below the 10-day gate.
    if n_complete < MIN_COMPLETE_DAYS_FOR_REPLICATION:
        end = datetime.now(UTC)
        runtime = {
            "START_UTC": start_s,
            "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "DURATION_SECONDS": (end - start).total_seconds(),
            "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        }
        gates = apply_gates(
            n_complete_days=n_complete,
            evaluation={"view_a_bidask": {"n_resolved": 0, "mean_r": None}, "chronological": {}, "buy_summary": {}, "sell_summary": {}, "view_c_stress_extra_005": {}},
            bootstrap={"ci95_excludes_zero": False, "dependent_on_one_exceptional_day": False},
            indep_cmp={"ok": False, "mismatches": ["evaluation_skipped_insufficient_complete_days"]},
        )
        final = {
            "phase": 36,
            "recipe_id": RECIPE_ID,
            "final_verdict": "INSUFFICIENT_DATA",
            "n_complete_days": n_complete,
            "complete_trading_days": manifest.get("complete_trading_days"),
            "incomplete_trading_days": manifest.get("incomplete_trading_days"),
            "selected_dates": dates["selected_dates"],
            "n_ticks": len(ticks),
            "n_m5_candles": 0,
            "n_resolved": 0,
            "mean_r": None,
            "failed_gates": ["min_10_complete_independent_dates"],
            "gates": gates.get("gates"),
            "evaluation_skipped": True,
            "evaluation_skip_reason": f"n_complete_days={n_complete} < MIN_COMPLETE_DAYS_FOR_REPLICATION={MIN_COMPLETE_DAYS_FOR_REPLICATION}",
            "acquisition_stop": manifest.get("stop_reason"),
            "mt5_used": False,
            "production": PRODUCTION_FINAL_ACTION,
            "champion": CHAMPION_STATUS,
            "runtime": runtime,
        }
        write_json("final_verdict.json", final)
        write_json("runtime.json", runtime)
        write_json(
            "evaluation_skipped.json",
            {
                "skipped": True,
                "reason": final["evaluation_skip_reason"],
                "n_complete_days": n_complete,
                "min_required": MIN_COMPLETE_DAYS_FOR_REPLICATION,
            },
        )
        _write_docs(final, runtime)
        print(json.dumps(final, indent=2))
        return final

    # 3) Evaluate only when >=10 complete independent days
    evaluation = evaluate_mean_reversion(ticks) if ticks else {
        "view_a_bidask": {"n_resolved": 0, "mean_r": None},
        "trades": [],
        "n_buy_signals": 0,
        "n_sell_signals": 0,
    }
    bootstrap = day_block_bootstrap(evaluation.get("trades") or [])
    indep = independent_recompute(ticks) if ticks else {"summary": {}, "n_buy_signals": 0, "n_sell_signals": 0}
    indep_cmp = compare_primary_vs_independent(evaluation, indep) if ticks else {"ok": False, "mismatches": ["no_ticks"]}
    gates = apply_gates(
        n_complete_days=n_complete,
        evaluation=evaluation,
        bootstrap=bootstrap,
        indep_cmp=indep_cmp,
    )

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 36,
        "recipe_id": RECIPE_ID,
        "final_verdict": gates["final_verdict"],
        "failed_gates": gates["failed_gates"],
        "gates": gates["gates"],
        "n_complete_days": n_complete,
        "complete_trading_days": manifest.get("complete_trading_days"),
        "incomplete_trading_days": manifest.get("incomplete_trading_days"),
        "selected_dates": dates["selected_dates"],
        "n_ticks": len(ticks),
        "n_m5_candles": evaluation.get("n_m5_candles"),
        "spread_stats": spreads,
        "n_buy_signals": evaluation.get("n_buy_signals"),
        "n_sell_signals": evaluation.get("n_sell_signals"),
        "n_resolved": gates.get("n_resolved"),
        "n_unresolved": (evaluation.get("view_a_bidask") or {}).get("n_unresolved"),
        "mean_r": gates.get("mean_r"),
        "stress_mean_r": gates.get("stress_mean_r"),
        "bootstrap_ci95": gates.get("ci95"),
        "prob_mean_r_le_0": bootstrap.get("prob_mean_r_le_0"),
        "positive_day_ratio": bootstrap.get("positive_day_ratio"),
        "independent_recompute_ok": indep_cmp.get("ok"),
        "frozen_source_hashes": frozen.get("source_hashes"),
        "acquisition_stopped_early": manifest.get("stopped_early"),
        "acquisition_stop_reason": manifest.get("stop_reason"),
        "mt5_used": False,
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
    _write_docs(final, runtime)
    print(json.dumps({"final_verdict": final["final_verdict"], "n_complete": n_complete, "runtime": runtime}, indent=2))
    return final


if __name__ == "__main__":
    main()
