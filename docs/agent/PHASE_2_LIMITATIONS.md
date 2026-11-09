# Phase 2 limitations

Finding class: exploratory. Status of all Phase 2 models: **experimental**. None are production-ready or live-ready.

## Safety (verified)

- Holdout `xauusd_m5_test.csv` was not opened.
- Modeling table max `decision_time` = 2026-09-29 17:50 (val_end). Cutoff 18:50 not exceeded.
- No extra market data downloaded. No packages installed or upgraded.
- Phase 1 datasets, labels, `rf_m5_baseline.pkl`, and research CSVs were not overwritten.
- No MT5 orders, no live signals, no decision engine.

## Incomplete tests (do not treat as passes)

- **Phase 1 permutation A** (200 RF retrains, day-block label shuffle) remains **`not_run`**. Phase 2 did not complete it and does not claim it passed.
- No CalibratedClassifierCV / isotonic fit was trained (would need nested training-only calibration). OOS Brier and per-class recalls are reported instead.
- No G2 promotion gate was applied to E1; E1 is a frozen readout and already has negative mean R in every fold.

## Statistical

- Adjacent M5 labels overlap (12-bar horizon). Purge handles the train/eval boundary; training rows still overlap each other.
- Uncertainty for E1 uses a **day-clustered** bootstrap (not iid trades), seed 42, 2,000 draws, 73 days. The 95% CI of mean R includes zero.
- 11,418 E1 selections is a large count but a **weak signal** (corr ≈ 0.03, MAE ≈ constant baseline). Sample size is not evidence of an edge.

## Modeling

- Only three frozen sklearn estimators plus two naive baselines. No hyperparameter search, by design.
- Original (wrong) UTC session features were excluded; corrected UTC columns were used. That is a feature-definition change vs Phase 1 RF inputs, so Phase 1 RF accuracy is not a same-sample comparator.
- Ineligible gap/incomplete windows are not modeled (3,840 rows). The 58 gap-crossing **backtest** trades remain outside this table.
- E1 selected SELL far more often than BUY (9,952 vs 1,466). That concentration is reported, not tuned away.
- Predicted net R is slightly negative on average, matching a losing label; the model does not isolate a positive conditional mean that survives costs.

## What was not built (on purpose)

- WAIT as a trained action
- Meta-model
- Expected-value decision engine
- Risk gate
- Live or paper signal generation

Those are later phases, only after explicit approval.
