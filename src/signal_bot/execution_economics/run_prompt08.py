"""Prompt 8 orchestrator — execution economics + live evidence readiness. No Prompt 9."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_bot.execution_economics.broker_audit import build_broker_economics_audit
from signal_bot.execution_economics.c07_readiness import build_c07_a_readiness
from signal_bot.execution_economics.collector_reliability import (
    inspect_collector_reliability,
    write_autostart_script,
)
from signal_bot.execution_economics.constants import (
    CHAMPION_STATUS,
    COST_MODEL_VERSION,
    DISCORD_ACTIONABLE,
    H70_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROMPT07_BUNDLE,
    REPORTS,
    VERDICT_COLLECTOR_FAIL,
    VERDICT_PARTIAL,
    VERDICT_SAFETY,
    VERDICT_VERIFIED,
    VERDICT_INSUFFICIENT,
)
from signal_bot.execution_economics.cost_model import build_cost_model
from signal_bot.execution_economics.evidence_qualification import build_live_evidence_qualification
from signal_bot.execution_economics.sensitivity import evaluate_trade_cost_sensitivity
from signal_bot.execution_economics.spread_analysis import analyze_live_spreads


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_prompt7_counts() -> tuple[int | None, int | None]:
    if not PROMPT07_BUNDLE.is_file():
        return None, None
    blob = json.loads(PROMPT07_BUNDLE.read_text(encoding="utf-8"))
    live = (blob.get("feasibility") or {}).get("genuine_live_exness_xauusdm") or {}
    return live.get("unique_newly_closed_live_m5_bars"), live.get("quotes")


def _choose_verdict(
    *,
    cost: dict[str, Any],
    spread: dict[str, Any],
    reliability: dict[str, Any],
) -> str:
    if ORDER_SEND != "PROHIBITED" or CHAMPION_STATUS != "NO_MODEL":
        return VERDICT_SAFETY
    svc = (reliability.get("health") or {}).get("service_status")
    alive = (reliability.get("health") or {}).get("pid_alive")
    if svc not in ("RUNNING",) or not alive:
        return VERDICT_COLLECTOR_FAIL
    n = int((spread.get("n_usable_quotes") or 0))
    if n < 30:
        return VERDICT_INSUFFICIENT
    # Spread observed but commission/swap/slippage incomplete → partial
    if cost.get("NET_PROFITABILITY") == "ESTABLISHED" and cost.get("production_approved"):
        return VERDICT_VERIFIED
    if n >= 30 and cost.get("known_cost_adjusted_r_supported"):
        return VERDICT_PARTIAL
    return VERDICT_INSUFFICIENT


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    roots = [
        PROJECT_ROOT / "src" / "signal_bot" / "execution_economics" / "tests",
        PROJECT_ROOT / "src" / "phase67" / "tests",
        PROJECT_ROOT / "src" / "phase69" / "tests" if (PROJECT_ROOT / "src" / "phase69" / "tests").is_dir() else None,
        PROJECT_ROOT / "src" / "phase54" / "tests",
        PROJECT_ROOT / "src" / "phase56" / "tests",
    ]
    for root in roots:
        if root and root.is_dir():
            suite.addTests(loader.discover(str(root), top_level_dir=str(PROJECT_ROOT / "src")))
    # phase66 if present
    p66 = PROJECT_ROOT / "src" / "phase66" / "tests"
    if p66.is_dir():
        suite.addTests(loader.discover(str(p66), top_level_dir=str(PROJECT_ROOT / "src")))
    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "failure_names": [str(f[0]) for f in result.failures[:25]],
        "error_names": [str(e[0]) for e in result.errors[:25]],
    }


def build_bundle() -> dict[str, Any]:
    script = write_autostart_script()
    spread = analyze_live_spreads()
    qual = build_live_evidence_qualification()
    p7_m5, p7_q = _load_prompt7_counts()
    audit = build_broker_economics_audit(
        live_m5=int(qual.get("unique_newly_closed_live_m5_bars") or 0),
        live_quotes=int(qual.get("live_quote_observations") or 0),
        complete_dates=int(qual.get("n_complete_independent_live_dates") or 0),
        prompt7_live_m5=p7_m5,
        prompt7_quotes=p7_q,
    )
    dist = spread.get("distribution_price_units") or {}
    dist_pts = spread.get("distribution_points") or {}
    cost = build_cost_model(
        observed_spread_price_median=dist.get("median"),
        observed_spread_points_median=dist_pts.get("median"),
        spread_n=int(spread.get("n_usable_quotes") or 0),
        commission_status=(audit.get("commission_summary") or {}).get("status", "UNKNOWN"),
        commission_value=(audit.get("commission_summary") or {}).get("value", "UNKNOWN"),
        swap_status="CONFLICTED",
        swap_value=(audit.get("swap_summary") or {}).get("observations_preserved"),
    )
    # Illustrative sensitivity only — NOT a strategy screen
    sens = evaluate_trade_cost_sensitivity(
        entry=2650.0,
        stop_loss=2648.0,
        take_profit=2654.0,
        holding_bars=12,
        direction="BUY",
        observed_spread_price=dist.get("median"),
        commission_r=None,
        swap_r_per_night=None,
        nights=0,
        slippage_r=None,
        cost_model=cost,
    )
    reliability = inspect_collector_reliability()
    c07 = build_c07_a_readiness()
    verdict = _choose_verdict(cost=cost, spread=spread, reliability=reliability)
    return {
        "generated_utc": _utc(),
        "prompt": "PROMPT_08",
        "primary_verdict": verdict,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "h70": H70_STATUS,
        "order_send": ORDER_SEND,
        "discord_actionable": DISCORD_ACTIONABLE,
        "cost_model_version": COST_MODEL_VERSION,
        "audit": audit,
        "spread": spread,
        "cost_model": cost,
        "sensitivity_example": sens,
        "live_evidence": qual,
        "collector_reliability": reliability,
        "c07_readiness": c07,
        "autostart_script": str(script),
        "prompt09_started": False,
    }


def write_reports(bundle: dict[str, Any], tests: dict[str, Any]) -> list[str]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    _json(REPORTS / "PROMPT_08_BUNDLE.json", {**bundle, "test_results": tests})
    created.append(str(REPORTS / "PROMPT_08_BUNDLE.json"))

    audit = bundle["audit"]
    spread = bundle["spread"]
    cost = bundle["cost_model"]
    live = bundle["live_evidence"]
    rel = bundle["collector_reliability"]
    c07 = bundle["c07_readiness"]
    sens = bundle["sensitivity_example"]

    p1 = REPORTS / "PROMPT_08_BROKER_ECONOMICS_AUDIT.md"
    _write(
        p1,
        "\n".join(
            [
                "# PROMPT 08 — Broker Economics Audit",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Primary verdict: `{bundle['primary_verdict']}`",
                "",
                "## Live evidence vs Prompt7",
                "",
                "```json",
                json.dumps(audit.get("live_evidence_vs_prompt7"), indent=2),
                "```",
                "",
                "## Commission / swap summaries",
                "",
                "```json",
                json.dumps({"commission": audit.get("commission_summary"), "swap": audit.get("swap_summary")}, indent=2),
                "```",
                "",
                "## Metadata fields",
                "",
                "```json",
                json.dumps(audit.get("fields"), indent=2),
                "```",
                "",
                "## Missing / incomplete",
                "",
                "\n".join(f"- {x}" for x in (audit.get("missing_stale_contradictory_incomplete") or [])),
                "",
                "## Safety",
                "",
                "```json",
                json.dumps(audit.get("safety"), indent=2),
                "```",
                "",
            ]
        ),
    )
    created.append(str(p1))

    p2 = REPORTS / "PROMPT_08_SPREAD_ANALYSIS.md"
    _write(
        p2,
        "\n".join(
            [
                "# PROMPT 08 — Spread Analysis",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Analysis version: `{spread.get('analysis_version')}`",
                "",
                f"- Usable quotes: **{spread.get('n_usable_quotes')}**",
                f"- Rejected: **{spread.get('n_rejected')}**",
                "",
                "## Distribution (price units = ask−bid)",
                "",
                "```json",
                json.dumps(spread.get("distribution_price_units"), indent=2),
                "```",
                "",
                "## Distribution (points)",
                "",
                "```json",
                json.dumps(spread.get("distribution_points"), indent=2),
                "```",
                "",
                "## By PKT hour",
                "",
                "```json",
                json.dumps(
                    {
                        "median_price": spread.get("by_pkt_hour_median_price"),
                        "n": spread.get("by_pkt_hour_n"),
                    },
                    indent=2,
                ),
                "```",
                "",
                "## By session bucket",
                "",
                "```json",
                json.dumps(spread.get("by_session_bucket"), indent=2),
                "```",
                "",
                "## Limitations",
                "",
                "\n".join(f"- {x}" for x in (spread.get("limitations") or [])),
                "",
                "```json",
                json.dumps(spread.get("high_volatility_periods"), indent=2),
                "```",
                "",
            ]
        ),
    )
    created.append(str(p2))

    p3 = REPORTS / "PROMPT_08_COST_MODEL.md"
    _write(
        p3,
        "\n".join(
            [
                "# PROMPT 08 — Cost Model",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Version: `{cost.get('cost_model_version')}`",
                f"Production approved: `{cost.get('production_approved')}`",
                f"NET_PROFITABILITY: `{cost.get('NET_PROFITABILITY')}`",
                "",
                "## Components",
                "",
                "```json",
                json.dumps(cost.get("components"), indent=2),
                "```",
                "",
                "## Hypothetical scenarios (not actual broker costs)",
                "",
                "```json",
                json.dumps(cost.get("hypothetical_scenarios"), indent=2),
                "```",
                "",
                "## Sensitivity framework example (illustrative only)",
                "",
                "```json",
                json.dumps(sens, indent=2),
                "```",
                "",
                "_Unknown components are never treated as zero. H70 not retuned. C07_A not screened._",
                "",
            ]
        ),
    )
    created.append(str(p3))

    p4 = REPORTS / "PROMPT_08_LIVE_EVIDENCE_STATUS.md"
    _write(
        p4,
        "\n".join(
            [
                "# PROMPT 08 — Live Evidence Status",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"- Target complete dates: **{live.get('target_complete_independent_dates')}**",
                f"- Complete independent live dates: **{live.get('n_complete_independent_live_dates')}**",
                f"- Target met: `{live.get('target_met')}`",
                f"- Unique live M5: **{live.get('unique_newly_closed_live_m5_bars')}**",
                f"- Live quotes: **{live.get('live_quote_observations')}**",
                f"- Backfill M5 (excluded from qualification): **{live.get('unique_historical_backfill_m5_bars')}**",
                "",
                "## Incomplete dates",
                "",
                "```json",
                json.dumps(live.get("incomplete_date_ids"), indent=2),
                "```",
                "",
                "## Date records",
                "",
                "```json",
                json.dumps(live.get("incomplete_date_records"), indent=2),
                "```",
                "",
                f"- Phase58 accessed: `{live.get('phase58_holdout_accessed')}`",
                f"- Backfill mixed into qualification: `{not live.get('backfill_never_combined_with_live_for_qualification')}`",
                "",
            ]
        ),
    )
    created.append(str(p4))

    p5 = REPORTS / "PROMPT_08_COLLECTOR_RELIABILITY.md"
    _write(
        p5,
        "\n".join(
            [
                "# PROMPT 08 — Collector Reliability",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "## Health",
                "",
                "```json",
                json.dumps(rel.get("health"), indent=2),
                "```",
                "",
                "## Single-instance",
                "",
                "```json",
                json.dumps(rel.get("single_instance"), indent=2),
                "```",
                "",
                "## Capabilities (implemented vs tested)",
                "",
                "```json",
                json.dumps(rel.get("capabilities"), indent=2),
                "```",
                "",
                "## Windows autostart",
                "",
                "```json",
                json.dumps(rel.get("windows_autostart"), indent=2),
                "```",
                "",
                f"Script: `{bundle.get('autostart_script')}`",
                "",
                "**Reboot recovery is NOT claimed.** Install/verify manually:",
                "",
                "```powershell",
                "powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action install",
                "powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action verify",
                "```",
                "",
            ]
        ),
    )
    created.append(str(p5))

    p6 = REPORTS / "PROMPT_08_C07_READINESS.md"
    _write(
        p6,
        "\n".join(
            [
                "# PROMPT 08 — C07_A Readiness",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                f"Status: `{c07.get('status')}`",
                f"Strategy implemented: `{c07.get('strategy_implemented')}`",
                "",
                "## Missing from original rationale",
                "",
                "\n".join(f"- {x}" for x in (c07.get("missing_from_original_discovery_rationale") or [])),
                "",
                "## Prerequisites",
                "",
                "```json",
                json.dumps(c07.get("prerequisites_before_preregistration_and_evaluation"), indent=2),
                "```",
                "",
                "## Current blockers",
                "",
                "\n".join(f"- {x}" for x in (c07.get("current_blockers") or [])),
                "",
            ]
        ),
    )
    created.append(str(p6))

    p7 = REPORTS / "PROMPT_08_TEST_RESULTS.md"
    _write(
        p7,
        "\n".join(
            [
                "# PROMPT 08 — Test Results",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(tests, indent=2),
                "```",
                "",
                "## Commands",
                "",
                "```text",
                ".venv\\Scripts\\python.exe -m signal_bot.execution_economics.run_prompt08",
                ".venv\\Scripts\\python.exe -m unittest discover -s src/signal_bot/execution_economics/tests -t src",
                "```",
                "",
                f"- Prompt9 started: `{bundle.get('prompt09_started')}`",
                "",
            ]
        ),
    )
    created.append(str(p7))

    p8 = REPORTS / "PROMPT_08_OPERATIONS_GUIDE.md"
    _write(
        p8,
        "\n".join(
            [
                "# PROMPT 08 — Operations Guide",
                "",
                "## Safety invariants",
                "",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- H70: `{H70_STATUS}`",
                f"- order_send: `{ORDER_SEND}`",
                "- Broker collection: READ_ONLY",
                "- Discord actionable: DISABLED",
                "",
                "## Collector",
                "",
                "```powershell",
                "$env:PYTHONPATH = \"$PWD\\src\"",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli health",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli evidence",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli report",
                "# start only if not running (single-instance protected)",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli start --interval 30",
                "```",
                "",
                "## Execution economics refresh",
                "",
                "```powershell",
                ".\\.venv\\Scripts\\python.exe -m signal_bot.execution_economics.run_prompt08",
                "```",
                "",
                "## Windows autostart (optional)",
                "",
                "```powershell",
                "powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action install",
                "powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action verify",
                "```",
                "",
                "After a reboot, re-run verify and confirm a single RUNNING collector PID. Do not claim reboot recovery until that test is done.",
                "",
                "## Do not",
                "",
                "- Open demo/live orders to discover commission",
                "- Treat UNKNOWN costs as zero",
                "- Mix backfill into independent live date qualification",
                "- Access Phase58 holdout",
                "- Start Prompt9 automatically",
                "",
            ]
        ),
    )
    created.append(str(p8))
    return created


def main() -> int:
    if str(PROJECT_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
    bundle = build_bundle()
    tests = _run_tests()
    files = write_reports(bundle, tests)
    print(
        json.dumps(
            {
                "primary_verdict": bundle["primary_verdict"],
                "usable_quotes": bundle["spread"].get("n_usable_quotes"),
                "live_m5": bundle["live_evidence"].get("unique_newly_closed_live_m5_bars"),
                "complete_dates": bundle["live_evidence"].get("n_complete_independent_live_dates"),
                "collector": (bundle["collector_reliability"].get("health") or {}).get("service_status"),
                "NET_PROFITABILITY": bundle["cost_model"].get("NET_PROFITABILITY"),
                "tests_ok": tests.get("ok"),
                "tests_run": tests.get("tests_run"),
                "files": files,
            },
            indent=2,
        )
    )
    return 0 if tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
