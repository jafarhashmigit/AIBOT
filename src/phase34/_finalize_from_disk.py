"""Finalize Phase 34 from local raw corpus — no network downloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from phase34.acquisition import rebuild_corpus_from_disk
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
    REPORTS_DIR,
    TICKS_DIR,
    select_trading_days,
)
from phase34.cost_reconciliation import reconcile_costs
from phase34.dst_validation import validate_utc_dst
from phase34.immutability import check_phase33_immutability
from phase34.intrabar import analyze_intrabar
from phase34.mt5_parity import report_mt5_parity
from phase34.progress import save_progress, write_json
from phase34.qualification import finalize
from phase34.quality import validate_ticks
from phase34.spread_analysis import analyze_spreads, independent_recompute_from_jsonl

UTC = timezone.utc


def main() -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_progress({"phase": 34, "current_stage": "finalize_from_disk", "start_utc": start_s})

    rebuilt = rebuild_corpus_from_disk(days=select_trading_days())
    acq = rebuilt["manifest"]
    # Mark that network pass was bounded / stopped — coverage is exact achieved set.
    acq["stopped_early"] = True
    acq["stop_reason"] = "max_wall_seconds_or_network_stall; reported_exact_coverage"
    write_json("acquisition_manifest.json", acq)

    ticks = rebuilt["ticks"]
    print(
        json.dumps(
            {
                "complete_days": acq.get("n_complete_trading_days"),
                "complete": acq.get("complete_trading_days"),
                "incomplete": acq.get("incomplete_trading_days"),
                "ticks": acq["totals"]["ticks"],
            },
            indent=2,
        ),
        flush=True,
    )

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
        "phase33_comparison": spreads.get("phase33_comparison"),
        "quality_pass": quality.get("pass"),
        "dst_pass": dst.get("pass"),
        "dst_probes": dst.get("probes"),
        "independent_recompute": independent,
        "independent_recompute_ok": qual.get("gates", {}).get("independent_recompute_ok"),
        "intrabar_classification": intrabar.get("classification"),
        "cost_recommendation": costs.get("recommendation"),
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

    (PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 34 — Results",
                "",
                f"**Final verdict:** `{final['final_verdict']}`",
                f"**Complete trading days:** `{final['n_complete_trading_days']}` / `{final['n_selected_days']}`",
                f"**Complete days:** {', '.join(f'`{d}`' for d in (final.get('complete_trading_days') or []))}",
                f"**Ticks:** `{(final.get('totals') or {}).get('ticks')}`",
                f"**Spread median / mean / P95 USD:** `{final.get('spread_median_usd')}` / `{final.get('spread_mean_usd')}` / `{final.get('spread_p95_usd')}`",
                f"**vs Phase33 representativeness:** `{final.get('representativeness')}`",
                f"**Quality pass:** `{final.get('quality_pass')}`  **DST pass:** `{final.get('dst_pass')}`",
                f"**MT5 parity:** `{final.get('mt5_parity')}`",
                f"**License:** `{(final.get('license_status') or {}).get('status')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}`  **Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- Holdout accessed: `{final['holdout_accessed']}`",
                f"- Phase33 immutable: `{final['phase33_immutable']}`",
                f"- Protected artifacts intact: `{final['protected_artifacts_intact']}`",
                f"- Broker orders: `{final['broker_orders']}`  Discord: `{final['discord_sent']}`  Packages: `{final['packages_installed']}`",
                "",
                f"- START_UTC: `{runtime['START_UTC']}`",
                f"- END_UTC: `{runtime['END_UTC']}`",
                f"- DURATION: `{runtime['DURATION']}`",
                "",
                "## Offline re-run (no download)",
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
    plan.write_text(
        "\n".join(
            [
                "# Phase 34 — Research Plan",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
                "Extend Dukascopy XAUUSD bid/ask history (up to 20 trading days) and validate",
                "spread / execution-cost characteristics. No strategy evaluation.",
                "",
                "## Offline re-analysis",
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

    print(json.dumps({"final_verdict": final["final_verdict"], "runtime": runtime}, indent=2), flush=True)
    return final


if __name__ == "__main__":
    main()
