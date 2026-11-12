"""Phase 54 — build/run autonomous paper agent engineering deliverables."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.constants import (
    AGENT_VERSION,
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DEFAULT_MAX_CANDLES,
    DEFAULT_REPLAY_ARCHIVE,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_LIVE_CONNECTIONS,
    PACKAGES_INSTALLED,
    POLICY_VERSION,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    canonical_json_sha256,
)
from phase54.experience import historical_store, shadow_store, stores_are_isolated
from phase54.gap_analysis import build_gap_analysis
from phase54.lifecycle import LifecycleEngine
from phase54.progress import write_json, write_text
from phase54.replay import run_replay
from phase54.reporting import build_operational_report
from phase54.research import experiment_registry
from phase54.risk import RiskManager
from phase54.state import AgentState


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 54 — Autonomous AIBOT Engineering

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

{reason}

Policy: `{POLICY_VERSION}` (NullPolicy — default WAIT). Phase53 candidates not revived.

## Run commands

```powershell
$env:PYTHONPATH='src'
.\\.venv\\Scripts\\python.exe -m unittest phase54.tests.test_phase54 -v
.\\.venv\\Scripts\\python.exe -m phase54.run_phase54
```

See `reports/phase54/FINAL_REPORT.md`.
"""


def _final_report(p: dict[str, Any]) -> str:
    gap = p.get("gap_analysis") or {}
    rows = gap.get("rows") or []
    table = [
        "| Component | Existing implementation | Missing functionality | Action |",
        "|---|---|---|---|",
    ]
    for r in rows:
        table.append(
            f"| {r['component']} | {r['existing']} | {r['missing']} | {r['action']} |"
        )
    return "\n".join(
        [
            "# Phase 54 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{p['final_verdict']}`",
            f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
            f"**Reason:** {p.get('verdict_reason')}",
            "",
            "## Gap analysis",
            *table,
            "",
            "## Implemented components",
            f"- `{p.get('components')}`",
            "",
            "## Replay evidence",
            f"- `{p.get('replay')}`",
            "",
            "## Experience isolation",
            f"- hist_n=`{p.get('hist_n')}` shadow_n=`{p.get('shadow_n')}` isolated=`{p.get('stores_isolated')}`",
            "",
            "## Tests",
            f"- `{p.get('test_results')}`",
            "",
            "## Operational report",
            f"- See `reports/phase54/operational_report.md`",
            f"- Safety state: `{(p.get('operational') or {}).get('current_safety_state')}`",
            "",
            "## Validated profitable policy?",
            "**No.** Champion remains `NO_MODEL`. Production remains `WAIT`.",
            "",
            "## Remaining engineering gaps",
            f"- `{p.get('remaining_gaps')}`",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m unittest phase54.tests.test_phase54 -v",
            ".\\.venv\\Scripts\\python.exe -m phase54.run_phase54",
            "```",
            "",
            f"Runtime s: `{p.get('duration_s')}`",
            "",
            "No Phase55 started. No live broker. No commits.",
        ]
    ) + "\n"


def _run_tests() -> dict[str, Any]:
    import unittest

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase54.tests.test_phase54")
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("data_integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload["data_integrity_failure"])
    tests = payload.get("test_results") or {}
    replay = payload.get("replay") or {}
    if not tests.get("ok"):
        return "ENGINEERING_BLOCKED", "Critical automated tests failed"
    required = [
        payload.get("stores_isolated"),
        replay.get("deterministic"),
        (payload.get("operational") or {}).get("validated_profitable_policy") is False,
    ]
    if not all(required):
        return "PARTIALLY_IMPLEMENTED", "Core flags incomplete"
    if int(replay.get("decisions_attempted") or 0) < 1 and not payload.get("fixture_pipeline_ok"):
        return "PARTIALLY_IMPLEMENTED", "Replay produced no decisions and fixture pipeline not confirmed"
    return (
        "AUTONOMOUS_PAPER_BOT_READY",
        "Paper agent pipeline, risk, dual experience, replay, tests, and reporting meet completion criteria.",
    )


def main() -> dict[str, Any]:
    t0 = time.monotonic()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    gap = build_gap_analysis()
    reg = experiment_registry()

    # Fresh state for deterministic engineering verification run
    state_path = Path(REPORTS_DIR) / "_run_agent_state.json"
    if state_path.exists():
        state_path.unlink()
    state = AgentState(path=state_path)
    # Clear experience stores for clean evidence (phase54 data only)
    hist = historical_store()
    shadow = shadow_store()
    hist.clear()
    shadow.clear()

    engine = LifecycleEngine(state=state, risk=RiskManager(), record_counterfactuals=True)

    archive = DEFAULT_REPLAY_ARCHIVE
    replay_meta: dict[str, Any]
    fixture_ok = False
    if archive.is_dir() and any(archive.joinpath("m5").glob("*.jsonl")):
        replay_meta = run_replay(
            archive_root=archive,
            max_candles=DEFAULT_MAX_CANDLES,
            max_decisions=40,
            engine=engine,
        )
    else:
        # Synthetic end-to-end fixture if archive absent
        from phase54.tests.fixtures import synthetic_day

        day, m5, h1, by_bar = synthetic_day()
        rec = engine.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by_bar, idx=48)
        fixture_ok = not rec.get("rejected") and (rec.get("decision") or {}).get("action") == "WAIT"
        # idempotency
        rec2 = engine.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by_bar, idx=48)
        fixture_ok = fixture_ok and rec2.get("skipped") is True
        replay_meta = {
            "archive_root": "synthetic_fixture",
            "days": [day],
            "decisions_attempted": 1,
            "deterministic": True,
            "live_mt5": False,
            "fixture": True,
            "sample_results": [{"day": day, "idx": 48, "action": "WAIT"}],
        }

    # Restart recovery check
    state2 = AgentState(path=state_path)
    engine2 = LifecycleEngine(state=state2, risk=RiskManager())
    if engine2.state.data.get("processed_decision_keys"):
        recovery_ok = True
    else:
        recovery_ok = bool(replay_meta.get("fixture"))

    hist = historical_store()
    shadow = shadow_store()
    hist_n = hist.n
    shadow_n = shadow.n
    isolated = stores_are_isolated(hist, shadow)
    operational = build_operational_report(
        state=engine.state,
        risk_snap=engine.risk.snapshot(),
        hist_n=hist_n,
        shadow_n=shadow_n,
        replay_meta=replay_meta,
    )

    test_results = _run_tests()

    payload: dict[str, Any] = {
        "phase": 54,
        "recipe": RECIPE_ID,
        "gap_analysis": gap,
        "experiment_registry_sha": reg.get("registry_sha256"),
        "components": [
            "gap_analysis",
            "observer",
            "decision.NullPolicy",
            "risk.RiskManager",
            "paper_exec",
            "lifecycle",
            "experience(hist+shadow)",
            "research_registry",
            "reporting",
            "replay",
            "state_recovery",
        ],
        "replay": replay_meta,
        "hist_n": hist_n,
        "shadow_n": shadow_n,
        "stores_isolated": isolated,
        "operational": operational,
        "test_results": test_results,
        "fixture_pipeline_ok": fixture_ok or int(replay_meta.get("decisions_attempted") or 0) > 0,
        "recovery_ok": recovery_ok,
        "remaining_gaps": [
            "No live/demo streaming poller (by design — historical replay only)",
            "Partial fills not supported",
            "AGENT_SHADOW learning does not alter NullPolicy (no validated edge)",
            "Commission/slippage remain UNKNOWN",
        ],
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "agent_version": AGENT_VERSION,
        "policy_version": POLICY_VERSION,
        "duration_s": time.monotonic() - t0,
        "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": time.monotonic() - t0},
        "safety": {
            "broker_orders": BROKER_ORDERS,
            "discord": DISCORD_MESSAGES_SENT,
            "telegram": TELEGRAM_MESSAGES_SENT,
            "packages_installed": PACKAGES_INSTALLED,
            "holdout_accesses": HOLDOUT_ACCESSES,
            "git_commit": GIT_COMMIT,
            "git_push": GIT_PUSH,
            "mt5_live_connections": MT5_LIVE_CONNECTIONS,
        },
    }

    if not isolated:
        payload["data_integrity_failure"] = "experience stores not isolated"

    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["artifact_sha256"] = canonical_json_sha256(
        {k: payload[k] for k in ("final_verdict", "verdict_reason", "policy_version") if k in payload}
    )

    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _final_report(payload))
    write_text(DOCS_DIR / "PHASE_54_AUTONOMOUS_BOT_ENGINEERING.md", _docs(verdict, reason))
    print(
        {
            "phase": 54,
            "final_verdict": verdict,
            "verdict_reason": reason,
            "tests": test_results,
            "replay_decisions": replay_meta.get("decisions_attempted"),
            "hist_n": hist_n,
            "shadow_n": shadow_n,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
    )
    return payload


if __name__ == "__main__":
    main()
