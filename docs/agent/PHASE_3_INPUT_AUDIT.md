# Phase 3 input audit

Status: completed before decision-layer fitting. Research only. Holdout not opened.

## 1. Git / safety

- Branch: `cursor/phase3-decision-layer` (created from `cursor/phase2-primary-outcome-modeling`).
- Working tree at start: untracked Phase 2 source/docs only. No Phase 1 modifications.
- Research cutoff: `2026-09-29 18:50:00` (server clock).
- Last usable decision timestamp: `2026-09-29 17:50:00`.
- `xauusd_m5_test.csv` was not opened.
- Nothing pushed.

## 2. Primary input (not modified)

| File | Role | Rows | Range |
|---|---|---|---|
| `src/data/phase2_oos_predictions.csv` | Genuine Phase 2 OOS primary-model predictions | 36,468 | 2026-06-19 03:05 → 2026-09-29 17:50 |

SHA-256 at Phase 3 start: `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f` (14,897,224 bytes). Phase 3 refuses to run if this hash changes.

### Counts

- BUY: 18,234
- SELL: 18,234
- Timestamps: 18,234 (one BUY and one SELL each)
- Folds: WF1 12,156 rows / WF2 12,156 / WF3 12,156 (6,078 timestamps × 2 sides each)

### Prediction fields (decision-time)

`decision_time`, `side`, `fold_id`, `training_period_end`, `prediction_generated_at_utc`, `p_tp_prior/logreg/rf`, `p_sl_*`, `p_time_*`, `pred_r_const/ridge/rf`, `primary_clf_model_id`, `primary_reg_model_id`, `feature_version`

### Actual outcome fields (evaluation only; forbidden as decision features)

`actual_exit_reason`, `actual_net_r`, `actual_net_pnl`

### Model IDs

Per side × fold: `rfclf_{side}_{WFk}`, `rfreg_{side}_{WFk}` (primary). Also stored but not used as the decision source: logreg, ridge, class prior, constant mean R.

`training_period_end` is strictly before `decision_time` on every row (Phase 2 expanding walk-forward with 12-bar purge). Predictions are genuine OOS relative to the primary models that produced them.

## 3. Supporting documents (read, not modified)

- `docs/agent/PHASE_2_MODEL_RESULTS.md`
- `docs/agent/PHASE_2_WALK_FORWARD_DESIGN.md`
- `docs/agent/PHASE_2_LIMITATIONS.md`
- `docs/agent/PHASE_2_FEATURE_LEAKAGE_REPORT.md`
- `reports/phase2/model_registry.json` (gitignored research output)
- `src/evaluation/` shared metrics, day-cluster bootstrap, integrity guards

Phase 2 source hashes were snapshotted in `src/phase3/constants.py`. The audit fails if those files change.

## 4. Whether predictions are genuinely OOS

Yes, for the **primary** models: each Phase 2 fold trains only on earlier timestamps, with a 12-bar purge.

They are **not** OOS for a decision layer trained on the same rows’ actual outcomes. That is why Phase 3 uses a nested split: earlier Phase 2 OOS folds calibrate the decision layer; later Phase 2 OOS folds are the outer evaluation and are never used to choose thresholds.

## 5. Limitations inherited from Phase 2

- Primary expected-R correlation vs actual R is ~0.03. Classification beats a class prior; E1 mean R is negative in every Phase 2 fold.
- Predicted R is slightly negative on average.
- E1 selected SELL far more often than BUY.
- Adjacent 12-bar labels overlap; day-cluster bootstrap is required.
- Ineligible gap/incomplete windows are absent from this file.
- Phase 1 permutation A remains `not_run`.
- No live policy was produced in Phase 2.

## 6. What this phase does not read

- `src/data/xauusd_m5_test.csv` (holdout)
- Any price bar after `2026-09-29 18:50:00`
- New market downloads

Market features are not re-joined. They already entered the primary predictions. Re-including them is not predeclared.
