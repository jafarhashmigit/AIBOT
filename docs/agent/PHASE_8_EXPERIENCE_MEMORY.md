# Phase 8 experience memory

Research-only. Not a trading strategy. Champion remains `no_model`. RiskGate remains WAIT-only.

```text
Observation → Predictor → Uncertainty → DecisionEngine → RiskGate
        → Journal → later Outcome → ExperienceStore.query(T)
```

An experience has two layers:

- `decision_time_fields` — timestamp, action, frozen predictions, uncertainty
- `outcome_fields` — attached only after the 12-bar / 60-minute horizon

`Observation` never contains outcome fields. `ExperienceStore.query(T)` returns only records with `outcome_end < T`.

Descriptive summaries (n, BUY/SELL/WAIT counts, mean selected R) are **not** trading rules and are **not** fed into the DecisionEngine.

No new model is trained.

## Replay result (descriptive)

- Decisions: 18,234; final BUY/SELL/WAIT = 0 / 0 / 18,234
- Completed experiences: 18,221 WAIT (selected R empty)
- Skipped: 13, reason `horizon_not_completed_before_next_oos_bar` (last hour of OOS; `outcome_end` not strictly before a later T)
- Ablation A vs B: identical WAIT decisions; only B’s `experience_n` grows (0 → 18,221)
- Leakage violations: 0
- Determinism: passed

## Conclusion

**EXPERIENCE MEMORY VALIDATED**

Not an economic edge. Not production-ready. See `reports/phase8/phase8_conclusion.json`.
