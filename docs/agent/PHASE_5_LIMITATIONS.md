# Phase 5 limitations

Independent NY-SELL replication. Not a live system. Not production-ready.

## What this phase did not do

- Did not retune NY hours, SELL side, TP/SL, horizon, or costs
- Did not add trend, volatility, EMA, RSI, RF probabilities, or any new model
- Did not pool Phase 4 and Phase 5 to recover a positive mean
- Did not search another window, side, asset, or broker after seeing the result
- Did not open the final holdout
- Did not append independent bars to `xauusd_m5.csv`
- Did not place MT5 orders or add live execution

## Data

- Independent history is the existing MT5 archive from `2025-06-02 01:30` through `2026-02-16 08:45` (50,000 M5 bars). That is months, not years.
- 219 gaps > 5 minutes, 39 gaps > 12 hours, 40 weekday gaps > 8 hours. Gaps were not filled; those windows are ineligible.
- 53 zero-range dojis left in place.
- Last 12-bar windows were **not** completed using the approved file, so the final days of the independent file contribute fewer eligible trades (last eligible decision `2026-02-13 22:55`).
- Broker server face remains Europe/Athens. DST conversion matches Phase 4; a residual localization error would affect session flags, not the sign of a large negative mean by itself.

## Inference

- Consecutive M5 SELL decisions overlap in path. Day-cluster bootstrap (182 days, seed 42, 2,000 draws) is the uncertainty method; it does not make overlapping trades independent.
- Largest loss −3.53 R can occur when the entry bar gaps through the stop without the 12-bar window being labeled a calendar gap. That is the frozen Phase 1 simulator, not a Phase 5 change.
- Cost stress omits two rows with non-positive reconstructed initial risk (8,444 vs 8,446). Immaterial to the sign.

## Interpretation

Phase 4 NY-SELL (`n=1,710`, mean R +0.036, CI including 0) was a short summer-2026 outer-OOS cell. Phase 5 is a longer earlier sample whose mean, PF, all three chronological blocks, bootstrap CI, and 1.5× stress are negative.

That is **non-replication**, not proof that some other untested filter would work. Filters were not searched.

Phase 1 permutation A remains `not_run`.

## Stop

Phase 5 is complete. Do not implement live signals, MT5 execution, automated trading, or Phase 6 until explicit approval.
