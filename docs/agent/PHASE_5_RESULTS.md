# Phase 5 independent NY-SELL replication results

Finding class: **exploratory**. Frozen hypothesis only. No new filters. No new model. Not production-ready. Not live-ready.

Hypothesis was written in `docs/agent/PHASE_5_HYPOTHESIS.md` **before** this scoring. Machine-readable: `reports/phase5/replication_results.json`.

## Frozen rule (not retuned)

Exclusive corrected-UTC New York session (`in_ny` and not `in_london`; NY local hour `[8, 17)`), SELL only, next-open entry, TP 1.5 ATR14 / SL 1.0 ATR14 / 12-bar horizon, SL-first same bar, approved costs, ineligible if the window is incomplete or gap-crossing.

## Independent sample

- Bars: 50,000, `2025-06-02 01:30:00` → `2026-02-16 08:45:00`
- NY-SELL rows including ineligible: 10,654
- Eligible observations / trades: **8,446**
- Eligible decision range: `2025-06-02 19:00:00` → `2026-02-13 22:55:00`
- Not pooled with Phase 4

## Primary replication (eligible NY SELL)

| Metric | Independent Phase 5 |
|---|---:|
| Eligible observations | 8,446 |
| Trades | 8,446 |
| Mean R | **−0.0816** |
| Median R | −1.000 |
| Total R | −689.11 |
| Net P&L (USD/oz) | −1,559.73 |
| Profit factor | **0.929** |
| Win rate | 38.87% |
| Max drawdown (USD) | 2,611.56 |
| Max drawdown (R) | 713.30 |
| Average trade (USD) | −0.185 |
| Largest win (R) | +1.500 |
| Largest loss (R) | −3.531 |

Median R ≈ −1 because the modal outcome is a full stop. Mean R is negative. PF < 1.

## Chronological blocks (predeclared equal-duration thirds)

Boundaries from eligible `decision_time` span, not chosen after seeing signs:

- early: `[2025-06-02 19:00:00, 2025-08-27 04:18:20)`
- middle: `[2025-08-27 04:18:20, 2025-11-20 13:36:40)`
- late: `[2025-11-20 13:36:40, 2026-02-13 22:55:00]`

| Block | n | Mean R | PF | Win rate | Sign |
|---|---:|---:|---:|---:|---|
| Early | 2,868 | −0.134 | 0.773 | 37.31% | negative |
| Middle | 2,795 | −0.060 | 0.929 | 39.71% | negative |
| Late | 2,783 | −0.050 | 0.979 | 39.63% | negative |

Positive blocks: **0 / 3**. No sign reversal (all negative). Losses are smaller in later thirds but never cross zero.

## Statistical uncertainty

Day-cluster bootstrap of mean trade R. Cluster = calendar day of `decision_time`. Draws = 2,000. Seed = 42. Days = 182.

| | |
|---|---|
| Mean R | −0.0816 |
| 95% CI | **[−0.139, −0.025]** |
| P(mean R ≤ 0) | **0.998** |

The interval is entirely below zero. Individual M5 candles were not treated as independent.

## Cost stress

Baseline costs are already inside `net_r`. Extra USD = (multiplier − 1) × $0.15 spread floor (same Phase 4 approximation). Two eligible rows with non-positive reconstructed risk are omitted from the stressed means (n = 8,444).

| Cost | Mean R | PF | Net P&L |
|---|---:|---:|---:|
| Baseline | −0.082 | 0.929 | −1,559.73 |
| 1.5× spread floor | −0.107 | 0.902 | −2,193.03 |
| 2.0× spread floor | −0.133 | 0.876 | −2,826.33 |

The result does not appear under modest cost stress. It is already negative at baseline.

## Concentration (reported; result is not positive)

The independent mean is negative, so concentration cannot manufacture a replica. For completeness:

- Best trade: +1.500 R (`2025-07-03 22:45:00`)
- Worst trade: −3.531 R (`2025-11-27 21:20:00`)
- Top 1% winners (85 trades) share of total R: −0.185 (share sign is inverted because total R is negative)
- Longest losing streak: 63 trades
- Max drawdown: 2,611.56 USD / 713.30 R

Top 5 winners are all ~+1.50 R TP hits. Top 5 losers: −3.53, −2.75, −1.14, −1.05, −1.04 R. The pooled loss is broad, not one outlier.

## Comparison with Phase 4 (not pooled)

| Metric | Phase 4 | Independent Phase 5 |
|---|---:|---:|
| Observations | 1,710 | 8,446 |
| Mean R | +0.036 | −0.082 |
| PF | 1.092 | 0.929 |
| Win rate | 44.0% | 38.9% |
| Max DD (USD) | 394.93 | 2,611.56 |
| 1.5× stress mean R | +0.021 | −0.107 |

Phase 4 and Phase 5 are different periods. They are **not** concatenated. The independent period is larger, fully negative in every predeclared block, and its day-cluster CI excludes zero on the downside.

## Classification

**NOT REPLICATED**

- Independent mean R ≤ 0
- Independent PF ≤ 1
- Baseline costs already fail
- 1.5× stress remains negative

The Phase 4 NY-SELL cell does not reproduce on the independent historical period. It is not a confirmed edge. It is not a production strategy.

No additional subgroup was mined after seeing this result.
