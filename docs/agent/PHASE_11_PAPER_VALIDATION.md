# Phase 11 paper validation

**Implemented:** read-only audit of `PaperExperienceStore` journaled from Phase 9 replay decisions.

Expected honest state under the frozen WAIT-only RiskGate:

- 18,234 decisions
- 0 paper trades
- 0 completed paper outcomes

Zero trades is **not** a validation failure.

Checks:

- `source_type` is `AGENT_PAPER`
- timestamps ordered
- WAIT is not a trade
- BLOCKED is not an executed trade
- no outcome attached without a trade
- no fabricated entry/exit prices
- decision-time objects have no future outcome fields

**Not implemented:** live paper trading, manufactured fills, or loosening the RiskGate to create trades.
