# Phase 7 evaluation design

Declared with the policy freeze, before scoring.

## Population

Paired Phase 2 OOS timestamps (BUY and SELL rows joined). Chronological. Folds WF1, WF2, WF3 reported separately and pooled. Not the holdout.

## Agent path

```text
Phase 2 OOS row pair
    → Observation (no actual_* fields)
    → Phase2PredictorAdapter.predict
    → Phase 6 DecisionEngine
    → Phase 6 RiskGate
    → final BUY / SELL / WAIT
    → decision journal (no realized outcome)
    → later evaluation join
```

## Metrics

Same approved side-outcome `actual_net_r` / `actual_net_pnl` (costs already inside). For policies with trades: n, mean/median/total R, net P&L, PF, win rate, max DD, average trade, largest win/loss, losing streak. Day-cluster bootstrap 2,000 draws, seed 42, on trade R.

WAIT-only policies: trade metrics are empty; decision distribution is still reported.

## Diagnostics

Descriptive only: probability / predicted-R / uncertainty distributions; predicted vs realized R. No recalibration. No new rule.
