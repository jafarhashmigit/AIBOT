# Experiment pre-registration template

Copy this file, fill every field **before** generating the first OOF prediction
or trade, and store the copy under `docs/agent/preregistrations/` (or attach it
to the model-registry record). Empty fields mean the experiment is not
registered. Do not edit thresholds after a result has been seen; start a new
registration instead.

Status: template only (Phase 1).

---

## 0. Header

- Experiment id:
- Date registered (UTC):
- Author:
- Family (e.g. `M5_meta_labeling`):
- Recipe hash (filled after the file is complete):
- Finding class this run is allowed to claim: exploratory / confirmatory
- Code commit / file hashes:

## 1. Question and hypothesis

- Question (one sentence):
- Hypothesis (directional, falsifiable):
- Null that permutation / bootstrap must beat:
- What would make us abandon this family:

## 2. Data (must stay inside the research cutoff until G4)

- Symbol / timeframe:
- Feature version / path:
- Label version / path:
- Training period:
- Walk-forward windows (list):
- Purge bars:
- Embargo bars:
- Holdout: **not used** (G4 requires a separate, later registration)
- Confirmation that `xauusd_m5_test.csv` will not be opened: yes / no

## 3. Model

- Role: primary / meta / other
- Estimator class:
- Hyperparameters (full dict, no “tune later”):
- Features (exact list):
- Forbidden inputs (outcomes, future timestamps, post-cutoff bars):
- Random seeds:
- Cost model (must match `label_m5` / `backtest_rf_m5` unless this registration
  explicitly replaces it, which Phase 1 does not):

## 4. Decision rule

- How BUY / SELL / WAIT is chosen:
- EV margin / probability thresholds (fixed now):
- Risk-gate rules:
- One-sided or two-sided (cannot change after seeing results):

## 5. Gates that will be run

Tick only gates that will actually execute. Unticked gates are `not_run` and
**cannot** be treated as passes.

- [ ] G0 integrity (required)
- [ ] G1 probabilistic skill
- [ ] G2 walk-forward economics
- [ ] G3 robustness
- [ ] G4 holdout (forbidden until a prior registration passed G0–G3)
- [ ] G5 forward paper signals

Record the threshold source: `docs/agent/ACCEPTANCE_CRITERIA.md` as of (date).
Do not copy weaker numbers here.

## 6. Multiple testing

- Family size (number of configurations registered together):
- FDR q:
- What is **not** a configuration (diagnostics that will not be selected on):

## 7. Permutation / bootstrap

- Bootstrap: day-cluster, 2000 draws, seed 42 (G2) unless registered otherwise
- Permutation A (label-block): draws, what is shuffled
- Permutation B (random-entry): draws, outcome pool
- Compute budget if a test will be skipped: skipping blocks a pass

## 8. Promotion rule

A pass of G2 does not auto-promote. Champion replacement follows
`ACCEPTANCE_CRITERIA.md` section 8. State the current champion id
(`no_model` if none).

## 9. Logging

- Decision journal schema version:
- Model registry id to be created:
- Machine-readable report path (gitignored `reports/` is fine):

## 10. Sign-off

- Registered by:
- Date:
- Explicit statement: no parameter, threshold, feature or model will be chosen
  using the final holdout or any bar after 2026-09-29 18:50 UTC.
