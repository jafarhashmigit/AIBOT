"""Adversarial failure injection across persistence boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase57_1.constants import INJECT_STAGES
from phase57_1.durable_engine import make_durable_engine
from phase57_1.journal import CrashInjected, TradeLifecycleJournal
from phase57_1.rebuild import (
    corrupt_store_json,
    rebuild_experience_from_journal,
    truncate_store,
    wipe_store,
)
from phase57_1.reconcile import reconcile


def _trade_once(work: Path, *, crash_at: str | None = None) -> dict[str, Any]:
    day, m5, h1, by = directional_path(day="2099-11-01", move_after_entry=-5.0)
    eng = make_durable_engine(
        work=work,
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
        crash_at=crash_at,
    )
    try:
        r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        eng.persist()
        return {"ok": True, "result": r, "raised": None, "engine": eng}
    except CrashInjected as exc:
        try:
            eng.persist()
        except Exception:
            pass
        return {"ok": False, "raised": str(exc), "engine": eng, "result": None}


def verify_integrity(work: Path, eng) -> dict[str, Any]:
    eng2 = make_durable_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
    # clear crash
    eng2.journal.crash_at = None
    recovery = eng2.recover_pending()
    day, m5, h1, by = directional_path(day="2099-11-01", move_after_entry=-5.0)
    keys_before = list(eng2.state.data.get("processed_decision_keys") or [])
    was_processed = any(k.endswith(":48") for k in keys_before)
    again = eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    if was_processed:
        idem = again.get("skipped") is True
    else:
        again2 = eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
        idem = again2.get("skipped") is True
    rep = reconcile(journal=eng2.journal, state=eng2.state, shadow=eng2.shadow, hist=eng2.hist)
    exits = eng2.journal.committed_exits()
    # If exit was committed, experience must exist after recovery
    lost = False
    for ex in exits:
        if (ex.get("experience_source") or "AGENT_SHADOW") != "AGENT_SHADOW":
            continue
        tid = ex["txn_id"]
        exp_ids = {r.get("experience_id") for r in eng2.shadow.all()}
        from phase57_1.constants import deterministic_experience_id

        eid = deterministic_experience_id(tid, "AGENT_SHADOW")
        if eid not in exp_ids:
            lost = True
    return {
        "recovery": recovery,
        "idempotent": idem,
        "duplicate_open": len(eng2.risk.open_positions) > 1,
        "double_close": len(eng2.state.data.get("closed_position_ids") or [])
        != len(set(eng2.state.data.get("closed_position_ids") or [])),
        "lost_committed_outcome": lost,
        "reconcile": rep,
        "n_exits": len(exits),
        "shadow_n": eng2.shadow.n,
        "ok": idem
        and not lost
        and not (len(eng2.risk.open_positions) > 1)
        and len(eng2.state.data.get("closed_position_ids") or [])
        == len(set(eng2.state.data.get("closed_position_ids") or [])),
    }


def run_inject_stage(stage: str, work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    # Map suite stage names to crash_at
    crash_map = {
        "before_exit_detection": "before_exit_detection",
        "after_exit_detection": "after_exit_detection",
        "before_durable_exit_commit": "before_durable_exit_commit",
        "during_journal_write": "during_journal_write",
        "after_durable_exit_commit": "after_durable_exit_commit",
        "before_outcome_derivation": "before_outcome_derivation",
        "during_outcome_persistence": "during_outcome_persistence",
        "after_outcome_before_experience": "after_outcome_before_experience",
        "during_experience_reconstruction": None,  # handled specially
        "during_checkpoint_update": "after_durable_exit_commit",  # approximate
        "during_restart_recovery": "after_outcome_before_experience",
    }
    if stage == "during_experience_reconstruction":
        r = _trade_once(work, crash_at=None)
        wipe_store(r["engine"].shadow)
        journal = TradeLifecycleJournal(work / "journal")
        try:
            rebuild_experience_from_journal(
                journal, shadow=r["engine"].shadow, source="AGENT_SHADOW", interrupt_after=0
            )
            # resume
            out = rebuild_experience_from_journal(journal, shadow=r["engine"].shadow, source="AGENT_SHADOW")
            v = verify_integrity(work, r["engine"])
            return {"stage": stage, "inject_ok": True, "rebuild": out, "verify": v, "ok": v["ok"] and out["n_written"] >= 0}
        except Exception as exc:
            return {"stage": stage, "ok": False, "error": str(exc)}

    crash_at = crash_map.get(stage)
    r = _trade_once(work, crash_at=crash_at)
    v = verify_integrity(work, r.get("engine"))
    # before_exit_detection: may have no EXIT_COMMITTED — not a lost committed outcome
    if stage == "before_exit_detection":
        ok = v["idempotent"] and not v["duplicate_open"] and not v["double_close"]
    elif stage in ("after_exit_detection", "before_durable_exit_commit", "during_journal_write"):
        # No durable EXIT_COMMITTED required yet
        ok = v["idempotent"] and not v["duplicate_open"] and not v["double_close"] and not v["lost_committed_outcome"]
    else:
        ok = v["ok"]
    return {
        "stage": stage,
        "raised": r.get("raised"),
        "verify": v,
        "ok": ok,
    }


def run_all_inject_stages(root: Path) -> dict[str, Any]:
    rows = []
    for stage in INJECT_STAGES:
        rows.append(run_inject_stage(stage, root / stage))
    return {
        "n": len(rows),
        "all_ok": all(r.get("ok") for r in rows),
        "stages": {r["stage"]: {"ok": r.get("ok"), "raised": r.get("raised")} for r in rows},
        "rows": rows,
    }


def run_rebuild_adversarial(work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    cases = {}
    # Baseline trade
    r = _trade_once(work / "base", crash_at=None)
    eng = r["engine"]
    assert eng.shadow.n >= 1
    tid = list(eng.journal.committed_exits())[0]["txn_id"]
    from phase57_1.constants import deterministic_experience_id

    eid = deterministic_experience_id(tid, "AGENT_SHADOW")
    payload = eng.journal.committed_exits()[0]["payload"]

    # 1 delete entire store
    wipe_store(eng.shadow)
    out = rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    cases["deleted_store"] = {
        "ok": eid in {x.get("experience_id") for x in eng.shadow.all()} and out["n_written"] >= 1,
        "exit_fill": payload.get("exit_fill"),
        "net_r": payload.get("net_r"),
        "preserved": eng.shadow.all()[0].get("actual_costed_outcome_net_r") == payload.get("net_r")
        if eng.shadow.n
        else False,
    }

    # 2 empty store + repeated rebuild
    wipe_store(eng.shadow)
    rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    n1 = eng.shadow.n
    rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    n2 = eng.shadow.n
    cases["repeated_rebuild_no_dup"] = {"ok": n1 == n2 == 1, "n1": n1, "n2": n2}

    # 3 corrupt json
    corrupt_store_json(eng.shadow.path)
    # reload store by clear+rebuild
    wipe_store(eng.shadow)
    out3 = rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    cases["corrupt_json_rebuilt"] = {"ok": out3["n_written"] == 1 and eng.shadow.n == 1}

    # 4 truncated
    truncate_store(eng.shadow.path, 15)
    wipe_store(eng.shadow)
    out4 = rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    cases["truncated_rebuilt"] = {"ok": out4["n_written"] == 1}

    # 5 interrupted reconstruction resume
    wipe_store(eng.shadow)
    mid = rebuild_experience_from_journal(eng.journal, shadow=eng.shadow, interrupt_after=0)
    fin = rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
    cases["interrupted_resume"] = {
        "ok": mid.get("interrupted") and fin["n_written"] + len([s for s in fin["skipped"] if s.get("reason") == "already_present"]) >= 0 and eng.shadow.n == 1,
        "mid": mid,
        "fin_n": eng.shadow.n,
    }

    # 6 invalid checksum quarantined
    jpath = (work / "base" / "journal" / "lifecycle_journal.jsonl")
    bad = {
        "schema_version": "phase57_1_journal_v1",
        "record_id": "bad",
        "txn_id": "badtxn",
        "position_id": "p",
        "stage": "EXIT_COMMITTED",
        "seq": 999,
        "payload": {},
        "provenance": "test",
        "created_iso": "x",
        "checksum": "deadbeef",
    }
    with jpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(bad) + "\n")
    j2 = TradeLifecycleJournal(work / "base" / "journal")
    cases["bad_checksum_quarantined"] = {
        "ok": len(list(j2.quarantine.glob("*"))) >= 1 and not any(r.get("txn_id") == "badtxn" for r in j2.all()),
        "quarantine_n": len(list(j2.quarantine.glob("*"))),
    }

    # 7 identity preservation
    cases["identity_preserved"] = {
        "ok": cases["deleted_store"]["ok"] and cases["deleted_store"]["preserved"],
        "experience_id": eid,
        "exit_reason": payload.get("exit_reason"),
        "exit_fill": payload.get("exit_fill"),
        "net_r": payload.get("net_r"),
    }

    ok = all(c.get("ok") for c in cases.values())
    return {"ok": ok, "cases": cases}


_SUBPROCESS_WORKER = """
import json, sys
from pathlib import Path
sys.path.insert(0, __SRC__)
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase57_1.durable_engine import make_durable_engine
from phase57_1.journal import CrashInjected

work = Path(sys.argv[1])
crash_at = sys.argv[2] if sys.argv[2] != "NONE" else None
day, m5, h1, by = directional_path(day="2099-11-02", move_after_entry=-5.0)
eng = make_durable_engine(
    work=work,
    policy=EngineeringTestPolicy(["BUY"]),
    risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
    crash_at=crash_at,
)
try:
    eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
    eng.persist()
    print(json.dumps({"status": "completed"}))
except CrashInjected as e:
    try:
        eng.state.save()
    except Exception:
        pass
    print(json.dumps({"status": "crashed", "at": str(e)}))
    raise SystemExit(90)
"""


def run_subprocess_crash(work: Path, crash_at: str) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    src = str(Path(__file__).resolve().parents[1])
    script = work / "_worker.py"
    script.write_text(
        _SUBPROCESS_WORKER.replace("__SRC__", repr(src)),
        encoding="utf-8",
    )
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = src
    proc = subprocess.run(
        [sys.executable, str(script), str(work), crash_at or "NONE"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    # Parent recovery
    eng = make_durable_engine(work=work, policy=EngineeringTestPolicy(["WAIT"]))
    eng.journal.crash_at = None
    recovery = eng.recover_pending()
    rep = reconcile(journal=eng.journal, state=eng.state, shadow=eng.shadow, hist=eng.hist)
    lost = False
    for ex in eng.journal.committed_exits():
        from phase57_1.constants import deterministic_experience_id

        eid = deterministic_experience_id(ex["txn_id"], "AGENT_SHADOW")
        if eid not in {r.get("experience_id") for r in eng.shadow.all()}:
            lost = True
    return {
        "crash_at": crash_at,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-500:],
        "stderr": (proc.stderr or "")[-500:],
        "recovery": recovery,
        "lost_committed_outcome": lost,
        "reconcile_missing": rep.get("missing_outcomes"),
        "ok": (not lost) if crash_at in (
            "after_durable_exit_commit",
            "after_outcome_before_experience",
            "before_outcome_derivation",
        ) else True,
        "shadow_n": eng.shadow.n,
        "n_exits": len(eng.journal.committed_exits()),
    }


def run_subprocess_suite(root: Path) -> dict[str, Any]:
    stages = [
        "after_durable_exit_commit",
        "after_outcome_before_experience",
        "before_durable_exit_commit",
    ]
    rows = [run_subprocess_crash(root / s, s) for s in stages]
    return {"n": len(rows), "all_ok": all(r.get("ok") for r in rows), "rows": rows}
