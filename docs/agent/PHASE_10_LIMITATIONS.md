# Phase 10 limitations

1. Architecture and validation only. No claim that experience learning improved OOS decision quality (Phase 9 already concluded it did not).
2. The Phase 6 WAIT-only RiskGate is unchanged. No paper trade can be opened from the Phase 9 journal.
3. Historical BUY/SELL counts are hypothetical sides, not executed agent trades.
4. The paper simulator does not generate market outcomes. Tests use explicit synthetic fixtures.
5. No live market access, no MT5, no broker orders, no background watcher, no scheduled paper trading.
6. Holdout / post-cutoff market rows are not accessed.
7. Sources are not combined inside a learner in this phase.
8. Missing hypothetical entry prices are left null rather than fabricated.
9. Not production-ready. Not live-trading-ready. Not an economic edge.

Empirical note (computed, not hardcoded): as of `2026-09-29 17:50:00`, historical completed records = 36,442 (18,221 BUY + 18,221 SELL hypotheticals; 26 incomplete side-rows skipped); paper decisions = 18,234; paper trades = 0; paper completed outcomes = 0.
