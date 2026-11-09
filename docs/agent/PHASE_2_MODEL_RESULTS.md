# Phase 2 model results

Finding class: **exploratory**. Not confirmatory. Not a trading edge.

Holdout: not opened. Cutoff: `2026-09-29 18:50:00`. Seed: 42.

OOS file: `src/data/phase2_oos_predictions.csv`  
36,468 rows = 18,234 BUY + 18,234 SELL across WF1–WF3 (6,078 timestamps × 2 sides × 3 folds).  
Every row records `fold_id`, `training_period_end`, `primary_clf_model_id`, `primary_reg_model_id`, and `feature_version=m5_utc_corrected_allowlist_v1`. Actual `exit_reason` / `net_r` are evaluation-only columns.

Machine-readable: `reports/phase2/model_results.json`.

## 1. Models (new artifacts only)

Saved under `src/models/phase2/`. Phase 1 `rf_m5_baseline.pkl` was not loaded for training and was not overwritten.

Per side and fold: StandardScaler (linear models), Logistic Regression, RF classifier (200 trees, depth 8, leaf 50), Ridge, RF regressor. Plus train-only class prior and constant mean R (no files).

## 2. Classification (TP / SL / TIME)

Identical OOS timestamps for prior, logreg, and RF.

| Model | Balanced acc. | Macro F1 | Log loss | Multiclass Brier |
|---|---|---|---|---|
| Class prior | 0.333 | 0.245 | 1.521 | 0.545 |
| Logistic regression | 0.454 | 0.339 | 1.235 | 0.650 |
| Random forest | **0.465** | **0.368** | **1.180** | 0.629 |

RF balanced accuracy by fold: WF1 0.454, WF2 0.462, WF3 0.479. BUY 0.462 / SELL 0.467.

RF per-class (pooled): TP precision 0.368 recall 0.364; SL 0.616 / 0.367; TIME 0.176 / 0.663. The majority class is SL (~58%). The prior always predicts SL (balanced acc. = 1/3).

Logreg and RF beat the prior on balanced accuracy and log loss on every fold. That is **not** an economic edge.

Phase 1 RF baseline (different task: BUY/SELL/WAIT on labels, 1,518 validation trades, −0.0169R, PF 0.965) is a historical reference only. It is not comparable on these 36,468 side-outcome rows.

## 3. Regression (expected net R)

Mean actual OOS net R = **−0.057R** (already after approved costs).

| Model | MAE | RMSE | Mean predicted R | Corr(pred, actual) |
|---|---|---|---|---|
| Constant train mean | 1.111 | 1.165 | −0.048 | 0.032 |
| Ridge | 1.111 | 1.167 | −0.051 | 0.020 |
| Random forest | 1.109 | 1.167 | −0.052 | 0.031 |

Fold correlations for RF: WF1 0.046, WF2 0.017, WF3 0.031. MAE is essentially the constant baseline. Predicted R has almost no linear association with realized R.

## 4. Economic readout E1 (pre-declared)

Rule (frozen in `PHASE_2_WALK_FORWARD_DESIGN.md` before OOS numbers): take the side with larger predicted RF expected R if that value is > 0; else WAIT. One side per timestamp. Realized P&L is the stored side-outcome (costs included).

| | n | Mean R | PF | Net USD/oz | Max DD USD/oz |
|---|---|---|---|---|---|
| Pooled | 11,418 | **−0.021** | 0.956 | −1,436.64 | 1,642.45 |
| WF1 | 4,102 | −0.005 | 0.975 | −295.04 | — |
| WF2 | 3,938 | −0.034 | 0.931 | −755.21 | — |
| WF3 | 3,378 | −0.023 | 0.961 | −386.39 | — |
| BUY | 1,466 | −0.114 | 0.794 | −1,004.55 | — |
| SELL | 9,952 | −0.007 | 0.984 | −432.10 | — |

Win rate 40.6%. All three folds have negative mean R.

Day-clustered bootstrap of mean R (block = calendar day of `decision_time`, 2,000 resamples, seed 42, 73 days): mean −0.021, 95% CI **[−0.060, +0.017]**, P(mean ≤ 0) = 0.86. The CI includes 0 and does not clear a positive lower bound.

**Classification improved vs the class prior; E1 did not establish a trading edge after costs.**

## 5. How a future agent could consume these OOS rows (not implemented)

At decision time the agent may read only:

- `decision_time`, `side`, `fold_id`
- `p_tp_*`, `p_sl_*`, `p_time_*`
- `pred_r_*`
- `primary_*_model_id`, `training_period_end`, `feature_version`

It must not read `actual_exit_reason`, `actual_net_r`, or `actual_net_pnl` for inference, feature construction, calibration, or model selection. Those columns exist so a later evaluator can score the file after the 12-bar window is historically complete. WAIT remains a later decision-layer output, not a trained action in this file.
