# Phase 16A — H13_C Prospective Shadow Integration

**Recipe:** `phase16a_h13c_shadow_pilot_v1`  
**Branch:** `cursor/phase16a-h13c-shadow-integration`

## Purpose

Integrate the Phase 14 retained-experimental H13_C rule with Phase 12/12C forward-shadow infrastructure for a controlled **read-only** MT5 observation pilot.

## Non-negotiables

- Production champion remains `NO_MODEL`
- H13_C remains `EXPERIMENTAL` / Phase 14 `RETAINED_EXPERIMENTAL`
- Phase 12C forward gate is **not** bypassed: experimental BUY/SELL → gated `final_action=WAIT`
- No parameter optimization, retraining, or threshold changes
- Frozen cuts: Phase 14 WF3 train q25/q75 values from `reports/phase14/replication.json`
- Only completed M5 candles (`bar_close < as_of`)
- Causal H1 context via Phase 14 `h1_trend_at`
- Never fabricate candles or paper fills / broker orders
- Dedicated storage: `src/data/phase16a/` (isolated from Phase 12 journals and experience stores)
- No merge into `HISTORICAL_HYPOTHETICAL` / `AGENT_PAPER` (source type is `FORWARD_SHADOW`)

## Architecture

1. **Preflight** (`preflight.py`) — fail-closed checks (hashes, allowlist, terminal, symbol probe, gate, lock, parity)
2. **MT5 reader** (`mt5_reader.py`) — allowlisted `copy_rates_*` only; lazy MetaTrader5 import
3. **Predictor** (`predictor.py`) — `decide_h13c` + `ForwardGateAdapter.apply`
4. **Session** (`session.py`) — explicit 1-hour RO pilot loop; manual start only via `--pilot`
5. **Outcomes** — Phase 12 `observe_outcome` with `outcome_end < as_of`; pending reported separately

## Frozen H13_C rule

- BUY: H1 up ∧ `close_to_ema_20 <= close_ema_low` ∧ `ema_9_20_spread > 0`
- SELL: H1 down ∧ `close_to_ema_20 >= close_ema_high` ∧ `ema_9_20_spread < 0`
- else WAIT

## Runner

```text
python src/phase16a/run_phase16a.py --preflight-only
python src/phase16a/run_phase16a.py --pilot
```
