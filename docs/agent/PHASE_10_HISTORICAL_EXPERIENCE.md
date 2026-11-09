# Phase 10 historical experience

Source type: `HISTORICAL_HYPOTHETICAL`.

These records are **not** agent paper trades. They answer: what would have happened if BUY or SELL had been selected on an approved historical bar?

## Origin

Approved Phase 2 OOS predictions plus already-computed side outcomes. Labels are not regenerated.

Each completed timestamp yields two hypothetical experiences (BUY and SELL), each with:

### Decision-time fields

- `experience_id`, `source_type`, `decision_timestamp`, `side`
- RF probabilities and predicted R already present at decision time
- provenance = `phase2_oos_predictions.csv`
- `hypothetical_entry_reference` is omitted when the artifact does not provide an entry price (not fabricated)

### Outcome fields (separate object)

- `outcome_end` (decision time + 60 minutes)
- `exit_reason`, `actual_net_r`, `realized_pnl`
- `outcome_status = completed`

Outcome keys never appear on the decision-time object.

## Completeness

Only experiences with `outcome_end < as_of` enter the store used by intelligence. The last 13 OOS timestamps remain incomplete at `as_of = 2026-09-29 17:50:00`, matching Phase 8/9 pending horizons.
