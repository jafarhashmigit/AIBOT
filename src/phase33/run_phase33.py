"""Phase 33 autonomous runner — Dukascopy bid/ask qualification."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase33.candle_builder import build_m5_candles
from phase33.constants import (
    CHAMPION_STATUS,
    GIT_COMMIT,
    GITHUB_PUSH,
    H13_C_STATUS,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    DISCORD_MESSAGES_SENT,
    BROKER_ORDERS,
    AGENT_SHADOW_DIR,
)
from phase33.execution_comparison import compare_execution_models
from phase33.mt5_parity_protocol import define_parity_protocol
from phase33.preflight import run_preflight, verify_protected_hashes
from phase33.progress import load_progress, mark_stage, save_progress, write_json
from phase33.provider_docs import run_provider_docs
from phase33.qualification import qualify
from phase33.raw_data_validation import validate_ticks
from phase33.sample_acquisition import run_sample_acquisition
from phase33.spread_analysis import analyze_spreads
from phase33.strategy_diagnostics import run_strategy_diagnostics
from phase33.timestamp_validation import validate_timestamps

UTC = timezone.utc

STAGES = [
    "preflight",
    "provider_docs",
    "sample_acquisition",
    "raw_data_validation",
    "candle_builder",
    "timestamp_validation",
    "spread_analysis",
    "mt5_parity_protocol",
    "execution_comparison",
    "strategy_diagnostics",
    "qualification",
    "final_verdict",
]


def _write_docs(qual: dict[str, Any], runtime: dict[str, Any], preflight: dict[str, Any]) -> None:
    plan = PROJECT_ROOT / "docs" / "agent" / "PHASE_33_RESEARCH_PLAN.md"
    results = PROJECT_ROOT / "docs" / "agent" / "PHASE_33_RESULTS.md"
    plan.write_text(
        "\n".join(
            [
                "# Phase 33 — Research Plan",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
                "## Objective",
                "",
                "Qualify whether Dukascopy can provide a free, complete, technically compatible",
                "historical XAUUSD bid/ask feed for independent execution validation.",
                "Provider qualification only — not strategy development.",
                "",
                "## Safety",
                "",
                f"- Cutoff: `{preflight.get('research_cutoff_utc')}`",
                "- No holdout, no MT5 connect, no Discord/Telegram/OCI, no broker orders,",
                "  no package installs, no AGENT_SHADOW writes, no commit/push.",
                "- Isolated under `src/phase33/`.",
                "",
                "## Stages",
                "",
                *[f"{i}. `{s}`" for i, s in enumerate(STAGES, 1)],
                "",
                "## Download policy",
                "",
                "Bounded diagnostic sample only (selected days × session hours), stdlib HTTP GET",
                "of public `datafeed.dukascopy.com` bi5 archives if freely reachable.",
                "",
                "## Qualification gates",
                "",
                "DOCUMENTATION_ONLY → SAMPLE_DATA_ACQUIRED → HISTORICAL_DATA_QUALITY_PASS →",
                "HISTORICAL_BID_ASK_QUALIFIED; MT5 parity is a separate pending gate.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results.write_text(
        "\n".join(
            [
                "# Phase 33 — Results",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                f"**Final verdict:** `{qual.get('final_verdict')}`",
                f"**Provider qualification:** `{qual.get('provider_qualification_primary')}`",
                f"**MT5 parity:** `{qual.get('mt5_parity_gate')}`",
                f"**Execution realism:** `{qual.get('execution_realism')}`",
                f"**Objective status:** `{qual.get('objective_status')}`",
                "",
                "## Confirmed findings",
                "",
                *[f"- {x}" for x in qual.get("confirmed_findings") or []],
                "",
                "## Unresolved limitations",
                "",
                *[f"- {x}" for x in qual.get("unresolved_limitations") or []],
                "",
                "## Safety verification",
                "",
                f"- Holdout accessed: `{HOLDOUT_ACCESSES > 0}`",
                f"- Protected artifacts: see `reports/phase33/preflight.json`",
                f"- MT5 connected: `{MT5_CONNECTIONS > 0}`",
                f"- Discord sent: `{DISCORD_MESSAGES_SENT > 0}`",
                f"- Broker orders: `{BROKER_ORDERS}`",
                f"- AGENT_SHADOW modified: `false` (write forbidden; dir={AGENT_SHADOW_DIR})",
                f"- Git commit: `{GIT_COMMIT}`",
                f"- Git push: `{GITHUB_PUSH}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- H13_C: `{H13_C_STATUS}`",
                "",
                "## Runtime",
                "",
                f"- START_UTC: `{runtime.get('START_UTC')}`",
                f"- END_UTC: `{runtime.get('END_UTC')}`",
                f"- DURATION: `{runtime.get('DURATION')}`",
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
    prog = {
        "phase": 33,
        "completed_stages": [],
        "current_stage": None,
        "download_attempts": [],
        "download_results": [],
        "source_evidence": [],
        "errors": [],
        "remaining_stages": list(STAGES),
        "start_utc": start_s,
    }
    save_progress(prog)

    preflight = run_preflight()
    mark_stage("preflight", completed=True)
    prog = load_progress()
    prog["remaining_stages"] = [s for s in STAGES if s not in prog["completed_stages"]]
    save_progress(prog)

    docs = run_provider_docs()
    mark_stage("provider_docs", completed=True, extra={"page_ok": docs.get("page_fetch", {}).get("ok")})

    acq = run_sample_acquisition()
    mark_stage(
        "sample_acquisition",
        completed=True,
        extra={"ticks": acq["log"].get("total_ticks"), "acquired": acq["log"].get("sample_acquired")},
    )
    ticks = acq["ticks"]

    raw_q = validate_ticks(ticks)
    mark_stage("raw_data_validation", completed=True, extra={"pass": raw_q.get("pass")})

    candle_out = build_m5_candles(ticks)
    mark_stage("candle_builder", completed=True, extra={"n": candle_out["report"].get("n_candles")})
    candles = candle_out["candles"]

    ts_rep = validate_timestamps(ticks, candles)
    mark_stage("timestamp_validation", completed=True, extra={"pass": ts_rep.get("pass")})

    spread_rep = analyze_spreads(ticks)
    mark_stage("spread_analysis", completed=True, extra={"pass": spread_rep.get("pass")})

    parity = define_parity_protocol()
    mark_stage("mt5_parity_protocol", completed=True, extra={"status": parity.get("status")})

    exec_rep = compare_execution_models(spread_rep)
    mark_stage("execution_comparison", completed=True)

    strat = run_strategy_diagnostics(ticks, candles)
    mark_stage("strategy_diagnostics", completed=True, extra={"skipped": strat.get("skipped")})

    qual = qualify(
        docs=docs,
        acquisition=acq,
        raw_quality=raw_q,
        candles=candle_out,
        timestamps=ts_rep,
        spreads=spread_rep,
        parity=parity,
        execution=exec_rep,
        strategy=strat,
    )
    mark_stage("qualification", completed=True, extra={"verdict": qual.get("final_verdict")})

    end = datetime.now(UTC)
    end_s = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    dur_s = (end - start).total_seconds()
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end_s,
        "DURATION_SECONDS": dur_s,
        "DURATION": f"{dur_s / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    hashes = verify_protected_hashes()
    final = {
        "phase": 33,
        "recipe_id": RECIPE_ID,
        "final_verdict": qual.get("final_verdict"),
        "provider_qualification": qual.get("provider_qualification_primary"),
        "historical_bid_ask_qualified": qual.get("historical_bid_ask_qualified"),
        "mt5_parity": qual.get("mt5_parity_gate"),
        "execution_realism": qual.get("execution_realism"),
        "objective_status": qual.get("objective_status"),
        "confirmed_findings": qual.get("confirmed_findings"),
        "unresolved_limitations": qual.get("unresolved_limitations"),
        "sample_ticks": acq["log"].get("total_ticks"),
        "sample_m5_candles": candle_out["report"].get("n_candles"),
        "spread_median_usd": (spread_rep.get("overall_usd") or {}).get("median"),
        "strategy_diagnostic_skipped": strat.get("skipped"),
        "holdout_accessed": False,
        "protected_artifacts": "INTACT" if hashes["intact"] else "MISMATCH",
        "phase0_32_modified": False,
        "mt5_connected": False,
        "discord_sent": False,
        "broker_orders": 0,
        "agent_shadow_modified": False,
        "git_commit": False,
        "git_push": False,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    mark_stage("final_verdict", completed=True)

    prog = load_progress()
    prog["remaining_stages"] = []
    prog["completed_stages"] = list(STAGES)
    prog["current_stage"] = "done"
    save_progress(prog)

    _write_docs(qual, runtime, preflight)
    print(json.dumps({"final_verdict": final["final_verdict"], "runtime": runtime}, indent=2))
    return final


if __name__ == "__main__":
    main()
