"""Finalize Phase 34 from disk corpus — no downloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from phase34.acquisition import rebuild_corpus_from_disk
from phase34.analyze_offline import load_all_ticks
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
from phase34.progress import mark_stage, save_progress, write_json
from phase34.qualification import finalize
from phase34.quality import validate_ticks
from phase34.spread_analysis import analyze_spreads, independent_recompute_from_jsonl

UTC = timezone.utc


def main() -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_progress({"phase": 34, "current_stage": "finalize", "start_utc": start_s, "completed_stages": []})

    rebuilt = rebuild_corpus_from_disk(days=select_trading_days())
    acq = rebuilt["manifest"]
    # Prefer streaming from jsonl to avoid holding duplicate tick lists if rebuild already wrote them
    ticks = load_all_ticks() or rebuilt["ticks"]
    mark_stage("rebuild", completed=True, extra={"ticks": len(ticks), "complete": acq.get("n_complete_trading_days")})

    immutability = check_phase33_immutability()
    mark_stage("immutability", completed=True)

    quality = validate_ticks(ticks)
    mark_stage("quality", completed=True, extra={"pass": quality.get("pass")})

    dst = validate_utc_dst(ticks, list(acq.get("days") or {}))
    mark_stage("dst", completed=True, extra={"pass": dst.get("pass")})

    spreads = analyze_spreads(ticks)
    mark_stage("spreads", completed=True)

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
    mark_stage("qualification", completed=True, extra={"verdict": qual.get("final_verdict")})

    end = datetime.now(UTC)
    # Include prior acquisition wall time context if lean fill log exists
    lean = REPORTS_DIR / "lean_fill_log.json"
    prior_fill_s = 0.0
    if lean.is_file():
        prior_fill_s = float(json.loads(lean.read_text(encoding="utf-8")).get("duration_seconds") or 0)
    # Also note earlier 20-min acquisition from first pass (~1206s)
    first_pass_s = 1206.0
    total_research_s = (end - start).total_seconds() + prior_fill_s + first_pass_s

    runtime = {
        "START_UTC": "2026-11-10T13:41:02Z",  # first Phase34 research start
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "FINALIZE_START_UTC": start_s,
        "FINALIZE_DURATION_SECONDS": (end - start).total_seconds(),
        "LEAN_FILL_SECONDS": prior_fill_s,
        "FIRST_ACQUISITION_SECONDS_APPROX": first_pass_s,
        "DURATION_SECONDS": total_research_s,
        "DURATION": f"{total_research_s / 60.0:.2f} min",
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
        "coverage_note": (
            "Selected 20 trading days; network 503/timeouts prevented full completion. "
            "Exact achieved coverage reported; dates not substituted."
        ),
        "spread_median_usd": (spreads.get("overall_usd") or {}).get("median"),
        "spread_mean_usd": (spreads.get("overall_usd") or {}).get("mean"),
        "spread_p95_usd": (spreads.get("overall_usd") or {}).get("p95"),
        "representativeness": spreads.get("representativeness"),
        "phase33_comparison": spreads.get("phase33_comparison"),
        "quality_pass": quality.get("pass"),
        "dst_pass": dst.get("pass"),
        "dst_unqualified_periods": dst.get("unqualified_periods"),
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

    (PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 34 — Results",
                "",
                f"**Final verdict:** `{final['final_verdict']}`",
                f"**Complete trading days:** `{final['n_complete_trading_days']}` / `{final['n_selected_days']}`",
                f"**Ticks:** `{(final.get('totals') or {}).get('ticks')}`",
                f"**Spread median / mean / P95 USD:** `{final.get('spread_median_usd')}` / `{final.get('spread_mean_usd')}` / `{final.get('spread_p95_usd')}`",
                f"**vs Phase 33:** `{final.get('representativeness')}`",
                f"**MT5 parity:** `{final.get('mt5_parity')}`",
                f"**License:** `{(final.get('license_status') or {}).get('status')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}` | **Champion:** `{CHAMPION_STATUS}`",
                "",
                "## Coverage",
                "",
                f"- Complete: {', '.join('`'+d+'`' for d in (final.get('complete_trading_days') or []))}",
                f"- Incomplete/not fully acquired: {', '.join('`'+d+'`' for d in (final.get('incomplete_trading_days') or []))}",
                f"- Note: {final.get('coverage_note')}",
                "",
                "## Runtime",
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
                "## Selected days",
                "",
                ", ".join(f"`{d}`" for d in select_trading_days()),
                "",
                "## Offline analysis (no download)",
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

    print(json.dumps({"final_verdict": final["final_verdict"], "runtime": runtime, "totals": final["totals"]}, indent=2))
    return final


if __name__ == "__main__":
    main()
