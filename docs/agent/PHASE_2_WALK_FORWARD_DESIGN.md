# Phase 2 walk-forward design

Declared **before** fitting. Windows are the existing Phase 1 M5 fractions (0.55 / 0.70 / 0.85 of research-period **feature** timestamps through validation end). They are not retuned.

Index series: UTC-corrected feature `time` with `time <= 2026-09-29 17:50:00` (42,438 bars). Using eligible-only timestamps would shift the cuts; that is not done.

## Folds

Expanding train, blocked evaluation, **12-bar purge**, embargo = 0.

A training row is kept only if `decision_time + 12 * 5 minutes < eval_start`, so the triple-barrier window cannot overlap the evaluation block.

BUY and SELL for the same `decision_time` always share a fold. A timestamp is never split across train and eval.

| Fold | Eval start (inclusive) | Eval stop | Inclusive stop | Train timestamps | Eval timestamps | Last train decision | Purge |
|---|---|---|---|---|---|---|---|
| WF1 | 2026-06-19 03:05:00 | 2026-07-23 11:25:00 | no (`< stop`) | 22,272 | 6,078 | 2026-06-19 02:00:00 | 12 bars (01:05 gap to eval start) |
| WF2 | 2026-07-23 11:25:00 | 2026-08-26 13:55:00 | no | 28,350 | 6,078 | 2026-07-23 10:20:00 | 12 bars |
| WF3 | 2026-08-26 13:55:00 | 2026-09-29 17:50:00 | **yes** | 34,428 | 6,078 | 2026-08-26 12:50:00 | 12 bars |

Each timestamp contributes two rows (BUY and SELL), so train/eval row counts are twice the timestamp counts.

Preprocessing (StandardScaler for linear models) is fit on that fold’s training side only. Feature selection is the frozen allowlist; nothing is selected on evaluation data.

No random split. No holdout. No bars after the cutoff.

## Pre-declared economic readout (not a live policy)

**E1** (`E1_max_predicted_r_positive`), frozen here before OOS metrics:

> At each evaluation timestamp, take the side with the larger **predicted expected net R** (primary: RF regressor) if that value is strictly greater than 0; otherwise WAIT. At most one side per timestamp. Realized P&L is the stored side-outcome `net_pnl` / `net_r` (costs already applied).

E1 is not optimized on OOS outcomes. Classification probabilities are stored for later research; they are not used to pick sides in E1.

## Estimators (frozen)

| ID | Task | Notes |
|---|---|---|
| `prior` | classification | Training class frequencies |
| `logreg` | classification | `LogisticRegression`, scaled, `C=1`, `class_weight=balanced`, seed 42 |
| `rfclf` | classification | sklearn RF, 200 trees, depth 8, leaf 50, `max_samples=0.5`, seed 42 |
| `const` | regression | Training mean `net_r` |
| `ridge` | regression | `Ridge(alpha=1)`, scaled |
| `rfreg` | regression | sklearn RF regressor, same size as `rfclf` |

BUY and SELL are separate models. The Phase 1 `rf_m5_baseline.pkl` is not retrained or overwritten.
