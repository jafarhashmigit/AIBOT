# Phase 7 error analysis

Descriptive only. No new trading rule.

The frozen agent final action is WAIT on all 18,234 timestamps. There are **no final false BUY or false SELL**.

## Final policy

| | Count |
|---|---:|
| Final false BUY | 0 |
| Final false SELL | 0 |
| WAIT then hypothetical BUY net R > 0 | 6,796 |
| WAIT then hypothetical BUY net R ≤ 0 | 11,438 |
| WAIT then hypothetical SELL net R > 0 | 7,433 |
| WAIT then hypothetical SELL net R ≤ 0 | 10,801 |

Hypothetical side outcomes are the unused Phase 2 labels. More WAIT bars sit on negative hypothetical R than positive. That does **not** mean WAIT should be reversed: taking a side on every bar is the Direction baseline, which loses after costs.

## Pre-gate engine (not the agent)

Raw DecisionEngine output, uncertainty = 0, before the WAIT-only gate:

| Raw | Count | Of which realized R ≤ 0 |
|---|---:|---:|
| BUY | 1,420 | 902 |
| SELL | 9,903 | 5,831 |
| WAIT | 6,911 | — |

Raw is close to E1 but not identical (Phase 6 `min_gap=0.02` and CONFLICT when both conservative EVs clear tau). Those raw errors are why the frozen gate is WAIT-only. They are not a prompt to loosen the gate.

## Prediction vs realized R (diagnostics, not a fit)

| Side | Mean pred R | Mean actual R | corr(pred R, actual R) | corr(p_tp, actual R) |
|---|---:|---:|---:|---:|
| BUY | −0.111 | −0.096 | 0.010 | 0.029 |
| SELL | +0.007 | −0.018 | 0.017 | −0.028 |

RF probabilities cluster near 1/3. Predicted R barely ranks realized R. No recalibration was performed.

## Folds / models

Each timestamp uses the Phase 2 RF models for that fold (`rfclf_{side}_WFk`). Fold-level economic gaps appear in the E1/Direction baselines (WF2 worst), not in the agent (always WAIT). Model IDs were not changed.
