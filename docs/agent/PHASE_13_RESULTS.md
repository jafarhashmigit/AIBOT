# Phase 13 results

**Conclusion: `EXPERIMENTAL_CANDIDATE_FOUND`**

Champion status: **`NO_MODEL`** (unchanged). No BUY/SELL enablement in Phase 6 / 12 / 12C. Not production. Not live trading.

An experimental research tag was assigned to `H13_C_H1_PULLBACK` under the pre-registered incomplete-gate rule. It is **not** a validated edge: WF1 is negative, the day-cluster CI includes 0, and FDR fails.

## Data

| | |
|---|---|
| OOS timestamps | 18,234 |
| Range | `2026-06-19 03:05:00` → `2026-09-29 17:50:00` |
| Max decision time | `2026-09-29 17:50:00` |
| Holdout opens | 0 |
| H1 join coverage | 1.0000 |
| Outcomes | eligible `m5_side_outcomes` only (costs inside `net_r`) |

## Hypotheses scored

| ID | Status | Trades | Mean R | Net USD/oz | PF | Win rate | Max DD USD | 95% CI mean R | FDR |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| H13_A_BREAKOUT_FAILURE | REJECTED | 1,286 | −0.152 | −695 | 0.764 | 0.348 | 750 | [−0.229, −0.074] | fail |
| H13_B_VOL_EXPANSION_TREND | REJECTED | 2,817 | −0.112 | −2,275 | 0.811 | 0.372 | 2,604 | [−0.200, −0.026] | fail |
| H13_C_H1_PULLBACK | EXPERIMENTAL | 226 | +0.049 | +88 | 1.090 | 0.434 | 102 | [−0.138, +0.217] | fail |
| H13_D_PRED_GAP_MIDVOL | REJECTED | 4,255 | −0.050 | −1,179 | 0.915 | 0.395 | 1,279 | [−0.114, +0.010] | fail |

### Walk-forward (H13_C)

| Fold | n | Mean R |
|---|---:|---:|
| WF1 | 63 | −0.108 |
| WF2 | 67 | +0.188 |
| WF3 | 96 | +0.054 |

Majority of active folds positive (2/3), but **not all folds positive**. That alone blocks `VALIDATED_CANDIDATE`.

### Cost stress (H13_C)

| Stress | Mean R |
|---|---:|
| 1.5× spread-floor approx | +0.036 |
| 2.0× | +0.023 |

Stress means stay positive, but the primary CI still includes 0 and FDR fails.

### Rejected candidates (summary)

- **H13_A:** CI entirely below 0; all folds negative after costs.
- **H13_B:** Pooled negative; CI below 0; WF3 strongly negative.
- **H13_D:** E1-style filter still loses; all folds negative; not an improvement over B_E1 economically.

## Baselines

| Policy | Trades | Mean R |
|---|---:|---:|
| B_WAIT | 0 | n/a |
| B_E1 (frozen Phase 2) | 11,418 | −0.021 |

## Experience sources

- `HISTORICAL_HYPOTHETICAL`: used only as labeled side outcomes for scoring.
- `AGENT_PAPER`: completed trades remain **0**; none fabricated; not combined into a learner.

## Why champion stays `NO_MODEL`

`H13_C` is tagged EXPERIMENTAL for possible later isolated research (longer M5 history / independent replication). It does **not** meet the pre-registered validation gate (all active folds positive, CI lower > 0, FDR). Phase 4→5 already showed that a fragile positive slice can reverse out of sample. No production promotion. No signal path changes.

## Safety

- MT5 connections: 0
- Broker orders: 0
- Package changes: 0
- Tests: 14/14 twice
- GitHub pushed: no
- Stage B: not authorized
