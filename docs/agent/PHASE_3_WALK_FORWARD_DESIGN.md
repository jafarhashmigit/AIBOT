# Phase 3 walk-forward design

Declared **before** outer evaluation. Nested chronological structure. No random splits. No holdout.

## Why nested

Phase 2 OOS predictions (WF1–WF3) are already out-of-sample for the **primary** models. They are in-sample for any decision rule that peeks at their actual `net_r` / `exit_reason` while choosing thresholds.

Therefore the decision layer is calibrated on **earlier** Phase 2 OOS folds and evaluated once on **later** Phase 2 OOS folds.

## Outer evaluation periods

The Phase 1/Phase 2 windows are reused. WF1 cannot be an outer evaluation fold: there is no earlier genuine OOS prediction set to fit the decision layer on. That limitation is not faked with a random split.

| Nested fold | Inner Phase 2 folds | Outer Phase 2 fold | Outer start (inclusive) | Outer stop | Inclusive stop |
|---|---|---|---|---|---|
| N1 | WF1 | WF2 | 2026-07-23 11:25:00 | 2026-08-26 13:55:00 | no (`< stop`) |
| N2 | WF1+WF2 | WF3 | 2026-08-26 13:55:00 | 2026-09-29 17:50:00 | yes |

## Purge / embargo

Same 12-bar purge as Phase 1/2: an inner row is kept only if

`decision_time + 12 * 5 minutes < outer_start`

Embargo = 0. BUY and SELL of the same timestamp stay together (the decision frame is one row per timestamp).

Runtime counts (recorded in `reports/phase3/walk_forward_design.json` before outer scoring):

| Nested fold | Inner timestamps | Inner end | Outer timestamps | Outer first | Outer last |
|---|---|---|---|---|---|
| N1 | 6,066 | 2026-07-23 10:20:00 | 6,078 | 2026-07-23 11:25:00 | 2026-08-26 13:50:00 |
| N2 | 12,144 | 2026-08-26 12:50:00 | 6,078 | 2026-08-26 13:55:00 | 2026-09-29 17:50:00 |

12 timestamps were purged at each inner/outer boundary (60 minutes of M5 bars). Combined outer evaluation: **12,156 timestamps** (WF2+WF3). WF1 is calibration-only.

## What is fit on inner only

- Class-conditional mean net R by `{TP, SL, TIME} × {BUY, SELL}`
- MAE of that EV mapping (uncertainty penalty)
- Thresholds for C, D, EV, conservative EV, and meta Ridge
- Logistic / Ridge meta-models and their scaler

## What is frozen before outer numbers are seen

- Candidate threshold grids (tiny, listed in `src/phase3/constants.py`)
- Selection rule: inner mean trade R > 0 and ≥ 50 trades, then the **highest** surviving threshold; else Always WAIT
- Uncertainty k = 1.0
- Conservative min-gap = 0.02
- Primary frozen policy id: `P3_CONSERVATIVE_EV`
- Meta Random Forest: **not used** (a priori)

Outer evaluation does not choose among policies. Always WAIT, Phase 2 E1, and primary-model direction are compared on the **same** outer timestamps (WF2+WF3 only).

## Rationale

Two outer folds is the maximum honest nested split this OOS file supports. Results are exploratory. A single profitable outer fold cannot establish an edge.
