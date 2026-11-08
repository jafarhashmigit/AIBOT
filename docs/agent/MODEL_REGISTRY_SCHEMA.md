# Model registry schema

Status: documentation only (Phase 1). No model is promoted by this document.

The registry is the only path from a trained artefact to a journaled decision.
`rf_m5_baseline.pkl` is the **reference baseline**, not a champion. While no
model has passed G4/G5, the champion is `"no model"` (WAIT-only).

## 1. Identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `model_id` | string | yes | Immutable. Suggested: `{family}_{label_version}_{utc_stamp}` |
| `role` | string | yes | `primary` / `meta` / `baseline` / `champion` / `challenger` |
| `artefact_path` | string | yes | Path relative to the repo; artefact itself is gitignored |
| `artefact_sha256` | string | yes | Hash of the serialised model file |
| `code_commit` | string | no | Git commit if identity is configured |
| `recipe_hash` | string | yes | Hash of the pre-registration record |
| `previous_champion` | string | no | `model_id` replaced, or `no_model` |
| `promotion_reason` | string | no | Empty until a promotion decision exists |
| `approval_status` | string | yes | `registered` / `rejected` / `champion` / `retired` |
| `registry_schema_version` | string | yes | Currently `1.0` |

## 2. Training recipe (frozen before the first OOF block)

| Field | Type | Notes |
|---|---|---|
| `training_period_start` | datetime | Inclusive, server clock as stored |
| `training_period_end` | datetime | Last training label whose window ends before the first OOF bar |
| `training_data_hash` | string | Prefix hash of the training rows actually used |
| `feature_version` | string | Matches the journal `feature_version` |
| `label_version` | string | e.g. `m5_tb_1.5_1.0_h12_v1` |
| `purge_bars` | int | 12 for M5 |
| `embargo_bars` | int | 0 unless a later experiment registers more |
| `hyperparameters` | object | Exact estimator kwargs |
| `random_seed` | int | |
| `cost_model` | object | Spread floor, $/side, TP/SL, horizon — copied, not changed |
| `split_definition` | object | Walk-forward windows or train/validation cut |

## 3. Evaluation results (machine-readable)

| Field | Type | Notes |
|---|---|---|
| `validation_results` | object | In-sample-relative validation metrics; never sufficient to promote |
| `walk_forward_results` | object | Per-block and pooled metrics from `evaluation.gates` |
| `acceptance_gate_results` | object | G0–G3 as executed; missing tests are `not_run`, not passes |
| `g2_passed` | bool | Must be false for `rf_m5_baseline` |
| `finding_class` | string | `exploratory` / `confirmatory` / `reproduction` |
| `holdout_status` | object | Test-open attempts must be 0 before G4 |

A model whose G2 record is missing or `not_run` on a required criterion
cannot have `approval_status=champion`.

## 4. Promotion

Promotion requires the champion/challenger rule in `ACCEPTANCE_CRITERIA.md`
section 8. The registry stores the decision; it does not compute a looser
rule. Classification accuracy, even if above a majority-class baseline, is
not a promotion input.
