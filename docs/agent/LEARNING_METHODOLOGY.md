# AIBOT Learning Methodology (proposed)

Status: design only (Phase 0). No result is assumed. Given the baseline inventory, the most likely outcome is that the agent mostly outputs WAIT and no candidate passes the acceptance gates. The methodology is built to detect that honestly.

## 1. Approaches evaluated

| Approach | What it learns | Fit for AIBOT now | Verdict |
|---|---|---|---|
| **Supervised primary model** | P(outcome \| features) per side, from cost-aware historical outcomes | Matches the data (about 40k labeled M5 rows, 51k H1 bars), the hardware (CPU RF/GBM in seconds to minutes) and the existing pipeline | **Core component** |
| **Meta-labeling** | P(candidate trade is profitable \| primary output, regime, recent realized outcomes) | Directly implements "learn from realized trade outcomes" and "learn when not to trade". Needs OOF primary predictions. | **Core component** |
| **Contextual bandit (offline)** | A policy context → {BUY, SELL, WAIT} that maximizes expected reward | Our simulator can compute the outcome of *every* action for every bar (no market impact assumed), so this is a full-information problem. A bandit then reduces to cost-sensitive classification, which supervised + EV already does. Exploration is unnecessary. | **Optional later**, only as a cost-sensitive policy learner over OOF features, with off-policy evaluation on the journal |
| Reinforcement learning (PPO, DQN) | Sequential policy | Sample-inefficient; non-stationary data; tends to exploit simulator quirks (spread floor, same-bar SL rule, gaps); no base edge for it to amplify; impractical on a GTX 1050 | **Not recommended** |
| Pretrained foundation models (Kronos) | Generic forecasts | E11: worse than no-change forecasts and below chance | **Rejected** for now |

The only true sequential dependence is "one simulated position at a time". It is handled by the single-position replay in evaluation, not by RL.

## 2. How the agent learns from historical outcomes

1. **Outcome table (component A).** For every closed bar t and each side s ∈ {BUY, SELL}, simulate the hypothetical trade with the backtester rules: entry at open[t+1], TP = 1.5×ATR14[t], SL = 1.0×ATR14[t], 12-bar time exit, and the costs. Store `outcome_s ∈ {TP, SL, TIME}`, `net_r_s` and `outcome_known_at_s`. These are realized historical experiences.
2. **Primary learning.** The supervised model learns P(TP), P(SL) and P(TIME) for each side from those outcomes. That is learning which market states historically led to which outcomes.
3. **Meta learning.** For the primary model's candidate trades, the realized `net_r` becomes the meta-label. The meta-model learns which kinds of candidates the primary model gets wrong: regimes, sessions, low margins, or periods after recent losses.
4. **Experience accumulation.** As new closed bars arrive, their outcomes resolve after 12 bars and are appended to the outcome table and the journal. The next scheduled retraining includes them. That is the agent's continuous learning, and it is always offline, scheduled and gated.

## 3. How the agent learns when NOT to trade

WAIT arises at five independent points, and each is recorded with a reason code:

| Stage | Mechanism | Learned or fixed |
|---|---|---|
| Primary model | High P(SL) or P(TIME) relative to P(TP) gives low EV | Learned |
| Meta-model | Low P(profit) for this kind of candidate | **Learned from realized outcomes** |
| EV engine | The lower confidence bound of EV is below the margin | Fixed rule on learned inputs |
| Risk gate | Data, cost, exposure or health checks fail | Fixed rule |
| Monitor | A drift or performance alarm triggers WAIT-only mode | Fixed rule on observed outcomes |

The journal records the hypothetical outcome of every WAIT bar, so the value of abstaining is measurable: **avoided R** (mean R of vetoed candidates) and **missed R**. If vetoed candidates do as well as accepted ones, the meta-model isn't adding value. That is part of gate G2 in ACCEPTANCE_CRITERIA.md.

## 4. Probability calibration

- **Why:** E5 showed the RF vote shares are confined to 0.33–0.48 and don't rank outcomes. EV needs probabilities in real units.
- **Where:** inside each walk-forward training window, split chronologically: base-fit segment, purge and embargo, then a calibration segment (the last 20% of the window, with at least 2,000 rows for M5).
- **Method (pre-registered order):**
  1. Multiclass per side (TP/SL/TIME): temperature scaling or vector scaling on log-probabilities.
  2. Binary meta-model: Platt (sigmoid) scaling by default. Isotonic only if the calibration segment has at least 5,000 rows.
- **Evaluation on OOF blocks:** Brier score against a climatology baseline (training-fold class frequencies), log loss, ECE with 10 equal-count bins, reliability slope and intercept, and per-bin counts. These feed the EV standard error.
- **Rule:** if calibrated probabilities do not beat climatology on Brier in the OOF blocks, the model has no usable probabilistic skill and every EV is treated as below the margin, which means WAIT.

## 5. Realized net R

Exactly as in `backtest_rf_m5.py` (the reference implementation; any new simulator must reproduce its 1,518 validation trades bit-for-bit first):

```
spread_k   = max(spread_points[k], 15) * 0.01          # USD/oz, bar k
c          = 0.05                                       # per side
risk       = SL_ATR * ATR14[t]   (= 1.0 * ATR14[t])     # 1R in USD/oz
BUY : entry = open[t+1] + spread_{t+1} + c
      exit valued at bid - c   (TP/SL at level; gap-through-SL at open - c; TIME at close[t+12] - c)
SELL: entry = open[t+1] - c
      exit valued at ask + c = price + spread_k + c
net_usd    = (exit - entry) for BUY, (entry - exit) for SELL
net_r      = net_usd / risk
```

Properties: TP exits give exactly +1.5R and SL exits exactly −1R, except gap fills (observed SL mean −1.015R). Costs act by moving the trigger levels, so cost stress has to be tested through outcome flips and an explicit **cost in R** (`cost_usd / risk`), not only spread multipliers (see the E16 finding).

Stress variants, all pre-registered: spread ×1.5 and ×2.0; an extra $0.10 per side of slippage; and the cost floor raised to the 95th-percentile spread. Portfolio metrics use the single-position replay. Per-candidate meta-labels use independent per-row outcomes.

## 6. Generating historical predictions without in-sample leakage

```
blocks  = consecutive, non-overlapping time blocks B_1..B_K (e.g. ~4-5 weeks of M5; quarters of H1)
for k in first_eval..K:
    train_rows = rows with outcome_known_at < start(B_k) - embargo        # purge + embargo
    split train_rows chronologically -> fit_part | purge | calib_part
    fit primary on fit_part; fit calibrator on calib_part
    predict B_k  -> OOF primary predictions (store model_id, train_end, fold=k)
for k in first_meta_eval..K:
    meta_rows = OOF candidates from blocks < k with outcome_known_at < start(B_k) - embargo
    fit + calibrate meta-model on meta_rows (same internal split)
    predict candidates in B_k -> OOF meta predictions
EV, signals, gate, single-position replay run on OOF predictions only.
```

Assertions in code: per row, `train_end + embargo ≤ tau`. A prefix test checks that predictions on a block prefix are identical to the full-block predictions. Every meta training row is out-of-fold for the primary model. Fold ids are stored and checked.

The current minimum training history is 55% of rows (the existing WF design). With 7.5 months of M5 that leaves about 3 evaluation blocks, which is why Phase 1 prioritizes more data (section 9).

## 7. Adding future closed-bar data safely

1. **Download only closed bars.** Use `copy_rates_range` ending at the last bar whose close ≤ the request time minus one bar. `copy_rates_from_pos` is never used, because it returns the forming bar.
2. **Append-only.** New bars go to a new dated file (`incoming/xauusd_m5_<from>_<to>.csv`). The overlap with already-stored bars must match their hashes bit-for-bit; a mismatch is a level-3 alarm (broker history revision).
3. **Quarantine before training.** A new block is first an **evaluation block** (forward OOS). It becomes training data only at the next scheduled retraining, after its evaluation has been recorded.
4. **Manifests.** Each dataset version records its source, server, row count, range, prefix hashes and the cutoff it respects.
5. **Holdout ordering.** The reserved holdout (after 2026-09-29 18:50) is consumed once, by gate G4. Data after the holdout's end forms the forward paper period (gate G5) and later rolling evaluation blocks.
6. **No backfilling of features with later-revised external data.** Every external value carries `available_at`.

## 8. Model replacement (champion/challenger)

1. **Pre-registration** (written before any evaluation block is generated): recipe (features, target, model, parameters, calibrator, EV constants, gate values), data range, evaluation block, and the acceptance thresholds from ACCEPTANCE_CRITERIA.md.
2. **Freeze.** The recipe hash is recorded. Any change after an evaluation block is generated makes a *new* challenger that needs a *new* untouched block.
3. **Evaluate** champion and challenger on the same untouched block, plus their walk-forward history.
4. **Promote** only if the challenger passes every absolute gate *and* beats the champion by the pre-set margin, with a paired block-bootstrap CI above zero. Ties keep the champion. "No champion" (WAIT-only) is a valid state and is the current one.
5. **Record** the decision, metrics and block consumption in the registry, including rejections.
6. **Multiple-testing ledger.** Every configuration evaluated on a given block is counted. BH-FDR (q = 0.10) is applied across that family, and the count is reported with the result.

## 9. Data available for training (pre-cutoff)

| Data | Span | Usable for |
|---|---|---|
| M5 XAUUSD | 2026-02-16 → 2026-09-29 (about 40.5k labeled rows) | Primary M5 models; 3 WF blocks |
| M15 (from M5) | Same span (14,163 candles) | M15 models (E14 follow-up) |
| H1 XAUUSD | 2018-01-02 → 2026-09-29 (51,461 bars) | Long-history H1/H4 models with many WF blocks; the strongest base for learning |
| DXY basket M5, US yields daily | 2026-02 → 2026-09 | Tested in E9 (no gain); available for meta features |
| Calendar timing | 2026 events | Tested in E10 (no gain) |
| Deeper M5 history | **Unknown.** Limited by MT5 `maxbars` = 100,000 (about 1.4 years of M5 at roughly 70k bars per year) and broker depth | To be probed read-only in Phase 1 |

## 10. Compute plan

The machine has an Intel i7-7700HQ (4 cores), 24 GB RAM and a GTX 1050 with 4 GB. The fixed RF, gradient boosting and logistic models run on the CPU. A full walk-forward with calibration takes minutes per configuration. No GPU deep learning or RL is planned. Experiment count is limited by statistical budget (multiple testing), not by compute.

## 11. What this methodology will not do

- Tune thresholds, features or parameters on an evaluation block or the holdout.
- Learn online from live markets or adapt intraday.
- Treat a classification improvement as evidence of profit.
- Assume that the agent will become profitable.
