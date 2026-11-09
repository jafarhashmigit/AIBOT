# Phase 8 temporal leakage rules

Enforced in `ExperienceStore.query` and the chronological replay. Not documentation-only.

## Retrieval boundary

```text
visible(experience, T)  ⇔  experience.outcome_end < T
```

If `outcome_end == T`, the experience is **not** visible. This is the chosen strict convention.

Example:

- Decision 10:00, horizon 12 M5 bars → `outcome_end = 11:00`
- Not usable at 10:05, 10:30, 10:59, or 11:00
- Usable starting at the first later timestamp with `T > 11:00`

## What may not happen

- An incomplete horizon is never appended.
- A future `outcome_end` is never returned by `query(T)`.
- Experience from T cannot influence a decision at T or earlier.
- The store is append-only; size never decreases.
- The store is not preloaded with the full OOS file before replay.

## Cutoff

`outcome_end > 2026-09-29 18:50:00` is rejected. Decision timestamps after the cutoff are rejected. The holdout file is not opened.
