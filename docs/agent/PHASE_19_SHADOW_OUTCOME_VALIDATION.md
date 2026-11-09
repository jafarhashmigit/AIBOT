# Phase 19 — Shadow Outcome Pipeline Validation

**Recipe:** `phase19_shadow_outcome_pipeline_validation_v1`  
**Branch:** `cursor/phase19-shadow-outcome-validation`

## Objective

Prove Phase 18 infrastructure correctly handles the experimental BUY/SELL shadow lifecycle **without** forcing live-market BUY/SELL and **without** modifying H13_C.

```text
Experimental BUY/SELL
→ Discord signal (synthetic-labeled / mock)
→ 5M / 10M / 15M / 30M / 60M outcomes
→ PASS / FAIL / TIMEOUT
→ AGENT_SHADOW experience (synthetic namespace)
→ daily reporting (synthetic-labeled)
```

This phase proves **infrastructure correctness only**. It does **not** claim a trading edge.

## Critical isolation

| Concern | Behavior |
|---------|----------|
| Namespace | `PHASE19_SYNTHETIC_TEST` under `src/data/phase19/` |
| Live MT5 | Never started |
| Production Phase 18 journal | Untouched |
| Production experience | Untouched |
| H13_C / Phase 16–18 code | Unmodified (hash-protected) |
| Champion | `NO_MODEL` |
| Production `final_action` | `WAIT` |

Synthetic events are never mistaken for real trading experience.

## Synthetic scenarios

Deterministic fixtures (programmatic M5 candles, no wall-clock wait):

| Scenario | Side | Expected H12 |
|----------|------|--------------|
| `BUY_PASS` | BUY | PASS (TP) |
| `BUY_FAIL` | BUY | FAIL (SL) |
| `SELL_PASS` | SELL | PASS (TP) |
| `SELL_FAIL` | SELL | FAIL (SL) |
| `TIMEOUT` | BUY | TIMEOUT (TIME) |

All five horizons (H1–H12) are evaluated independently by advancing synthetic candle boundaries.

Realized R is checked against `phase18.barrier.simulate_trade_horizon` (validated cost-aware methodology).

## Discord

Default path uses **MockDiscordClient** (no network).

Synthetic payloads always include:

```text
PHASE 19 SYNTHETIC TEST
NOT A REAL TRADING SIGNAL
```

Expected Horizon formatting is validated per label (`5M`…`60M`). Guarantee language is forbidden.

## Experience

Shadow experience is written only under the synthetic root via Phase 18 `ExperienceStore`, with source `AGENT_SHADOW` and synthetic meta markers.

Historical hypothetical remains in a separate file (`HISTORICAL_HYPOTHETICAL`).

## Commands

```text
# Ready only (default) — no MT5, no synthetic run
python src/phase19/run_phase19.py

# Explicit synthetic validation suite
python src/phase19/run_phase19.py --synthetic-test
```

## Package

```text
src/phase19/
docs/agent/PHASE_19_SHADOW_OUTCOME_VALIDATION.md
docs/agent/PHASE_19_RESULTS.md
reports/phase19/
src/data/phase19/PHASE19_SYNTHETIC_TEST/
```
