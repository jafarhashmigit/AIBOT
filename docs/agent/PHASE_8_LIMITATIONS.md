# Phase 8 limitations

- The WAIT-only gate is unchanged, so final trades remain zero. That is expected, not a failure of memory.
- WAIT experiences have no selected realized R; mean selected R is empty. Hypothetical side R is stored as outcome-only fields and is not a signal.
- The last 60 minutes of OOS decisions cannot enter the store during replay (horizon still open relative to later T). They are recorded as skips.
- Experience is not used to change BUY/SELL/WAIT.
- No claim of economic edge, production readiness, or live readiness.
- Phase 7 journals are required on disk; Phase 8 does not regenerate labels.
- Holdout remains unused.
