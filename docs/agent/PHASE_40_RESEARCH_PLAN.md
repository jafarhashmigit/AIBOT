# Phase 40 — Research Plan

Extend Phase38 MT5 archive with full-session ticks and H1 warm-up for 10 dates.
Data readiness only — no strategy evaluation.

**Recipe:** `phase40_targeted_historical_coverage_v1`

## Constraints
- MT5 historical read-only; no orders; no installs; no holdout.
- Never overwrite Phase38; store under `src/data/phase40/`.
- Max wall 10 minutes; one date at a time; resume-safe.

