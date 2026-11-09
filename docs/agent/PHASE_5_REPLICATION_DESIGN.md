# Phase 5 replication design

Declared with the hypothesis, before independent scoring.

## Population

Eligible SELL outcomes at exclusive corrected-NY session timestamps in `phase5_independent_m5.csv` only.

Not Phase 4 OOS. Not the approved `xauusd_m5.csv`. Not the holdout.

## Blocks

Three equal-duration chronological thirds of the eligible NY-SELL `decision_time` range. Boundaries are a frozen formula, not chosen after seeing mean R.

## Uncertainty

Day-cluster bootstrap of mean trade R, 2,000 draws, seed 42. Cluster = calendar day of `decision_time` (server date face).

## Cost stress

Phase 4 approximation: extra USD = (multiplier − 1) × $0.15 spread floor. $0.10 round-trip extra is not scaled. Multipliers 1.5 and 2.0 only.

## What is not done

No BUY, no extra filters, no session-bound search, no pooling with Phase 4, no new model.
