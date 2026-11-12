"""Phase 56 — verify integrated SL/TP lifecycle + bounded autonomous replay."""

from __future__ import annotations

import shutil
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase55.engineering_policy import EngineeringTestPolicy
from phase55.independent import compare_to_engine, recompute_path
from phase56.constants import (
    ARCHIVE_ROOT,
    CHAMPION_STATUS,
    DATA_ROOT,
    DOCS_DIR,
    HIST_DIR,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SHADOW_DIR,
    STATE_DIR,
    canonical_json_sha256,
)
from phase56.defect import reproduce_sl_tp_defect
from phase56.health import build_health_report
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.poller import BoundedPoller
from phase56.progress import write_json, write_text
from phase56.provider import HistoricalReplayProvider
from phase56.research import research_readiness_registry
from phase56.shutdown import graceful_shutdown
from phase56.tests.fixtures import directional_path


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clear_runtime() -> None:
    for d in (STATE_DIR, HIST_DIR, SHADOW_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromName("phase56.tests.test_phase56"))
    suite.addTests(loader.loadTestsFromName("phase55.tests.test_phase55"))
    suite.addTests(loader.loadTestsFromName("phase54.tests.test_phase54"))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def choose_verdict(p: dict[str, Any]) -> tuple[str, str]:
    if p.get("data_integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(p["data_integrity_failure"])
    need = [
        p.get("defect_confirmed"),
        p.get("sl_tp_integrated"),
        p.get("buy_sl_ok"),
        p.get("sell_tp_ok"),
        p.get("poller_ok"),
        p.get("recovery_ok"),
        p.get("null_policy_ok"),
        (p.get("test_results") or {}).get("ok"),
    ]
    if all(need):
        return (
            "AUTONOMOUS_REPLAY_AGENT_READY",
            "SL/TP integrated into lifecycle; bounded historical replay, recovery, and regressions passed.",
        )
    missing = [k for k, v in {
        "defect": p.get("defect_confirmed"),
        "sl_tp": p.get("sl_tp_integrated"),
        "buy_sl": p.get("buy_sl_ok"),
        "sell_tp": p.get("sell_tp_ok"),
        "poller": p.get("poller_ok"),
        "recovery": p.get("recovery_ok"),
        "null": p.get("null_policy_ok"),
        "tests": (p.get("test_results") or {}).get("ok"),
    }.items() if not v]
    if p.get("sl_tp_integrated") or p.get("poller_ok"):
        return "PARTIALLY_IMPLEMENTED", f"Incomplete: {missing}"
    return "ENGINEERING_BLOCKED", f"Blocked: {missing}"


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 56 — Autonomous Observer & Lifecycle Integration

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

{reason}

Phase54 source unmodified. `IntegratedLifecycleEngine` subclasses LifecycleEngine and wires `monitor_and_maybe_exit`.

## Commands

```powershell
$env:PYTHONPATH='src'
.\\.venv\\Scripts\\python.exe -m unittest phase56.tests.test_phase56 phase55.tests.test_phase55 phase54.tests.test_phase54 -v
.\\.venv\\Scripts\\python.exe -m phase56.run_phase56
.\\.venv\\Scripts\\python.exe -m phase56.cli --max-candles 20
```

See `reports/phase56/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 56 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{p['final_verdict']}`",
            f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
            f"**Reason:** {p.get('verdict_reason')}",
            "",
            "## Defect investigation",
            f"- `{p.get('defect')}`",
            "",
            "## Files changed (Phase56 only)",
            f"- `{p.get('files_changed')}`",
            "",
            "## SL/TP integration evidence",
            f"- buy_sl: `{p.get('buy_sl')}`",
            f"- sell_tp: `{p.get('sell_tp')}`",
            f"- independent: `{p.get('independent')}`",
            "",
            "## Bounded replay",
            f"- `{p.get('poller')}`",
            "",
            "## Restart recovery",
            f"- `{p.get('recovery')}`",
            "",
            "## Tests",
            f"- `{p.get('test_results')}`",
            "",
            "## Health",
            f"- See `reports/phase56/operational_health.md`",
            "",
            "## Limitations",
            "- Historical replay verified only — not streaming/live MT5 readiness",
            "- No profitable trading claim; NullPolicy remains production default",
            "- Phase0–55 unmodified",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m unittest phase56.tests.test_phase56 phase55.tests.test_phase55 phase54.tests.test_phase54 -v",
            ".\\.venv\\Scripts\\python.exe -m phase56.run_phase56",
            ".\\.venv\\Scripts\\python.exe -m phase56.cli --max-candles 20",
            "```",
            "",
            f"Runtime s: `{p.get('duration_s')}`",
            "",
            "No Phase57 started.",
        ]
    ) + "\n"


def main() -> dict[str, Any]:
    t0 = time.monotonic()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    _clear_runtime()

    defect = reproduce_sl_tp_defect()
    research_readiness_registry()

    # --- BUY SL on synthetic via integrated engine ---
    day, m5, h1, by = directional_path(move_after_entry=-5.0)
    eng_buy = IntegratedLifecycleEngine(
        state=AgentState(path=STATE_DIR / "buy_sl.json"),
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
        immediate_monitor_through_horizon=True,
    )
    buy = eng_buy.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    buy_sl_ok = (
        buy.get("sl_tp_integrated")
        and (buy.get("closed") or {}).get("exit_reason") == "STOP_LOSS"
        and (buy.get("closed") or {}).get("exit_fill") == (buy.get("closed") or {}).get("exit_bid")
    )
    indep_buy = None
    if buy.get("closed"):
        indep_buy = recompute_path(
            side="BUY",
            m5=m5,
            ticks_by_bar=by,
            entry_idx=int(buy["closed"]["entry_idx"]),
            horizon_bars=12,
            atr=buy["closed"].get("atr_at_entry"),
            stop_distance=abs(float(buy["closed"]["entry_fill"]) - float(buy["closed"]["stop_loss"])),
        )
        indep_buy = compare_to_engine(buy["closed"], indep_buy)

    # --- SELL TP ---
    day2, m52, h12, by2 = directional_path(day="2099-06-04", move_after_entry=-5.0)
    eng_sell = IntegratedLifecycleEngine(
        state=AgentState(path=STATE_DIR / "sell_tp.json"),
        policy=EngineeringTestPolicy(["SELL"]),
        risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
        immediate_monitor_through_horizon=True,
    )
    sell = eng_sell.process_bar(day=day2, m5=m52, h1=h12, ticks_by_bar=by2, idx=48)
    sell_tp_ok = (sell.get("closed") or {}).get("exit_reason") == "TAKE_PROFIT" and (
        sell["closed"]["exit_fill"] == sell["closed"]["exit_ask"]
    )

    # --- NullPolicy bounded poller on real archive ---
    _clear_runtime()
    eng = IntegratedLifecycleEngine(
        state=AgentState(path=STATE_DIR / "agent_state.json"),
        policy=NullPolicy(),
        immediate_monitor_through_horizon=False,
    )
    provider = HistoricalReplayProvider(days=list_archived_m5_days_safe(), stride=12, max_candles=30)
    poller = BoundedPoller(
        eng,
        provider,
        config={"max_candles": 30, "max_iterations": 100, "max_wall_seconds": 90, "checkpoint_every": 5},
    )
    poll_meta = poller.run()
    health = build_health_report(eng, poll_meta)
    poller_ok = (
        poll_meta.get("stop_reason") in ("max_candles", "COMPLETED", "max_iterations")
        and poll_meta.get("live_mt5") is False
        and poll_meta.get("auto_started") is False
        and int(poll_meta.get("candles") or 0) > 0
    )
    null_policy_ok = isinstance(eng.policy, NullPolicy)

    # --- Recovery demo ---
    day3, m53, h13, by3 = directional_path(day="2099-06-05", move_after_entry=0.0)
    sp = STATE_DIR / "recovery.json"
    if sp.exists():
        sp.unlink()
    e1 = IntegratedLifecycleEngine(
        state=AgentState(path=sp),
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0}),
        immediate_monitor_through_horizon=False,
    )
    d1 = e1.process_bar(day=day3, m5=m53, h1=h13, ticks_by_bar=by3, idx=48)
    open_n = len(e1.risk.open_positions)
    graceful_shutdown(e1, reason="RECOVERY_TEST")
    e2 = IntegratedLifecycleEngine(state=AgentState(path=sp), policy=NullPolicy(), immediate_monitor_through_horizon=False)
    recovered_open = len(e2.risk.open_positions) == open_n == 1
    # close via monitor after price drop
    pid = next(iter(e2.risk.open_positions))
    pos = e2.risk.open_positions[pid]
    pos["stop_loss"] = float(pos["entry_fill"]) - 0.01
    pos["take_profit"] = float(pos["entry_fill"]) + 100
    for j in range(49, 55):
        ts = str(m53[j]["timestamp_utc"])
        px = float(pos["entry_fill"]) - 1.0
        by3[ts] = [{"epoch_ms": j, "timestamp_utc": ts, "bid": px, "ask": px + 0.1}]
    closed = e2.monitor_open_positions(day=day3, m5=m53, ticks_by_bar=by3, current_idx=54)
    recovery_ok = recovered_open and len(closed) == 1 and e2.process_bar(day=day3, m5=m53, h1=h13, ticks_by_bar=by3, idx=48).get("skipped")

    test_results = _run_tests()

    files_changed = sorted(
        str(p.relative_to(Path(__file__).resolve().parents[2])) if False else str(p)
        for p in Path(__file__).resolve().parent.rglob("*.py")
    )
    # simplify list
    root = Path(__file__).resolve().parent
    files_changed = sorted(str(p.relative_to(root.parent.parent)) for p in root.rglob("*.py"))

    payload: dict[str, Any] = {
        "phase": 56,
        "recipe": RECIPE_ID,
        "defect": defect,
        "defect_confirmed": bool(defect.get("defect_confirmed")),
        "sl_tp_integrated": bool(buy.get("sl_tp_integrated")),
        "buy_sl": {
            "ok": buy_sl_ok,
            "exit_reason": (buy.get("closed") or {}).get("exit_reason"),
            "entry_fill": (buy.get("closed") or {}).get("entry_fill"),
            "exit_fill": (buy.get("closed") or {}).get("exit_fill"),
            "trace_stages": [t.get("stage") for t in (buy.get("trace") or [])],
        },
        "buy_sl_ok": buy_sl_ok and (indep_buy or {}).get("ok"),
        "sell_tp": {
            "ok": sell_tp_ok,
            "exit_reason": (sell.get("closed") or {}).get("exit_reason"),
            "exit_fill": (sell.get("closed") or {}).get("exit_fill"),
            "exit_ask": (sell.get("closed") or {}).get("exit_ask"),
        },
        "sell_tp_ok": sell_tp_ok,
        "independent": indep_buy,
        "poller": poll_meta,
        "poller_ok": poller_ok,
        "recovery": {"open_n": open_n, "closed": (closed[0].get("exit_reason") if closed else None), "ok": recovery_ok},
        "recovery_ok": recovery_ok,
        "null_policy_ok": null_policy_ok,
        "health": {
            "policy": health.get("policy_version"),
            "streaming_ready": health.get("streaming_ready"),
            "actions": health.get("action_counts"),
        },
        "test_results": test_results,
        "files_changed": files_changed,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "duration_s": time.monotonic() - t0,
        "runtime": {"START_UTC": start, "END_UTC": _utc()},
        "limitations": [
            "Historical replay only — not live streaming",
            "No profitable policy",
            "Phase0-55 unmodified",
        ],
    }

    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["artifact_sha256"] = canonical_json_sha256(
        {k: payload[k] for k in ("final_verdict", "verdict_reason") if k in payload}
    )
    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(DOCS_DIR / "PHASE_56_AUTONOMOUS_OBSERVER_LIFECYCLE.md", _docs(verdict, reason))
    print(
        {
            "phase": 56,
            "final_verdict": verdict,
            "verdict_reason": reason,
            "buy_sl_ok": buy_sl_ok,
            "sell_tp_ok": sell_tp_ok,
            "tests": test_results,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
    )
    return payload


def list_archived_m5_days_safe() -> list[str]:
    from phase54.archive_loader import list_archived_m5_days

    days = list_archived_m5_days(ARCHIVE_ROOT)
    return days[:3] if days else []


if __name__ == "__main__":
    main()
