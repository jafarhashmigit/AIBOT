# Phase 6 information boundary

Enforced in `src/phase6/information_boundary.py` and `Observation.from_mapping`.

## Time `t`

`t` is the close of a completed M5 bar, stored as naive Europe/Athens server face in the existing files, interpreted with the Phase 4 UTC correction when features are built. Phase 6 does not rebuild features.

## Allowed at t

- OHLCV and tick volume with bar time ≤ t
- Approved historical features computed only from data ≤ t
- Model parameters trained only on rows whose outcomes were known before the evaluation period (`training_end < eval start`, plus purge/embargo)
- Historical realized outcomes with `outcome_known_at` strictly before the current training cutoff
- Estimated transaction cost from the spread **at t** (and the frozen floor), not realized P&L

## Forbidden at t

- Future OHLC, volume, labels, realized R
- Future model performance, session outcome, volatility, news, candles
- Any key in `FORBIDDEN_DECISION_TIME_KEYS` or prefixed `future_`, `outcome_`, `realized_`, `actual_`

## Code contracts

- `Observation` construction runs `assert_decision_time_payload`
- `available_history_end` must equal the observation timestamp
- `Predictor.fit` may not receive observations after `training_end`
- `Predictor.predict` may not be called on a timestamp inside the training window (`ScriptedPredictor`)
- `DecisionEngine` and `RiskGate` accept `Observation`, not `Outcome`
- `Outcome` attach requires the 12-bar / 60-minute horizon to be complete
- Journal decision-time rows cannot contain `realized_R` / `exit_reason` / `evaluation_timestamp`
- Replay processes timestamps in increasing order; the builder’s prefix is `timestamp <= t`

## Cutoff

Nothing after `2026-09-29 18:50:00` is a legal `t` until a separate G4 registration. The holdout file is not opened.
