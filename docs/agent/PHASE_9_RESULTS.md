# Phase 9 results

Research only. Not production. Not live trading. Not an economic edge.

**Conclusion:** `EXPERIENCE LEARNING DID NOT IMPROVE OOS DECISION QUALITY`

## Configuration (frozen before scoring)

- Recipe: `phase9_experience_ridge_v1`
- Policy: `P9_EXPERIENCE_RIDGE`
- Ridge alpha: `1.0`
- Min experiences per side: `100`
- Allowlist: `p_tp_rf_BUY, p_sl_rf_BUY, p_time_rf_BUY, p_tp_rf_SELL, p_sl_rf_SELL, p_time_rf_SELL, pred_r_rf_BUY, pred_r_rf_SELL, pred_r_ridge_BUY, pred_r_ridge_SELL, pred_r_rf_diff, p_tp_rf_diff`
- RiskGate: wait_only / champion `no_model` (unchanged)

## Replay

- Decisions: 18234
- Completed experiences used for training: 18221
- Skipped / pending: 13
- Cold-start fallbacks: 112
- Learner-available decisions: 18122
- Max timestamp accessed: `2026-09-29 17:50:00`
- Holdout opens: 0

## BUY / SELL / WAIT (final, after RiskGate)

- BUY 0 / SELL 0 / WAIT 18234

## BUY / SELL / WAIT (raw, pre-gate, diagnostic only)

- BUY 1406 / SELL 8974 / WAIT 7854

## Primary comparison (final decisions)

- Mean difference in R (Phase 9 − frozen Phase 6): 0.0
- 95% CI: [0.0, 0.0]
- Bootstrap P(diff <= 0): 1.0
- Draws: 2000, seed 42, day-cluster

Label: DESCRIPTIVE — NOT USED FOR OPTIMIZATION

## Reproducibility

- Two learner replays identical: `True`

## Tests

- 16/16 passed

## Integrity

- Protected artifacts unchanged: `True`
- Temporal leakage violations: 0

Pushed to GitHub: no
