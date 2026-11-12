# Phase 56 — Autonomous Observer & Lifecycle Integration

**Recipe:** `phase56_autonomous_observer_lifecycle_integration_v1`  
**Verdict:** `AUTONOMOUS_REPLAY_AGENT_READY`  
**Champion:** `NO_MODEL` | **Production:** `WAIT`

SL/TP integrated into lifecycle; bounded historical replay, recovery, and regressions passed.

Phase54 source unmodified. `IntegratedLifecycleEngine` subclasses LifecycleEngine and wires `monitor_and_maybe_exit`.

## Commands

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m unittest phase56.tests.test_phase56 phase55.tests.test_phase55 phase54.tests.test_phase54 -v
.\.venv\Scripts\python.exe -m phase56.run_phase56
.\.venv\Scripts\python.exe -m phase56.cli --max-candles 20
```

See `reports/phase56/FINAL_REPORT.md`.
