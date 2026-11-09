# Phase 3 feature leakage report

Machine-readable twin: `reports/phase3/feature_audit.json`. **Passed.**

## Allowlist (14 decision-time columns)

Primary-model outputs only, after pivoting BUY and SELL onto one timestamp:

- RF outcome probabilities: `p_tp_rf_*`, `p_sl_rf_*`, `p_time_rf_*`
- Predicted net R: `pred_r_rf_*`, `pred_r_ridge_*`
- Derived at the same timestamp: `pred_r_rf_diff`, `p_tp_rf_diff`, `p_tp_minus_sl_rf_*`

Market features are not re-joined. They already entered the Phase 2 primary models. Re-including them was not predeclared.

## Explicitly excluded

All `actual_*` fields, exit timestamps/prices, future high/low/returns, gross/net P&L, `net_r`, costs, fills, TP/SL prices, and any statistic computed from the outer evaluation outcomes.

## Checks (all passed)

1. Allowlist is explicit.
2. No outcome field is in the allowlist.
3. No `actual_` prefix in the allowlist.
4. All allowlist columns present on the timestamp frame.
5. No missing or infinite allowlist values.
6. No duplicate timestamps; BUY and SELL are paired.
7. Max decision time = 2026-09-29 17:50 ≤ validation end and cutoff.
8. Phase 2 OOS SHA-256 unchanged.
9. Phase 2 source/doc hashes unchanged.
10. Every row’s `decision_time` is strictly after that row’s primary `training_period_end` (genuine primary OOS).
11. Timestamps chronological and unique.
12. Holdout not opened. CSV reads: `phase2_oos_predictions.csv` only.

## Nested anti-leakage

Inner calibration may use inner actual outcomes as **labels** (to estimate class-conditional R, MAE, thresholds, meta-models). Those outcomes are never features. Outer timestamps are not used for fitting, threshold selection, calibration, or model choice.

A 12-bar purge keeps inner label windows from overlapping the outer period.
