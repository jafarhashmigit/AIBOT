# PHASE 30 — Results

Created: `2026-11-10T09:59:02Z`
Phase verdict: **NO_NEW_EDGE_FOUND**
Champion: `NO_MODEL` | H13_C: `PAUSED_FROZEN_BENCHMARK` (FROZEN_BENCHMARK) | Production: `WAIT`

## Comparative table (pooled, after costs)

| Strategy | N | Mean R | PF | Win% | Max DD$ | Fold Stability | Status |
|---|---:|---:|---:|---:|---:|---|---|
| H13_C (FROZEN_BENCHMARK) | 226 | 0.048561 | 1.089975 | 0.433628 | 101.736875 | False | FROZEN_BENCHMARK |
| vol_norm_momentum | 6611 | -0.032667 | 0.944231 | 0.399637 | 1598.162329 | False | REJECTED |
| m15_trend_m5_trigger | 10031 | -0.049412 | 0.916373 | 0.392384 | 3245.756524 | False | REJECTED |
| robust_mad_reversion | 2599 | -0.049348 | 0.915716 | 0.390920 | 922.359446 | False | REJECTED |
| body_persistence | 152 | -0.002486 | 0.995675 | 0.401316 | 92.765808 | False | REJECTED |
| regime_cond_momentum | 4764 | -0.056738 | 0.903984 | 0.387490 | 2396.469767 | False | REJECTED |
| regression_residual_mr | 2899 | -0.068321 | 0.885572 | 0.387375 | 1142.821963 | False | REJECTED |
| wick_exhaustion | 287 | -0.084651 | 0.861827 | 0.379791 | 165.392285 | False | REJECTED |
| compression_expansion | 59 | -0.055278 | 0.903511 | 0.389831 | 32.718957 | False | REJECTED |
| momentum_structure_ensemble | 40 | -0.046647 | 0.919927 | 0.400000 | 27.785574 | False | REJECTED |
| london_open_imbalance | 0 | nan | nan | nan | 0.000000 | True | WEAK_UNCONFIRMED |

## Ranking (composite)

- #1 `vol_norm_momentum` score=0.096831 status=REJECTED mean_r=-0.032667 n=6611 sig/500=181.282220
- #2 `m15_trend_m5_trigger` score=0.068983 status=REJECTED mean_r=-0.049412 n=10031 sig/500=275.063069
- #3 `robust_mad_reversion` score=0.065540 status=REJECTED mean_r=-0.049348 n=2599 sig/500=71.267961
- #4 `body_persistence` score=0.059323 status=REJECTED mean_r=-0.002486 n=152 sig/500=4.168038
- #5 `regime_cond_momentum` score=0.054062 status=REJECTED mean_r=-0.056738 n=4764 sig/500=130.635077
- #6 `regression_residual_mr` score=0.033115 status=REJECTED mean_r=-0.068321 n=2899 sig/500=79.494351
- #7 `wick_exhaustion` score=-0.004444 status=REJECTED mean_r=-0.084651 n=287 sig/500=7.869913
- #8 `compression_expansion` score=-0.048854 status=REJECTED mean_r=-0.055278 n=59 sig/500=1.617857
- #9 `momentum_structure_ensemble` score=-0.067024 status=REJECTED mean_r=-0.046647 n=40 sig/500=1.096852
- #10 `london_open_imbalance` score=-1498.396052 status=WEAK_UNCONFIRMED mean_r=nan n=0 sig/500=0.000000

## Required answers

1. Outperform H13_C mean R? best Δ check via ranking; H13_C mean_r=0.048561
2. Survive all WF folds? n_fold_stable=1
3. Survive costs? see Gate E / cost_robustness 1.5x in per-strategy blocks
4. Survive bootstrap? see CI in metrics.bootstrap
5. Survive permutation? see robustness_results for shortlist
6. Param perturbation? see robustness_results
7. Single-trade dependent? see drawdown_concentration flags
8. Multiple-testing: tested=10; 10 predeclared strategies evaluated once (no iterative OOS retuning). Best raw mean R is not automatically a winner; composite rank + gates applied. Multiple-testing penalty included in composite score via log(n) term.
9. Failed families: see REJECTED/WEAK statuses
10. Forward-shadow deserving: verdict=NO_NEW_EDGE_FOUND
11. Signals per 500 (best): 181.282220
12. Forward validation practicality: require non-rare frequency + RESEARCH_CANDIDATE
13. Better path than H13_C? only if RESEARCH_CANDIDATE_FOUND with material improvement

Positive mean-R families: 0

## Diversity

```json
{
  "n_positive_mean_r": 0,
  "n_fold_stable": 1,
  "n_research_candidate": 0,
  "n_promising": 0
}
```

## Final safety

- Production = `WAIT`
- Champion = `NO_MODEL`
- H13_C = `PAUSED_FROZEN_BENCHMARK`
- Broker Orders = 0
- Holdout Accessed = false

## Best composite candidate (not automatically an edge)

- id: `vol_norm_momentum`
- status: REJECTED
- n: 6611
- mean_r: -0.032667
- pf: 0.944231
- max_dd: 1598.162329
- rationale: Non-positive pooled mean R after costs.

