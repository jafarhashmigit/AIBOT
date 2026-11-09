# Phase 21 Results

**Recipe:** `phase21_h13c_threshold_reachability_v1`  
**Date:** 2026-11-09  

**Research only — no trading edge established.**

## 1. BUY condition reachability (frozen WF3)

| Metric | Value |
|--------|------:|
| Eligible observations | 42,450 |
| H1-up | 19,817 |
| BUY pullback (`c2e <= low`) | 10,679 |
| Complete BUY rule | **283** |
| BUY rate | **0.667%** |

## 2. SELL condition reachability (frozen WF3)

| Metric | Value |
|--------|------:|
| H1-down | 22,633 |
| SELL extension (`c2e >= high`) | 10,406 |
| Complete SELL rule | **401** |
| SELL rate | **0.945%** |

## 3. Frozen threshold statistics

| Cut | Value |
|-----|------:|
| q_low / q_high | 25 / 75 |
| `close_ema_low` | -0.0010069324198160867 |
| `close_ema_high` | 0.0009989244530461683 |
| WF3 train n / cutoff | 36,061 / 2026-08-26 12:55:00 |

### Feature distributions (historical, ≤ cutoff)

**close_to_ema_20** (n=42,450): min/max/mean/median and q1–q99 in `reports/phase21/feature_distributions.csv` (q25 ≈ -0.001015, near frozen low).  

**ema_9_20_spread:** full distribution in same CSV.  

**H1 direction:** up 19,817 · down 22,633.

## 4. Historical WAIT reason distribution

| Reason | Count |
|--------|------:|
| `h1_up_pullback_not_met` | 19,534 |
| `h1_down_pullback_not_met` | 22,232 |
| Actions BUY/SELL (`selected`) | 684 total |

WAIT dominates (~98.4% of bars).

## 5. Real vs historical comparison

| Source | n | Exp BUY/SELL/WAIT |
|--------|--:|-------------------|
| Phase 16A live shadow | 24 | 0 / 0 / 24 |
| Phase 20 live shadow | 12 | 0 / 0 / 12 |
| Phase 20A diagnosis | — | same failure: `h1_up_pullback_not_met` |
| Historical frozen | 42,450 | 283 / 401 / 41,766 |

Live short H1-up windows with **zero** frozen BUY matches are **consistent** with a highly selective rule (~0.67% historical BUY rate), not evidence that RiskGate deletes experimental BUY. Live rows were **not** merged into historical research.

## 6. Hypothetical percentile sensitivity (research only)

WF3-train recomputed cuts; **not applied** to agent:

| q_low | BUY | SELL | BUY rate | SELL rate |
|------:|----:|-----:|---------:|----------:|
| 25 (frozen-equivalent recompute) | 283 | 401 | 0.667% | 0.945% |
| 20 | 160 | 241 | 0.377% | 0.568% |
| 15 | 71 | 153 | 0.167% | 0.360% |
| 10 | 30 | 81 | 0.071% | 0.191% |
| 5 | 10 | 38 | 0.024% | 0.090% |

Tighter percentiles **reduce** frequency. Higher frequency is **not** better performance.

## 7. Restrictiveness judgment

Label: **`highly_selective_but_reachable`**

Frozen thresholds are rare (~0.7–0.9% full-rule hit rate) but **not unreachable** on permitted history. Conjunction of H1 direction + pullback/extension + EMA spread drives scarcity more than any single cut alone.

## 8. Future research hypothesis?

**Yes, justified as a separate research track** — e.g. whether recent live regimes undersample historical pullback frequency — **without** changing frozen thresholds, forcing signals, or claiming edge.

## Integrity

- Holdout access: 0  
- Thresholds modified: false  
- Protected Phase 14/16A hashes: OK  
- Champion `NO_MODEL` · H13_C `EXPERIMENTAL` · production `WAIT`  
- No MT5 / Discord / orders / training / packages / push  

## Explicit conclusion

**Research only — no trading edge established.**
