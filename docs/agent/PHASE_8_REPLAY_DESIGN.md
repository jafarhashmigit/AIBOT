# Phase 8 replay design

Declared before scoring. Frozen Phase 6 policy. No threshold search.

## Inputs (read-only)

- `src/data/phase7_oos_agent_decisions.csv` — decision-time journal
- `src/data/phase7_oos_agent_evaluation.csv` — approved side outcomes, joined only after each horizon
- Phase 2 OOS SHA-256 checked; file not regenerated

## Loop

For each OOS timestamp T in chronological order:

1. Append pending experiences with `outcome_end < T` (approved outcomes only).
2. Query the store (ablation B) or skip (ablation A).
3. Build Observation without outcome fields.
4. Run Phase 6 `DecisionEngine` then WAIT-only `RiskGate`.
5. Record final action and experience metadata.
6. Enqueue this timestamp as pending until `T + 60 minutes`.

Do not complete the last hour of decisions inside the OOS window: there is no later T with `outcome_end < T`. Those rows are skipped with reason `horizon_not_completed_before_next_oos_bar`, not dropped silently.

## Ablation (predeclared)

- **A — No Experience:** query is not used; `experience_n = 0`.
- **B — Experience Available:** query returns the deterministic summary.

DecisionEngine / RiskGate inputs do not include the summary. Both ablations must keep final WAIT.

## Determinism

Replay A and B each twice. Compare experience counts, summaries, final actions, skip reasons. Seed 42 unused (no RNG).
