# Phase 12 architecture

Stage A (this implementation): offline shadow-observation system, synthetic fixtures only.

Stage B (not executed): manual read-only MT5 session, started and stopped by the user.

```text
Read-only completed M5 bar
  → validation (OHLC, completeness, duplicates, gaps)
  → FORWARD_SHADOW observation
  → champion check (no_model)
  → WAIT proposal
  → frozen WAIT-only RiskGate policy
  → shadow decision journal
  → outcome path after 12 later bars
```

`FORWARD_SHADOW` is not `AGENT_PAPER` and not `HISTORICAL_HYPOTHETICAL`.

No live trading. No broker orders. No Phase 9 learner. No combined experience learning.

## RiskGate compatibility

Phase 6 `RiskGate.evaluate()` refuses Observation timestamps after the research cutoff. Phase 12 does **not** modify that gate. Forward bars are after the cutoff, so shadow journaling uses the frozen gate **configuration** (`wait_only=True`, `champion_id=no_model`) rather than passing a post-cutoff Phase 6 Observation into `evaluate()`.
