# Phase 10 temporal safety

Enforced in code for **both** sources:

```text
visible  ⇔  outcome_end < as_of_timestamp
```

Equality is not visible. Incomplete outcomes are not stored in the completed retrieval path.

## Rules

- Future outcome exclusion
- Incomplete outcome exclusion
- Chronological insertion (no backdating of decision timestamps)
- Decision-time objects cannot carry outcome fields
- Historical and paper retrieval are separate
- Queries after the research cutoff are rejected
- Decision timestamps after `2026-09-29 17:50:00` are rejected in this phase

## Paper attachment

A simulated outcome is attached only when `outcome_end < as_of`. Opening a trade does not complete it.
