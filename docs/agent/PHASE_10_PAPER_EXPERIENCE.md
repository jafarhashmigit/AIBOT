# Phase 10 paper experience

Source type: `AGENT_PAPER`.

## Lifecycle

1. **Decision record** — observation/prediction references, raw proposal, RiskGate ALLOW/BLOCK, final action.
2. **Paper trade record** — created only if an approved simulator opens a trade.
3. **Paper outcome record** — attached only after `outcome_end < as_of`.

WAIT is journaled as a decision and never becomes a trade.

BLOCKED BUY/SELL is journaled as a decision (`final_action = WAIT`) and never becomes a trade.

## Phase 10 journal contents

Phase 9 OOS replay decisions are ingested as paper **decisions** only:

- provenance = `phase9_replay_log.csv`
- frozen WAIT-only RiskGate ⇒ no executable paper trades
- `trade_count = 0`, `completed_count = 0`

This is an offline journal, not real-time paper trading.

## Simulator interface

`PaperSimulator` accepts a decision plus a caller-supplied `EntryReference` and a caller-supplied outcome fixture.

It does not:

- look up live or unlabeled prices
- invent market outcomes
- call a broker
- connect to MT5

A future separately approved paper-trading phase may supply real simulated fills. That phase has not started.
