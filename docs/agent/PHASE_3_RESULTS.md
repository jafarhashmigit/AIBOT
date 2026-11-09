# Phase 3 results

Finding class: **exploratory**. Frozen policy status: **experimental**. Not production-ready. Not live-ready.

Outer evaluation: Phase 2 WF2+WF3 only, 12,156 timestamps, 2026-07-23 11:25 → 2026-09-29 17:50. Seed 42. Costs already inside side-outcome `net_r` / `net_pnl`.

Machine-readable: `reports/phase3/decision_results.json`. Journal: `src/data/phase3_decision_journal.csv` (12,156 rows, including WAIT).

## Frozen policy `P3_CONSERVATIVE_EV`

Inner selection froze Always WAIT on both nested folds (conservative EV never exceeded 0 after the 1.0×MAE penalty).

| | Combined | WF2 (N1 outer) | WF3 (N2 outer) |
|---|---|---|---|
| Decisions | 12,156 | 6,078 | 6,078 |
| BUY / SELL / WAIT | 0 / 0 / 12,156 | 0 / 0 / 6,078 | 0 / 0 / 6,078 |
| Trades | 0 | 0 | 0 |
| Mean R per decision | 0 | 0 | 0 |
| Mean R per trade | n/a | n/a | n/a |
| Net R / net P&L | 0 / $0 | 0 / $0 | 0 / $0 |

Day-cluster bootstrap of **decision** R (49 days, 2,000 draws, seed 42): mean 0, CI [0, 0]. Trade-R bootstrap is undefined (no trades). Cost stress and threshold perturbation are not applicable.

**This is not an edge. It is a refusal to trade.**

## Mandatory references (identical outer timestamps)

| Policy | Trades | WAIT | Mean trade R | Mean decision R | Net R | Net USD/oz | PF | Win rate | Max DD USD |
|---|---|---|---|---|---|---|---|---|---|
| A_WAIT | 0 | 12,156 | n/a | 0 | 0 | 0 | n/a | n/a | 0 |
| E1_PHASE2 | 7,316 | 4,840 | −0.029 | −0.018 | −214.4 | −1,141.61 | 0.945 | 40.0% | 1,433 |
| B_DIRECTION | 12,156 | 0 | −0.041 | −0.041 | −495.6 | −2,396.10 | 0.932 | 39.6% | 2,748 |
| **P3_CONSERVATIVE_EV** | **0** | **12,156** | n/a | **0** | **0** | **0** | n/a | n/a | 0 |

E1 on this outer sample matches Phase 2’s WF2+WF3 readout (3,938 and 3,378 trades, mean R −0.034 and −0.023). BUY E1: 1,085 trades, −0.102R. SELL E1: 6,231 trades, −0.017R.

Day-cluster 95% CI for E1 mean **trade** R: **[−0.081, +0.022]**, P(mean ≤ 0) = 0.88, 49 days.

Always taking a side (B) is worse than E1. Filtering to WAIT (frozen policy) matches Always WAIT.

## Other predeclared comparisons (not used to pick a winner)

These were frozen from **inner** data. Outer numbers are reported for honesty, not for selection.

### C_EV_THRESHOLD (inner tau 0.05 on N1, 0.10 on N2)

2,248 trades (342 BUY / 1,906 SELL). Mean trade R **+0.0038**. Net R +8.48. **Net USD −232.57**. PF 0.962. WF2 mean R −0.008 (1,898 trades); WF3 +0.066 (350 trades). Trade-R CI **[−0.081, +0.093]**. One fold negative, USD negative, CI includes 0.

Slightly positive average R is not an economic edge after costs. Classification-style filtering reduced trade count; it did not produce a stable dollar edge.

### D_PROB_ADVANTAGE

N1 fell back to WAIT. N2 used tau 0.10. Outer: 173 trades, all in WF3, mean R **−0.165**, CI [−0.404, +0.121], 22 days. Sample too small and losing.

### EV_ENGINE

Inner mean R negative at every tau. Frozen to WAIT. Identical to Always WAIT on outer.

### META_RIDGE (inner tau 0.05 both folds)

Inner mean trade R was +0.11 / +0.13. Outer: 3,322 trades (298 BUY / 3,024 SELL), mean trade R **−0.011**, net USD +54.66, PF 1.006. WF2 +0.004R; WF3 −0.033R. Trade-R CI **[−0.092, +0.071]**, P(mean ≤ 0) = 0.57.

Inner positivity did not survive outer evaluation. That is overfitting of the decision layer to the calibration window, not a confirmed edge.

## What improved vs what did not

- **Predictive:** not re-scored as a classifier in this phase. Phase 2 RF already beat a class prior; that did not become an edge here.
- **Trade filtering:** C and META traded less than E1. Fewer trades is not automatically better.
- **Economic:** no policy cleared the Phase 3 gate. Frozen policy = WAIT. E1 and B lose after costs. C has mixed folds and negative USD. META overfits inner data.

## Phase 3 economic gate (frozen policy)

Failed: mean trade R not positive (no trades), majority of folds not positive, CI not above 0, trade count < 50, cost/perturbation positivity n/a.

Leakage audit: passed.

Phase 1 permutation A: still `not_run`. Not this gate.

## Conclusion

**NO CREDIBLE ECONOMIC EDGE**
