# Phase 4 feature leakage report

Regime labels use **decision-time** information only.

## Allowed

- Corrected UTC hour, weekday, and session flags from `xauusd_m5_features_utc_corrected.csv`
- `atr_14_pct` and `ema_9_20_spread` from the closed decision bar
- ATR tercile **cuts** fit on inner timestamps only, then applied to outer

## Forbidden

- Actual `net_r` / `exit_reason` as features
- Exit prices, future high/low, future returns
- Outer outcomes when forming tercile cuts
- Holdout rows
- Any timestamp after `2026-09-29 18:50:00`

Scoring uses outer actual outcomes **after** the slice is defined. That is evaluation, not a feature.

## Join

OOS `decision_time` inner-joins feature `time`. 0 missing keys. Max stamp 2026-09-29 17:50. CSV reads: `phase2_oos_predictions.csv`, `xauusd_m5_features_utc_corrected.csv`. Holdout not opened.
