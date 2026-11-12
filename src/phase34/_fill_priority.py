"""One-shot priority fill for DST/incomplete days, then disk rebuild + analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from phase34.acquisition import DST_PRIORITY_DAYS, rebuild_corpus_from_disk, run_acquisition
from phase34.constants import REPORTS_DIR, TICKS_DIR, select_trading_days
from phase34.cost_reconciliation import reconcile_costs
from phase34.dst_validation import validate_utc_dst
from phase34.immutability import check_phase33_immutability
from phase34.intrabar import analyze_intrabar
from phase34.mt5_parity import report_mt5_parity
from phase34.progress import mark_stage, save_progress, write_json
from phase34.qualification import finalize
from phase34.quality import validate_ticks
from phase34.spread_analysis import analyze_spreads, independent_recompute_from_jsonl
from phase34.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    H13_C_STATUS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
)

UTC = timezone.utc


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_progress({"phase": 34, "completed_stages": [], "current_stage": "priority_fill", "start_utc": start_s})

    priority = list(DST_PRIORITY_DAYS) + ["2026-02-16", "2026-02-26", "2026-09-28"]
    print("PRIORITY_FILL", priority, flush=True)
    fill = run_acquisition(days=priority)
    print(
        "FILL_DONE",
        {
            "complete": fill["manifest"].get("n_complete_trading_days"),
            "ticks": fill["manifest"]["totals"]["ticks"],
            "stopped": fill["manifest"].get("stopped_early"),
            "reason": fill["manifest"].get("stop_reason"),
        },
        flush=True,
    )
    mark_stage("priority_fill", completed=True)

    # Ensure corpus includes all selected days from disk
    rebuilt = rebuild_corpus_from_disk(days=select_trading_days())
    acq = rebuilt["manifest"]
    ticks = rebuilt["ticks"]
    print(
        "REBUILD",
        {
            "complete": acq.get("n_complete_trading_days"),
            "complete_days": acq.get("complete_trading_days"),
            "incomplete": acq.get("incomplete_trading_days"),
            "ticks": acq["totals"]["ticks"],
        },
        flush=True,
    )
    mark_stage("rebuild", completed=True)

    immutability = check_phase33_immutability()
    quality = validate_ticks(ticks)
    dst = validate_utc_dst(ticks, list(acq.get("days") or {}))
    spreads = analyze_spreads(ticks)
    paths = sorted(TICKS_DIR.glob("*.jsonl")) if TICKS_DIR.is_dir() else []
    independent = independent_recompute_from_jsonl(paths)
    write_json("independent_spread_recompute.json", independent)
    costs = reconcile_costs(spreads)
    intrabar = analyze_intrabar(ticks, acq)
    mt5 = report_mt5_parity()
    qual = finalize(
        acquisition=acq,
        quality=quality,
        dst=dst,
        spreads=spreads,
        costs=costs,
        intrabar=intrabar,
        mt5=mt5,
        immutability=immutability,
        independent=independent,
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
        "phase": 34,
        "recipe_id": RECIPE_ID,
        "final_verdict": qual.get("final_verdict"),
        "provider_qualification_separate": qual.get("provider_qualification"),
        "mt5_parity": mt5.get("status"),
        "license_status": qual.get("license_status"),
        "n_complete_trading_days": acq.get("n_complete_trading_days"),
        "n_selected_days": acq.get("n_selected_days"),
        "complete_trading_days": acq.get("complete_trading_days"),
        "incomplete_trading_days": acq.get("incomplete_trading_days"),
        "totals": acq.get("totals"),
        "stopped_early": acq.get("stopped_early"),
        "stop_reason": acq.get("stop_reason"),
        "spread_median_usd": (spreads.get("overall_usd") or {}).get("median"),
        "spread_mean_usd": (spreads.get("overall_usd") or {}).get("mean"),
        "spread_p95_usd": (spreads.get("overall_usd") or {}).get("p95"),
        "representativeness": spreads.get("representativeness"),
        "quality_pass": quality.get("pass"),
        "dst_pass": dst.get("pass"),
        "independent_recompute": independent,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "mt5_connected": MT5_CONNECTIONS > 0,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "broker_orders": BROKER_ORDERS,
        "packages_installed": PACKAGES_INSTALLED,
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "phase33_immutable": immutability.get("phase33_immutable_ok"),
        "protected_artifacts_intact": immutability.get("protected_artifacts_intact"),
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "strategy_evaluated": False,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)

    # Docs
    results = PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESULTS.md"
    results.write_text(
        "\n".join(
            [
                "# Phase 34 — Results",
                "",
                f"**Final verdict:** `{final['final_verdict']}`",
                f"**Complete trading days:** `{final['n_complete_trading_days']}` / `{final['n_selected_days']}`",
                f"**Ticks:** `{(final.get('totals') or {}).get('ticks')}`",
                f"**Spread median/mean/p95 USD:** `{final.get('spread_median_usd')}` / `{final.get('spread_mean_usd')}` / `{final.get('spread_p95_usd')}`",
                f"**Representativeness vs Phase33:** `{final.get('representativeness')}`",
                f"**MT5 parity:** `{final.get('mt5_parity')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}`  **Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- START_UTC: `{runtime['START_UTC']}`",
                f"- END_UTC: `{runtime['END_UTC']}`",
                f"- DURATION: `{runtime['DURATION']}`",
                "",
                "## Offline re-run",
                "",
                "```powershell",
                "$env:PYTHONPATH='src'",
                "python -m phase34.analyze_offline",
                "```",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    plan = PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESEARCH_PLAN.md"
    if not plan.is_file():
        plan.write_text(
            "# Phase 34 — Research Plan\n\nExtended Dukascopy bid/ask validation. Offline: `python -m phase34.analyze_offline`\n",
            encoding="utf-8",
        )

    print(json.dumps({"final_verdict": final["final_verdict"], "runtime": runtime, "totals": final["totals"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
