# Phase 10 architecture

Research only. Not a trading strategy. Not production. Not live trading.

## Two independent experience sources

The agent may later learn from two domains that stay separately identifiable:

1. **Historical hypothetical experience** (`HISTORICAL_HYPOTHETICAL`)
2. **Agent paper experience** (`AGENT_PAPER`)

Raw records are never merged into one unlabeled dataset.

```text
Approved historical OOS
  → hypothetical BUY/SELL outcomes
  → HistoricalExperienceStore

Agent decision journal
  → frozen RiskGate
  → paper decisions (WAIT/BLOCK never become trades)
  → PaperExperienceStore (trades only if an approved simulator opens them)

Both stores
  → read-only ExperienceIntelligence
```

Phase 10 does **not** change the Phase 6 WAIT-only RiskGate and does **not** make trading decisions.

## Source provenance

Every record carries an explicit `source_type`. Identifiers are prefixed:

- historical: `hist:{timestamp}:{side}`
- paper: `paper:{timestamp}:XAUUSD:M5`

Missing, unknown, or cross-store source types are rejected.

## What Phase 10 implements

- Dual schemas and stores
- Strict `outcome_end < as_of` retrieval
- Read-only intelligence summaries
- Offline paper simulator **interface** (fixture outcomes only)

## What remains unimplemented

- Live or scheduled paper trading
- MT5 / broker connectivity
- Combining sources inside a learner
- Any change to the frozen RiskGate
