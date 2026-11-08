# AIBOT Acceptance Criteria (pre-registered)

Status: binding for every model or strategy experiment started after 2026-11-08. These criteria are fixed **before** any future experiment. A gate cannot be loosened after a result has been seen. Changes apply only to experiments registered after the change, and the change is logged with its date and reason.

All economic metrics use OOF predictions only, the single-position replay, and the realized net R definition in LEARNING_METHODOLOGY.md, section 5. Unless stated otherwise: costs at 1.0× (spread floor 15 points plus $0.05 per side), and R units, not USD (E15 showed USD and R can disagree when price levels change).

## 1. Gate sequence

| Gate | Name | Data used | Pass needed to continue |
|---|---|---|---|
| G0 | Integrity | Everything that is read | Yes, always |
| G1 | Probabilistic skill | Walk-forward OOF blocks | Yes |
| G2 | Walk-forward economics | Walk-forward OOF blocks | Yes |
| G3 | Robustness | Walk-forward OOF blocks | Yes |
| G4 | Final holdout (single use) | Data after 2026-09-29 18:50 | Yes |
| G5 | Forward paper signals | New closed bars after the holdout | Yes, before any further phase |

A candidate failing any gate is **rejected** and is not re-tested with modifications on the same data. A modified version is a new candidate and needs blocks it has never seen.

## 2. G0 — Integrity (all must pass)

- Every leakage check in AGENT_ARCHITECTURE.md, section 5 passes, including a leaky control that the check detects.
- The existing baseline reproduces exactly: labels, splits, `rf_m5_baseline.pkl` predictions and the 1,518 validation trades.
- The holdout guard records 0 opens of `xauusd_m5_test.csv`, and every loaded frame ends at or before the cutoff (before G4).
- Before/after file-hash snapshot: no existing file changed.
- The recipe hash was registered before the first OOF block was generated.

## 3. G1 — Probabilistic skill (necessary, not sufficient)

| Metric | Threshold |
|---|---|
| Brier skill score against the training-fold climatology (calibrated) | > 0 pooled, and > 0 in at least 2 of 3 blocks (at least 75% of blocks when there are 4 or more) |
| Expected calibration error (10 equal-count bins) | ≤ 0.03 pooled; ≤ 0.05 in every block |
| Reliability slope | 0.8–1.2 pooled |
| Direction tasks only (2-class) | Balanced-accuracy improvement ≥ +0.02 in at least 2 of 3 blocks, no block < −0.01, mean ≥ +0.02, block-bootstrap CI excluding 0 (the rule already used in E13/E14) |

## 4. G2 — Walk-forward economics

| Criterion | Threshold |
|---|---|
| Minimum trade count | Pooled ≥ 300 and ≥ 50 per block. This is a floor; the CI criterion below usually needs far more (section 9). |
| Walk-forward expected R | Pooled mean net R ≥ **+0.05R** |
| Block consistency | Mean R > 0 in at least 2 of 3 blocks (at least 75% when there are 4 or more); no block below −0.10R |
| Profit factor (R units) | Pooled ≥ **1.10**; no block below 0.90 |
| Confidence interval | 95% moving-block bootstrap of the pooled mean R (block = one trading day of trades; at least 2,000 resamples, fixed seed): **lower bound > 0** |
| Block bootstrap tail | Bootstrap P(mean R ≤ 0) < 2.5% (consistent with the CI) |
| Permutation test A (label null) | At least 200 permutations. Shuffle the training outcomes in blocks of one trading day and rerun the whole pipeline (fit, calibrate, EV, gate, replay). The observed pooled mean R must exceed the 95th percentile of the null (p ≤ 0.05). Null sanity: the null median sits within ±0.02R of the cost-only expectation. |
| Permutation test B (random-entry null) | At least 1,000 draws of random eligible entry bars with the same trade count, side mix and exit rules. Observed mean R above the 95th percentile (p ≤ 0.05). |
| Multiple testing | BH-FDR at q = 0.10 over every configuration registered in the same family. The candidate must survive. |
| Drawdown | Maximum closed-trade drawdown ≤ **20R** pooled, and total R / max drawdown ≥ 1.0 |
| Loss streak | Longest losing streak ≤ the 99th percentile of streaks simulated under the observed win rate (detects serial dependence) |
| Meta-model value | Mean R of accepted candidates minus mean R of vetoed candidates > 0, with a 95% block-bootstrap CI above 0. Otherwise the meta-model is removed and the simpler system is evaluated as a separate candidate. |
| Concentration | No single block contributes more than 50% of total R; no single session or ATR quartile more than 60%. BUY and SELL are reported separately. A one-sided system is allowed only if it was registered as one-sided. |

## 5. G3 — Robustness

| Criterion | Threshold |
|---|---|
| Spread × 1.5 | Pooled mean R ≥ +0.03R |
| Spread × 2.0 | Pooled mean R > 0 |
| Extra slippage +$0.10 per side | Pooled mean R > 0 |
| Edge versus cost | Pooled mean R ≥ 1.0 × the average round-trip cost in R (`cost_usd / risk`) |
| Outcome flips under cost stress | Reported. They do not decide pass or fail, but explain why the spread multiplier may have little effect. |
| Regime (ATR quartiles from development data only) | Mean R ≥ 0 in at least 3 of 4 quartiles; no quartile with ≥ 100 trades below −0.10R |
| Seed stability | 5 seeds (42 plus 4 pre-listed): every pooled mean R > 0; SD across seeds < 0.5 × the mean |
| Neighbourhood stability | Pre-registered ±1-step changes of `ev_margin` and `q_min` (checked for stability only, never used to select): pooled mean R > 0 for every neighbour |

## 6. G4 — Final holdout (one use only)

- Allowed only for **one** candidate that passed G0–G3, registered in advance with the exact recipe and the code commit or file hashes.
- Trade count ≥ 100. Fewer trades means **inconclusive**, which counts as not passed. No second attempt.
- Mean net R > 0, profit factor (R) ≥ 1.05.
- Mean R not below the 5th percentile of the walk-forward bootstrap distribution, scaled to the holdout trade count. This detects collapse.
- Maximum drawdown (R) ≤ 1.5 × the walk-forward bootstrap 95th-percentile drawdown at the same trade count.
- G0 integrity checks pass on the holdout run.
- After this single run the holdout is marked **consumed** in the registry, whatever the result. A failed candidate is permanently rejected.

## 7. G5 — Forward paper-signal performance (no orders)

| Criterion | Threshold |
|---|---|
| Duration and sample | At least 8 calendar weeks **and** at least 100 resolved BUY/SELL signals, whichever comes later; maximum 6 months |
| Mean realized R | > 0 |
| Agreement with expectation | Mean realized R ≥ 50% of the mean predicted EV of the same signals |
| Downside bound | One-sided 90% block-bootstrap lower bound of mean R > −0.05R |
| Calibration | ECE ≤ 0.05 on resolved outcomes |
| Sequential stop | A CUSUM/SPRT for "mean R ≤ 0", with boundaries fixed at the start, ends G5 early as **failed** when crossed |
| Journal completeness | 100% of closed bars journalled, including WAIT; zero hash-chain breaks; zero unresolved level-3 data alarms |
| Monitoring | No unresolved level-2 drift alarm at the end |

## 8. Champion/challenger replacement

A challenger replaces the champion only if all of these hold:

1. It passes G0–G3 on its own walk-forward history.
2. On the **same untouched evaluation block**, the challenger's mean R minus the champion's is ≥ **+0.03R**, with a paired block-bootstrap 95% CI above 0.
3. Its drawdown is no more than 20% worse than the champion's; its ECE is no more than 0.01 worse.
4. It passes G5-style forward checks on that block, where the block is forward data.

Ties or failures keep the champion. While no model has passed G4/G5, the champion is **"no model" (WAIT-only)**. `rf_m5_baseline.pkl` is the reference baseline, not a champion.

## 9. Statistical power (why trade count matters)

The number of trades needed for the 95% CI lower bound to clear 0 when the true mean is μ is about n ≈ (1.96 σ / μ)². Observed σ of trade R is about 1.25 for the 1.5:1 bracket (E3, E12) and about 1.45 for a 2:1 bracket (E15/E16 geometry).

| True mean R | n for the 1.5:1 bracket (σ ≈ 1.25) | n for the 2:1 bracket (σ ≈ 1.45) |
|---|---|---|
| +0.05R | ~2,400 | ~3,200 |
| +0.10R | ~600 | ~800 |
| +0.15R | ~270 | ~360 |

Implications: M5 walk-forward produced about 3,900 trades over three blocks (E12), which is enough to resolve +0.05R. The H1 pullback produced 446 walk-forward trades. Its +0.091R has an approximate SE of 0.068, so its 95% CI includes zero. This is computed from the reported figures, not by a new run.

## 10. Stop rules (research budget)

- At most 10 registered configurations per research family (for example "M5 meta-labeling", "H1 primary + EV") before a family-level review.
- If no configuration in a family passes G2, the family is closed on the current data. It is reopened only when new, untouched data is available.
- After every G4/G5 failure, record the lessons, but do not tune on the failed data.

## 11. Existing experiments against these gates (reference)

| Experiment | G1 | G2 | Status |
|---|---|---|---|
| E2/E3 RF baseline | Not computed (uncalibrated) | Fails: WF pooled −0.045R, CI below 0 | Rejected |
| E6 RF configurations | Not computed | Fails: all validation average R < 0 | Rejected |
| E7–E10 label and feature variants | Classification only; no consistent gain | Not run as gated economics | Rejected for those definitions |
| E11 Kronos-mini | Below chance | −0.063R | Rejected |
| E12 conditional subgroups | — | 0/102 survive FDR | Rejected |
| E13 M5 direction | Fails the +0.02 rule | — | Rejected |
| E14 M15 H4 direction | Meets the improvement rule; pre-declared permutation check failed | Not run | **Unconfirmed.** Eligible as a pre-registered G1/G2 candidate on new blocks only |
| E15 EMA pullback | — | Fails: CI includes 0 (approximate), USD negative, no permutation test | **Unconfirmed.** Eligible for re-evaluation under G2 only as a frozen rule with the full test battery |
| E16 EMA crossover | — | Fails: −0.106R WF | Rejected |
