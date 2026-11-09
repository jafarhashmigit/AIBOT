# Phase 9 learning design

Frozen **before** OOS scoring. One learner. No search.

## Hypothesis

H1: completed historical experience (`outcome_end < T`) can improve future decision quality vs the frozen no-experience agent.

H0: it does not.

## Learner (only candidate)

Side-specific **Ridge** (`alpha = 1.0`, intercept included, intercept not penalized).

Target per side: approved hypothetical side-outcome `actual_net_r` (already in Phase 2 OOS). Not a new label.

No scaler: allowlisted inputs are already probabilities in `[0, 1]` and predicted R of similar magnitude. Scaling is not required.

`MIN_EXPERIENCES_PER_SIDE = 100`. Below that: `NO EXPERIENCE MODEL AVAILABLE` → frozen Phase 6 DecisionEngine on RF predicted R.

## PHASE9_LEARNER_FEATURE_ALLOWLIST

Decision-time only:

- `p_tp_rf_BUY`, `p_sl_rf_BUY`, `p_time_rf_BUY`
- `p_tp_rf_SELL`, `p_sl_rf_SELL`, `p_time_rf_SELL`
- `pred_r_rf_BUY`, `pred_r_rf_SELL`
- `pred_r_ridge_BUY`, `pred_r_ridge_SELL`
- `pred_r_rf_diff` = `pred_r_rf_BUY - pred_r_rf_SELL`
- `p_tp_rf_diff` = `p_tp_rf_BUY - p_tp_rf_SELL`

Rejected: realized R, P&L, exit reason, future prices, `outcome_end`, any `actual_*` / `hypothetical_*` as features.

## Decision rule (frozen)

After the learner (or fallback engine):

- BUY iff `pred_BUY > 0` and `pred_BUY > pred_SELL`
- SELL iff `pred_SELL > 0` and `pred_SELL > pred_BUY`
- else WAIT

Then **unchanged** Phase 6 WAIT-only RiskGate. The gate is not loosened.

## Ablation

A: frozen agent (no experience fit).  
B: experience Ridge as above.  
Identical observations, Phase 2 predictions, chronology, costs, RiskGate.
