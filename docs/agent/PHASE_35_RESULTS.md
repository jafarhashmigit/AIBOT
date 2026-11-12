# Phase 35 — Final Report

**Recipe:** `phase35_historical_execution_revaluation_v1`
**Executive verdict:** `PROMISING_BUT_UNCONFIRMED`

## Strategy comparison

| Strategy | Previous Mean R | Historical Bid/Ask Mean R | N Resolved | N Unresolved | PF | Max DD (R) | Verdict |
|---|---|---|---|---|---|---|---|
| `H13_C` | 0.04856060840719428 | 0.32434827014197903 | 22 | 0 | 1.6765540171190139 | -6.061205190567348 | INSUFFICIENT_SAMPLE |
| `mean_reversion` | -0.07520041102335161 | 0.07350397989615302 | 102 | 5 | 1.1345501313967772 | -23.76596832309305 | UNCONFIRMED |
| `breakout_retest` | -0.10010444891988272 | -0.22930918660554475 | 111 | 7 | 0.6600312822118581 | -29.18539360043801 | REJECTED |
| `smc_liquidity` | n/a | None | 0 | 0 | None | 0.0 | INSUFFICIENT_SAMPLE |
| `regime_router` | -0.09090909090909442 | 1.2477490353199998 | 4 | 0 | inf | 0.0 | INSUFFICIENT_SAMPLE |
| `mtf_h1_m5` | -0.020453238495809035 | -0.1545946341620816 | 11 | 0 | 0.7634793569804353 | -2.703956661500163 | INSUFFICIENT_SAMPLE |
| `vol_norm_momentum` | -0.032667297112387264 | -0.08198984866100044 | 472 | 27 | 0.8655289229397293 | -48.98664259420637 | REJECTED |
| `compression_expansion` | n/a | -1.0105419661396455 | 4 | 1 | 0.0 | -4.042167864558582 | INSUFFICIENT_SAMPLE |
| `robust_mad_reversion` | -0.04934843607006664 | -0.13642876076244884 | 224 | 4 | 0.7864272879597634 | -56.44976810556729 | REJECTED |
| `regression_residual_mr` | n/a | -0.1709352407352402 | 256 | 3 | 0.715654759827151 | -71.20904080662525 | REJECTED |
| `wick_exhaustion` | n/a | -0.24481373018443717 | 22 | 2 | 0.643177919788944 | -11.95117445022527 | INSUFFICIENT_SAMPLE |
| `regime_cond_momentum` | n/a | -0.013680710240208544 | 371 | 1 | 0.9757094033453682 | -24.853718450162184 | REJECTED |
| `london_open_imbalance` | n/a | -0.02320071964558092 | 133 | 0 | 0.9623606089364469 | -23.031860966476014 | REJECTED |
| `m15_trend_m5_trigger` | -0.0494117107544147 | -0.11160107050688771 | 777 | 60 | 0.8208498813188608 | -99.93899854311798 | REJECTED |
| `body_persistence` | n/a | 0.026944359757682244 | 10 | 2 | 1.053311661517703 | -2.741627661151341 | INSUFFICIENT_SAMPLE |
| `momentum_structure_ensemble` | n/a | None | 0 | 0 | None | 0.0 | INSUFFICIENT_SAMPLE |

## Execution comparison

- VIEW A: historical bid/ask tick-path (primary)
- VIEW B: legacy frozen mid+floor+$0.05/side (comparison only)
- VIEW C: stress = VIEW A minus unverified $0.05/side (sensitivity)
- Spread is not double-counted on VIEW A; COMMISSION_UNVERIFIED; SLIPPAGE_UNVERIFIED

## Data limitations

- Complete trading days only: **6** (2026-02-17, 2026-03-06, 2026-03-10, 2026-05-15, 2026-07-08, 2026-09-15)
- Ticks used: **2351368**
- Recomputed spread median/mean/p95: `{'n': 2351368, 'median': 0.6900000000000546, 'mean': 0.7063982396630404, 'p95': 0.98700000000008}`
- Missing/failed Phase 34 hours → UNRESOLVED_DATA_GAP (no fabrication)
- MT5 parity: PENDING (not used)
- Commercial licensing: not cleared
- Tick-path coverage incomplete across selected 20-day set

## Safety

- MT5 = NOT USED
- Broker orders = `0`
- Discord = `0`
- Telegram = `0`
- Package installations = `False`
- Holdout accessed = `False`
- Phase 0–34 = untouched
- Phase 34 immutable = `True`
- Commit/push = `False` / `False`
- Independent recompute OK = `True`
- Production = `WAIT` | Champion = `NO_MODEL`

## Runtime

- START_UTC: `2026-11-10T20:33:55Z`
- END_UTC: `2026-11-10T20:35:48Z`
- DURATION: `1.88 min`

