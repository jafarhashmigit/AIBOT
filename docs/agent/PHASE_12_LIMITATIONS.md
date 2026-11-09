# Phase 12 limitations

1. Stage A only. No forward observations have been collected from the live market.
2. Champion remains `no_model`; every shadow decision is WAIT.
3. Phase 6 RiskGate source is unchanged; post-cutoff Phase 6 Observation objects are not passed into `evaluate()`.
4. MT5 read-only adapter exists but is not imported or connected in Stage A.
5. No hypothetical trade P&L is computed or labeled as paper P&L.
6. `FORWARD_SHADOW` is not merged with historical or paper stores.
7. Gaps are excluded, never filled.
8. Not a trading edge. Not production. Not live trading.
