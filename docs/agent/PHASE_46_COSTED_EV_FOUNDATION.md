# Phase 46 — Costed Expected Value Foundation

**Recipe:** `phase46_costed_expected_value_foundation_v1`  
**Verdict:** `COSTED_EV_FOUNDATION_READY`  
**Champion:** `NO_MODEL` | **Production:** `WAIT`

## Purpose
M1 foundation: action-conditioned BUY/SELL/WAIT outcomes with bid/ask execution,
gross vs net separation, explicit cost scenarios, and independent recomputation.

This phase does **not** discover or promote a trading edge.

## Frozen contract
- Contract SHA-256: `44e33d0ea569c916d2f3332d875799076dc75149abe6b02f09abb4e44893984d`
- Horizon: `12` M5 bars
- BUY entry ASK / exit BID; SELL entry BID / exit ASK
- WAIT: zero incremental PnL and costs (no opportunity-cost model here)
- Commission/slippage under OBSERVED_BIDASK_ONLY: **UNKNOWN** (not invented)
- Demo source is **not** live broker truth

## Data exposure
- Engineering dates: Phase44 discovery dates only (already exposed)
- Forbidden: Phase44 validation dates, holdout, legacy tests
- Independent validation is **not** claimed

## Out of scope
Neural nets, RL, bandits, online policy updates, strategy discovery,
indicator screens, live trading, model promotion.

## Final verdict
`COSTED_EV_FOUNDATION_READY` — BUY/SELL/WAIT outcomes defined with bid/ask fills, gross/net separation, explicit unknown costs, exposure accounting, and independent verification. No profitability claim.

See `reports/phase46/FINAL_REPORT.md`.
