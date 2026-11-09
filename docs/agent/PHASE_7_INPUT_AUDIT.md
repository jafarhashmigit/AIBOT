# Phase 7 input audit

Recorded **before** Phase 7 scoring. Evaluation/integration only. Holdout not opened. Phase 1–6 research artifacts not modified.

## Git

- Branch: `cursor/phase7-oos-agent-evaluation` (from `cursor/phase6-agent-architecture`)
- Working tree at audit: untracked Phase 2–6 source/docs; no tracked Phase 1 files modified
- Nothing pushed

## Frozen hashes

| Artifact | SHA-256 |
|---|---|
| `src/data/phase2_oos_predictions.csv` | `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f` |
| `src/data/phase3_decision_journal.csv` | `b8cc1da7cc5918d9fd17131c67913aad183f58098b2671d04c7cc1b024d5324a` |
| `reports/phase5/replication_results.json` | `39b74769bc63de7ec5c6b74d356aaca66f5d108cff24d8918998607741d05785` |
| `src/data/xauusd_m5.csv` | `ac34d06fdede8a71bfcc2170badb7c04acfad83e5ecb79a928f85276ef5a4760` |

Phase 2 OOS integrity (row scan for counts and range only; no economic scoring):

- Rows: 36,468
- BUY 18,234 / SELL 18,234
- Folds: WF1 12,156 / WF2 12,156 / WF3 12,156
- Range: `2026-06-19 03:05:00` → `2026-09-29 17:50:00`
- Rows after cutoff `2026-09-29 18:50:00`: 0

## Holdout

`src/data/xauusd_m5_test.csv` exists and is not opened. Guard target: `test_open_attempts = 0`.

Maximum market timestamp accessed at audit: Phase 2 OOS `decision_time` max `2026-09-29 17:50:00` (inside the research window). No holdout file. No bars after cutoff.

## What this phase consumes

Existing genuinely OOS Phase 2 predictions, unchanged. Phase 6 interfaces (`Observation`, `Predictor`, `DecisionEngine`, `RiskGate`, `Journal`). Phase 3 baseline *definitions* (Always WAIT, E1, Direction, frozen conservative EV), not retuned.

## What this phase will not do

Retrain Phase 2, create features, revive NY-SELL, weaken the Phase 6 WAIT-only gate, tune thresholds on OOS, or open the holdout.
