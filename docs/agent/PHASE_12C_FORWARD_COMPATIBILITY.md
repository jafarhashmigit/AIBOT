# Phase 12C — Forward evaluation compatibility

**Conclusion: `PHASE 12C COMPLETE — FORWARD COMPATIBILITY ESTABLISHED`**

Qualification: this establishes **RiskGate / `apply_gate()` parity** and a fail-closed forward path. It does **not** establish full Phase 6 `evaluate()` parity on post-cutoff Observations.

## Concepts (kept separate)

| Label | Result | Meaning |
|---|---|---|
| A. Full Phase 6 `evaluate()` parity | **INCOMPLETE / NOT PROVEN** | Original `RiskGate.evaluate()` cannot process forward Observations without modifying Phase 6. |
| B. RiskGate and `apply_gate()` parity | **PASS** | Pre-cutoff `evaluate()`+`apply_gate` matches Phase 12C adapter for WAIT/BUY/SELL; all finals WAIT. |
| C. Forward observation compatibility | **PASS** | Synthetic post-cutoff `ForwardObservation` objects are processed by the Phase 12C adapter without calling `evaluate()`. |

Do not treat B as proof of A.

## Cutoff blockers (unchanged Phase 6)

1. `assert_before_cutoff` — timestamp after `2026-09-29 18:50:00`.
2. `Observation.__post_init__` — calls `assert_before_cutoff`.
3. `assert_decision_time_payload(..., as_of=...)` — rejects `as_of` after cutoff.
4. `DecisionEngine.decide` — supplies observation timestamp as `as_of`.
5. `RiskGate.evaluate` — refuses post-cutoff Observation timestamps.

Reusable without modifying Phase 6:

- `RiskGate()` frozen defaults (`wait_only=True`, `champion_id=no_model`)
- `GateResult`
- `apply_gate(raw_decision, gate_result)`

## Adapter

Path: `src/phase12c/`  
Version: `phase12c_forward_gate_adapter_v1`

| Reused from Phase 6 | Independently implemented in 12C |
|---|---|
| `RiskGate.__init__` config | `ForwardObservation` (not Phase 6 Observation) |
| `GateResult` | wait_only / no_model branch selection for forward timestamps |
| `apply_gate` | fail-closed proposal validation (missing/invalid prediction, uncertainty, model id, features) |

Not called: `RiskGate.evaluate`, `DecisionEngine.decide`, Phase 6 `Observation` construction for forward bars.

Research cutoff remains intact. RiskGate restrictions are not weakened. ALLOW cannot create BUY/SELL from WAIT. With champion `no_model`, forced BUY/SELL raw actions are BLOCK → WAIT.

## Pipeline I/O

**Inputs (forward path):** completed synthetic/forward bar fields, optional prediction/uncertainty/model id, frozen champion status.

**Outputs:** `raw_action`, `risk_gate_result`, `final_action`, `decision_reason`, `evaluate_called=false`, `apply_gate_reused=true`, `full_evaluate_parity=NOT_PROVEN`.

## Safety

- No approved model → WAIT / `NO_APPROVED_MODEL`
- Invalid / missing prediction → WAIT
- Unknown model id → WAIT
- Unavailable uncertainty → WAIT
- Missing required feature → WAIT
- Incomplete / invalid OHLC → reject
- Duplicate observation id → detectable for journal skip
- No MT5, no broker orders, no Stage B, no holdout

## Branch

`cursor/phase12c-forward-compatibility`

## Not authorized

Stage B observation, live BUY/SELL, broker execution, production promotion, Phase 13.
