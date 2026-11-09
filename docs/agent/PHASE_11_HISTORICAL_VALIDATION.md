# Phase 11 historical validation

**Implemented:** read-only audit of `HistoricalExperienceStore` rebuilt from approved Phase 2 OOS artifacts. Outcomes are not regenerated.

Checks:

- `source_type` is always `HISTORICAL_HYPOTHETICAL`
- BUY and SELL remain distinct (`hist:{timestamp}:{side}`)
- provenance is `phase2_oos_predictions.csv`
- every stored record has a completed outcome
- incomplete rows stay out of completed retrieval (26 side-rows skipped at `as_of = 2026-09-29 17:50:00`)
- IDs unique; no `paper:` prefixes
- no outcome fields on decision-time objects
- records are labeled as hypothetical paths, not agent paper trades

Phase 10 reconciliation target: 36,442 completed (18,221 BUY + 18,221 SELL).

**Not implemented:** any rewrite of historical labels or a combined store.
