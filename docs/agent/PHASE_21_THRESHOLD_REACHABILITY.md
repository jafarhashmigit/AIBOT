# Phase 21 — H13_C Threshold Reachability Research

**Recipe:** `phase21_h13c_threshold_reachability_v1`  
**Branch:** `cursor/phase21-threshold-reachability`  
**Mode:** Research only  

**Research only — no trading edge established.**

## Objective

Measure whether frozen Phase 14 WF3 H13_C thresholds are reachable historically, and how often full BUY/SELL rules fire — **without** changing thresholds, logic, or production WAIT.

## Scope & safety

| Constraint | Status |
|------------|--------|
| Frozen WF3 q25/q75 cuts | Unchanged |
| H13_C / Phase 12C / 16A–20 | Unchanged |
| Research cutoff | `2026-09-29 18:50 UTC` |
| Holdout / legacy test | Not accessed |
| Live Phase 16A/20 / 20A | Compared separately; not merged into historical |
| MT5 / Discord / orders / training / packages / push | None |

## Method

1. Load permitted Phase 14 historical bundle (`xauusd_m5_features_utc_corrected.csv`, H1, outcomes/OOS paths as used by Phase 14; features/H1 filtered to ≤ cutoff).  
2. For every feature timestamp with valid inputs, run **unchanged** `decide_h13c` against **exact** `FROZEN_CUTS`.  
3. Report distributions, partial conditions, full-rule matches, regimes, live comparison, and research-only percentile sensitivity.

## Frozen BUY / SELL rules

- **BUY:** `h1_trend==up` AND `close_to_ema_20 <= close_ema_low` AND `ema_9_20_spread > 0`  
- **SELL:** `h1_trend==down` AND `close_to_ema_20 >= close_ema_high` AND `ema_9_20_spread < 0`  

Frozen cuts: `close_ema_low ≈ -0.00100693`, `close_ema_high ≈ 0.00099892` (WF3 train q25/q75).

## Commands

```text
python src/phase21/run_phase21.py
python src/phase21/run_phase21.py --run-research
```

## Artifacts

```text
src/phase21/
docs/agent/PHASE_21_THRESHOLD_REACHABILITY.md
docs/agent/PHASE_21_RESULTS.md
reports/phase21/
```
