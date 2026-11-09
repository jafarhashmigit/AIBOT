# Phase 3 decision policy

Declared before outer evaluation. Research only. Not live-ready.

## Interface

```text
decision(timestamp, information_available_at_timestamp) -> BUY / SELL / WAIT
```

Steps: compute BUY evidence, compute SELL evidence, compare, require a minimum gap, require evidence above tau after the approved cost model (already inside `net_r`), otherwise WAIT. Never force a trade.

## Expected-value formula (decision-time)

Class-conditional means are estimated on the **inner** window only:

`E[R | class, side] = mean(actual_net_r | exit_reason=class, side)` on inner rows.

Then for each outer timestamp:

`EV_side = p_tp_rf_side * E[R|TP,side] + p_sl_rf_side * E[R|SL,side] + p_time_rf_side * E[R|TIME,side]`

Probabilities are Phase 2 RF OOS outputs for that timestamp. The current row’s actual outcome is not used.

## Uncertainty (frozen)

`Conservative EV_side = EV_side − 1.0 * MAE_inner(EV_side, actual_R_side)`

k = 1.0 is not searched. Inner MAE was ≈ 1.17R on both sides, so conservative EV is almost always negative.

Near-tie rule: WAIT if `|cons_EV_BUY − cons_EV_SELL| < 0.02`.

## Threshold selection (inner only)

Candidate grids are tiny and frozen in `src/phase3/constants.py`.

Rule `inner_positive_then_most_conservative`: keep candidates with ≥ 50 inner trades and mean trade R > 0; if any remain, take the **highest** tau; else freeze Always WAIT for that nested fold.

## Frozen policy: `P3_CONSERVATIVE_EV`

This is the predeclared policy used for the economic gate, bootstrap headline, stress tests, and the decision journal.

On both N1 and N2 the inner catalogue produced **zero** trades at tau ∈ {0.00, 0.05} because conservative EV never cleared zero after the MAE penalty. The selection rule therefore froze Always WAIT for both outer folds.

That is the intended conservative behaviour, not a runtime error.

## Other predeclared policies (comparisons, not selected from outer results)

| ID | Evidence | Tau |
|---|---|---|
| A_WAIT | none | always WAIT |
| B_DIRECTION | `pred_r_rf` argmax | none (trade the better-looking side) |
| E1_PHASE2 | `pred_r_rf` argmax if > 0 | frozen at 0 (Phase 2 E1) |
| C_EV_THRESHOLD | `pred_r_rf` | inner-selected from {0.05, 0.10, 0.20} |
| D_PROB_ADVANTAGE | `p_tp_rf − p_sl_rf` | inner-selected from {0.00, 0.10, 0.20} |
| EV_ENGINE | raw EV from the formula above | inner-selected from {0.00, 0.05, 0.10} |
| META_RIDGE | Ridge expected R, plus P(R>0)>0.5 | inner-selected from {0.00, 0.05} |

Random Forest was not used as a meta-model (a priori: Phase 2 expected-R correlation ≈ 0.03).

## How a later agent could consume the journal (not implemented)

At decision time read only the non-`outcome_*` columns in `src/data/phase3_decision_journal.csv`. Those fields reconstruct the WAIT/BUY/SELL action. `outcome_*` columns exist for later scoring after the 12-bar window is historically complete and must not be fed back into the policy.
