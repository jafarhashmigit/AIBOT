"""Phase 34 autonomous runner — extended Dukascopy bid/ask validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase34.acquisition import run_acquisition
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


def _write_docs(qual: dict[str, Any], runtime: dict[str, Any], acq: dict[str, Any]) -> None:
    plan = PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESEARCH_PLAN.md"
    results = PROJECT_ROOT / "docs" / "agent" / "PHASE_34_RESULTS.md"
    days = select_trading_days()
    plan.write_text(
        "\n".join(
            [
                "# Phase 34 — Research Plan",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
                "## Objective",
                "",
                "Extend Dukascopy XAUUSD bid/ask history (up to 20 trading days) and validate",
                "spread / execution-cost characteristics for future offline evaluation.",
                "No strategy evaluation or parameter changes.",
                "",
                "## Selected trading days (deterministic)",
                "",
                ", ".join(f"`{d}`" for d in days),
                "",
                "## Offline re-analysis (no download)",
                "",
                "```powershell",
                "$env:PYTHONPATH='src'",
                "python -m phase34.analyze_offline",
                "```",
                "",
                "## Safety",
                "",
                "- Phase 0–33 immutable; no holdout; no MT5; no Discord; no packages; no commit/push.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results.write_text(
        "\n".join(
            [
                "# Phase 34 — Results",
                "",
                f"**Final verdict:** `{qual.get('final_verdict')}`",
                f"**MT5 parity:** `{qual.get('mt5_parity_status')}`",
                f"**Complete trading days:** `{acq.get('n_complete_trading_days')}`",
                f"**Ticks:** `{(acq.get('totals') or {}).get('ticks')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}`",
                f"**Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- START_UTC: `{runtime.get('START_UTC')}`",
                f"- END_UTC: `{runtime.get('END_UTC')}`",
                f"- DURATION: `{runtime.get('DURATION')}`",
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


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_progress({"phase": 34, "completed_stages": [], "current_stage": "start", "start_utc": start_s, "errors": []})

    immutability = check_phase33_immutability()
    mark_stage("immutability", completed=True, extra={"ok": immutability.get("phase33_immutable_ok")})

    acq_out = run_acquisition()
    acq = acq_out["manifest"]
    ticks = acq_out["ticks"]
    mark_stage(
        "acquisition",
        completed=True,
        extra={"complete_days": acq.get("n_complete_trading_days"), "ticks": acq.get("totals", {}).get("ticks")},
    )

    quality = validate_ticks(ticks)
    mark_stage("quality", completed=True, extra={"pass": quality.get("pass")})

    days_obj = acq.get("days") or {}
    day_list = list(days_obj.keys()) if isinstance(days_obj, dict) else list(days_obj)
    dst = validate_utc_dst(ticks, day_list)
    mark_stage("dst_validation", completed=True, extra={"pass": dst.get("pass")})

    spreads = analyze_spreads(ticks)
    mark_stage("spread_analysis", completed=True)

    paths = sorted(TICKS_DIR.glob("*.jsonl")) if TICKS_DIR.is_dir() else []
    independent = independent_recompute_from_jsonl(paths)
    write_json("independent_spread_recompute.json", independent)
    mark_stage("independent_recompute", completed=True)

    costs = reconcile_costs(spreads)
    mark_stage("cost_reconciliation", completed=True)

    intrabar = analyze_intrabar(ticks, acq)
    mark_stage("intrabar", completed=True)

    mt5 = report_mt5_parity()
    mark_stage("mt5_parity", completed=True)

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
    _write_docs(qual, runtime, acq)
    print(json.dumps({"final_verdict": final["final_verdict"], "runtime": runtime, "ticks": final["totals"]}, indent=2))
    return final


if __name__ == "__main__":
    main()
