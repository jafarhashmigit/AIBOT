# Phase 9 limitations

This phase is a controlled OOS experiment, not a trading system.

1. The Phase 6 RiskGate remains WAIT-only with champion `no_model`. It blocks every BUY/SELL. Final trade count is therefore expected to be zero regardless of learner output. The gate was not loosened.
2. One predeclared learner: side-specific Ridge, alpha=1.0. No search, no second candidate.
3. Features are only the frozen Phase 2 decision-time allowlist. No new indicators.
4. Targets are hypothetical side `actual_net_r` already present in Phase 2 OOS. WAIT experiences have no selected realized R; both sides are trained from the same timestamp.
5. Cold start uses the frozen Phase 6 DecisionEngine until 100 completed experiences per side.
6. The holdout file was not opened. No row after `2026-09-29 18:50:00` UTC was used.
7. Prediction-quality and pre-gate raw-action metrics are descriptive. They were not used to retune alpha, features, or the decision rule.
8. Bootstrap is descriptive evidence for the single predeclared comparison. It is not a license to try another learner.
9. Improvement of raw (pre-gate) counts would still not be an economic edge: costs, fills, and live execution are out of scope; the frozen gate remains in the architecture.
10. Phase 9 does not claim production readiness and does not enable live trading.

Empirical note: final BUY=0, SELL=0, WAIT=18234; completed experiences=18221.
