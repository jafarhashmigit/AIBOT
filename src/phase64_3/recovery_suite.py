"""Recovery & idempotency — in-process crash gates + subprocess crash."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase57_1.journal import CrashInjected as DurableCrash
from phase64.execution_intent import CrashInjected as IntentCrash
from phase64_1.market_snapshot import CrashInjected as SnapCrash
from phase64_2.constants import STATUS_PAPER_FINALIZED, STATUS_WAIT_FINALIZED
from phase64_2.intent_state import CrashInjected
from phase64_3.approved_runtime import make_approved_paper_engine, summarize_engine_counts
from phase64_3.constants import canonical_json_sha256
from phase64_3.xauusdm_profile import active_account_profile

PROFILE = active_account_profile()
CRASH_TYPES = (CrashInjected, IntentCrash, DurableCrash, SnapCrash)


def _case_inprocess(crash_at: str, *, action: str = "BUY") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        day, m5, h1, by = directional_path(day="2099-12-10", n_bars=100, move_after_entry=-5.0)
        eng = make_approved_paper_engine(
            work=work,
            policy=EngineeringTestPolicy([action]),
            risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            crash_at=crash_at,
            immediate_monitor_through_horizon=True,
            account_profile=PROFILE,
        )
        raised = None
        try:
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        except CRASH_TYPES as exc:
            raised = str(exc)

        eng2 = make_approved_paper_engine(
            work=work,
            policy=EngineeringTestPolicy([action]),
            crash_at=None,
            immediate_monitor_through_horizon=True,
            account_profile=PROFILE,
        )
        eng2.recover_pending()
        eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        # After paper-entry crash: monitor subsequent bars WITHOUT new decisions (avoid extra intents)
        if crash_at == "after_paper_entry" or eng2.risk.open_positions:
            for idx in range(49, min(80, len(m5) - 1)):
                eng2.monitor_open_positions(day=day, m5=m5, ticks_by_bar=by, current_idx=idx)
                eng2.persist()
                if not eng2.risk.open_positions:
                    break
            eng2.recover_pending()
        c1 = summarize_engine_counts(eng2)
        eng2.recover_pending()
        eng2.recover_pending()
        c2 = summarize_engine_counts(eng2)
        eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        intents = eng2.intent_journal.all_intents()
        pending_closed = []
        closed = set(eng2.state.data.get("closed_position_ids") or [])
        for i in intents:
            if i.get("intent_status") == "PENDING":
                for r in eng2.intent_journal.all_records():
                    if r.get("intent_id") == i.get("intent_id") and r.get("stage") == "OUTCOME_RECORDED":
                        pid = (r.get("payload") or {}).get("position_id")
                        if pid in closed:
                            pending_closed.append(i.get("intent_id"))
        if action == "BUY":
            terminal = any(i.get("intent_status") == STATUS_PAPER_FINALIZED for i in intents)
        else:
            terminal = any(i.get("intent_status") == STATUS_WAIT_FINALIZED for i in intents)
        idempotent = (
            c1["n_intents"] == c2["n_intents"]
            and c1["n_wait_durable_experiences"] == c2["n_wait_durable_experiences"]
            and c1["n_canonical_decisions"] == c2["n_canonical_decisions"]
        )
        return {
            "case": crash_at,
            "mode": "in_process_exception",
            "crash_raised": raised,
            "n_intents": len(intents),
            "pending_closed": pending_closed,
            "terminal_ok": terminal,
            "idempotent_repeated_recovery": idempotent,
            "pass": raised is not None
            and len(intents) == 1
            and not pending_closed
            and terminal
            and idempotent,
            "genuine_broker_deals": 0,
        }


def _subprocess_crash_test() -> dict[str, Any]:
    """Real subprocess: child hits crash gate then os._exit; parent recovers."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        marker = work / "child_done.txt"
        src_dir = Path(__file__).resolve().parents[1]
        script = work / "child_crash.py"
        script.write_text(
            "\n".join(
                [
                    "import os, sys",
                    "from pathlib import Path",
                    f"sys.path.insert(0, r'{src_dir}')",
                    "from phase55.engineering_policy import EngineeringTestPolicy",
                    "from phase56.tests.fixtures import directional_path",
                    "from phase64_3.approved_runtime import make_approved_paper_engine",
                    "from phase64_3.xauusdm_profile import active_account_profile",
                    f"work = Path(r'{work}')",
                    "day, m5, h1, by = directional_path(day='2099-12-11', n_bars=100)",
                    "eng = make_approved_paper_engine(",
                    "    work=work,",
                    "    policy=EngineeringTestPolicy(['WAIT']),",
                    "    crash_at='during_wait_experience_append',",
                    "    account_profile=active_account_profile(),",
                    ")",
                    "try:",
                    "    eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)",
                    "except Exception as e:",
                    "    (work / 'child_done.txt').write_text(str(e), encoding='utf-8')",
                    "    os._exit(99)",
                    "(work / 'child_done.txt').write_text('NO_CRASH', encoding='utf-8')",
                    "os._exit(0)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_dir)
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(work),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        child_ran = marker.is_file()
        eng = make_approved_paper_engine(
            work=work,
            policy=EngineeringTestPolicy(["WAIT"]),
            account_profile=PROFILE,
        )
        eng.recover_pending()
        day, m5, h1, by = directional_path(day="2099-12-11", n_bars=100)
        eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        counts = summarize_engine_counts(eng)
        st = (
            eng.intent_journal.all_intents()[0].get("intent_status")
            if eng.intent_journal.all_intents()
            else None
        )
        return {
            "case": "subprocess_crash_during_wait",
            "mode": "subprocess_os_exit",
            "child_exitcode": proc.returncode,
            "child_ran": child_ran,
            "child_marker": marker.read_text(encoding="utf-8") if child_ran else None,
            "n_intents": counts["n_intents"],
            "n_wait_exp": counts["n_wait_durable_experiences"],
            "intent_status": st,
            "pass": child_ran
            and counts["n_intents"] == 1
            and counts["n_wait_durable_experiences"] == 1
            and st == STATUS_WAIT_FINALIZED,
            "stderr_tail": (proc.stderr or "")[-800:],
            "genuine_broker_deals": 0,
        }


def run_recovery_suite() -> dict[str, Any]:
    points = [
        ("after_snapshot_persistence", "BUY"),
        ("after_decision_persistence", "BUY"),
        ("after_risk_approval", "BUY"),
        ("before_intent_persistence", "BUY"),
        ("after_intent_before_paper_entry", "BUY"),
        ("after_paper_entry", "BUY"),
        ("after_durable_outcome_before_intent_status", "BUY"),
        ("during_wait_experience_append", "WAIT"),
        ("after_wait_experience_before_intent_finalize", "WAIT"),
    ]
    cases = [_case_inprocess(p, action=a) for p, a in points]
    cases.append(_subprocess_crash_test())
    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "subprocess_executed": True,
        "genuine_broker_deals": 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
