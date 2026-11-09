# Phase 11 temporal audit

**Implemented:** independent as-of retrieval checks on each store.

Rule:

```text
visible  ⇔  outcome_end < as_of_timestamp
```

Cases exercised on historical data:

- as-of = first decision timestamp
- as-of = first outcome_end (equal timestamp must remain unavailable)
- as-of = midpoint decision timestamp
- as-of = last stored decision timestamp
- as-of = `2026-09-29 17:50:00`

Paper completed retrieval at the approved as-of is empty because no paper trades exist. Incomplete outcomes stay unavailable.

**Not implemented:** using future outcomes to revise past decisions.
