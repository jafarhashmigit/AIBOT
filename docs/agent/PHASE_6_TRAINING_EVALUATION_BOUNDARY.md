# Phase 6 training / evaluation boundary

```text
TRAIN
VALIDATE
TEST / OOS
HOLDOUT
```

## Roles

| Split | Use | Forbidden use |
|---|---|---|
| TRAIN | Fit primary/meta parameters; estimate EV constants, uncertainty penalties, cost buffers | Watching OOS or holdout results |
| VALIDATE / inner | Calibration, frozen threshold *selection if a later experiment registers it* | Reusing a consumed block for a modified recipe |
| TEST / OOS | Walk-forward economics (G1–G3) | Training, threshold tuning, feature selection, model selection |
| HOLDOUT | Single G4 use after G0–G3 pass, separately registered | Any Phase 6 access |

## Hard rules

The architecture must never allow:

- test outcome → model training
- test outcome → threshold tuning
- test outcome → feature selection
- test outcome → model selection

The final holdout (`xauusd_m5_test.csv` and every bar after `2026-09-29 18:50:00`) remains permanently untouched in Phase 6.

A recipe change after an evaluation block is generated is a **new** challenger and needs a **new** untouched block (`LEARNING_METHODOLOGY.md` section 8).

## Phase 6 execution

Phase 6 runs unit tests and schema checks on synthetic timestamps only. It does not consume a new OOS market block and does not train.
