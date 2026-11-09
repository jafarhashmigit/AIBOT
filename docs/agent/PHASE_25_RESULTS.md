# PHASE 25 — Results

Created: `2026-11-09T15:48:36Z`
Phase verdict: **NO_NEW_EDGE_FOUND**
Champion: `NO_MODEL` | H13_C: `EXPERIMENTAL` | Production: `WAIT`

## Comparative table (pooled, after costs)

| Strategy | Status | N | Mean R | Net R | PF | Win% | Max DD$ | CI low | CI high |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H13_C (benchmark) | EXPERIMENTAL | 226 | 0.048561 | 10.974698 | 1.089975 | 0.433628 | 101.736875 | -0.137632 | 0.216662 |
| mean_reversion | REJECTED | 2038 | -0.075200 | -153.258438 | 0.874986 | 0.380275 | 624.389392 | -0.148087 | 0.004110 |
| breakout_retest | REJECTED | 1596 | -0.100104 | -159.766700 | 0.838948 | 0.370301 | 1003.175050 | -0.169618 | -0.033504 |
| smc_liquidity | INCONCLUSIVE | 0 | nan | 0.000000 | nan | nan | 0.000000 | nan | nan |
| regime_router | REJECTED | 22 | -0.090909 | -2.000000 | 0.857143 | 0.363636 | 15.143899 | -0.545455 | 0.375000 |
| mtf_h1_m5 | REJECTED | 229 | -0.020453 | -4.683792 | 0.964990 | 0.406114 | 107.808412 | -0.188843 | 0.155815 |

## Per-strategy decisions

### mean_reversion

- Status: **REJECTED**
- Rationale: Pooled mean net R <= 0 after costs.
- Signals/trades: 2038/2038 (BUY 1033 / SELL 1005)
- Δ mean R vs H13_C: -0.123761
- WF1 mean R (n=622): -0.073987
- WF2 mean R (n=727): -0.074083
- WF3 mean R (n=689): -0.077475
- Cost 1.5x mean R: -0.091121
- Gates: `{"pooled_mean_r_gt_0": false, "ci_low_gt_0": false, "all_active_folds_mean_r_gt_0": false, "cost_1_5x_mean_r_gt_0": false, "min_pooled_n": true, "min_days": true, "beats_h13c_pooled_mean_r": false}`

### breakout_retest

- Status: **REJECTED**
- Rationale: Non-positive expectancy with CI not supporting upside.
- Signals/trades: 1596/1596 (BUY 804 / SELL 792)
- Δ mean R vs H13_C: -0.148665
- WF1 mean R (n=520): -0.062228
- WF2 mean R (n=552): -0.070153
- WF3 mean R (n=524): -0.169244
- Cost 1.5x mean R: -0.116169
- Gates: `{"pooled_mean_r_gt_0": false, "ci_low_gt_0": false, "all_active_folds_mean_r_gt_0": false, "cost_1_5x_mean_r_gt_0": false, "min_pooled_n": true, "min_days": true, "beats_h13c_pooled_mean_r": false}`

### smc_liquidity

- Status: **INCONCLUSIVE**
- Rationale: Too few trades for credible inference.
- Signals/trades: 0/0 (BUY 0 / SELL 0)
- Δ mean R vs H13_C: nan
- WF1 mean R (n=0): nan
- WF2 mean R (n=0): nan
- WF3 mean R (n=0): nan
- Cost 1.5x mean R: nan
- Gates: `{"pooled_mean_r_gt_0": false, "ci_low_gt_0": false, "all_active_folds_mean_r_gt_0": true, "cost_1_5x_mean_r_gt_0": false, "min_pooled_n": false, "min_days": false, "beats_h13c_pooled_mean_r": false}`

### regime_router

- Status: **REJECTED**
- Rationale: Pooled mean net R <= 0 after costs.
- Signals/trades: 22/22 (BUY 12 / SELL 10)
- Δ mean R vs H13_C: -0.139470
- WF1 mean R (n=9): -0.444444
- WF2 mean R (n=4): 0.250000
- WF3 mean R (n=9): 0.111111
- Cost 1.5x mean R: -0.113204
- Gates: `{"pooled_mean_r_gt_0": false, "ci_low_gt_0": false, "all_active_folds_mean_r_gt_0": false, "cost_1_5x_mean_r_gt_0": false, "min_pooled_n": false, "min_days": false, "beats_h13c_pooled_mean_r": false}`

### mtf_h1_m5

- Status: **REJECTED**
- Rationale: Pooled mean net R <= 0 after costs.
- Signals/trades: 229/229 (BUY 107 / SELL 122)
- Δ mean R vs H13_C: -0.069014
- WF1 mean R (n=68): 0.035919
- WF2 mean R (n=72): -0.078043
- WF3 mean R (n=89): -0.016935
- Cost 1.5x mean R: -0.036765
- Gates: `{"pooled_mean_r_gt_0": false, "ci_low_gt_0": false, "all_active_folds_mean_r_gt_0": false, "cost_1_5x_mean_r_gt_0": false, "min_pooled_n": true, "min_days": true, "beats_h13c_pooled_mean_r": false}`

## Rejected / inconclusive hypotheses

- `mean_reversion` → REJECTED: Pooled mean net R <= 0 after costs.
- `breakout_retest` → REJECTED: Non-positive expectancy with CI not supporting upside.
- `smc_liquidity` → INCONCLUSIVE: Too few trades for credible inference.
- `regime_router` → REJECTED: Pooled mean net R <= 0 after costs.
- `mtf_h1_m5` → REJECTED: Pooled mean net R <= 0 after costs.

## Data integrity & safety

```json
{
  "holdout_file_exists_but_not_opened": true,
  "holdout_accesses": true,
  "bundle_holdout_flag_false": true,
  "all_timestamps_le_max_decision": true,
  "research_cutoff_respected_on_features": true,
  "broker_orders": true,
  "mt5_connections": true,
  "discord_messages": true,
  "telegram_messages": true,
  "packages_installed": true,
  "oci_provisioned": true,
  "github_push": true,
  "autonomous_retrain": true,
  "production_final_action_wait": true,
  "all_pass": true
}
```

## Multiple-testing note

Five predeclared strategies + one frozen benchmark evaluated once. No iterative parameter search against validation folds.

## Recommended next research step

Preserve champion `NO_MODEL`, H13_C `EXPERIMENTAL`, production `WAIT`. Next research should explore orthogonal features/labels or longer out-of-sample observation — not promote any Phase 25 strategy to production.

## Artifacts

- `C:\Users\Dell\Documents\1\AIBOT\reports\phase25\phase25_summary.json`
- `C:\Users\Dell\Documents\1\AIBOT\reports\phase25\comparative_results.json`
- `C:\Users\Dell\Documents\1\AIBOT\reports\phase25\strategy_decisions.json`
- `C:\Users\Dell\Documents\1\AIBOT\reports\phase25\repo_audit.json`

