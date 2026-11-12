# PHASE 27 — Results

Verdict: **PROMISING_BUT_UNCONFIRMED**
Rationale: Possible decision-quality signal under filters, but volatility prediction and/or fold evidence is incomplete.

Champion `NO_MODEL` | H13_C `EXPERIMENTAL` | Production `WAIT`
Phase25 `NO_NEW_EDGE_FOUND` | Phase26 `PROMISING_BUT_UNCONFIRMED`

## Volatility prediction audit (independent recompute)

- Folds improved: 3 / 3; all: True

- WF1: baseline MAE=0.000287589 → ortho MAE=0.000277718 (Δ=9.87105e-06, improved=True); class_acc=0.4682461335965778; regime_agree=0.48206646923330043
- WF2: baseline MAE=0.000270202 → ortho MAE=0.000255991 (Δ=1.42104e-05, improved=True); class_acc=0.48206646923330043; regime_agree=0.5065811122079631
- WF3: baseline MAE=0.000260975 → ortho MAE=0.000247657 (Δ=1.33175e-05, improved=True); class_acc=0.4633865394108935; regime_agree=0.5051834786901431

## Hypothetical policies vs baseline

- `baseline_h13c`: n=226 mean_r=0.04856060840719428 Δ=0.0 PF=1.0899746441904932 win=0.4336283185840708 cost1.5x=0.03578970962899189
- `skip_high_pred_vol`: n=100 mean_r=-0.06069277379817847 Δ=-0.10925338220537276 PF=0.8926104214519806 win=0.39 cost1.5x=-0.07533779534796238
- `skip_low_pred_vol`: n=208 mean_r=0.06405847949934135 Δ=0.015497871092147064 PF=1.1189918327497803 win=0.4326923076923077 cost1.5x=0.051435377662796676
- `high_only`: n=126 mean_r=0.13526964190352184 Δ=0.08670903349632755 PF=1.2603763364722358 win=0.46825396825396826 cost1.5x=0.12398614215038409
- `medium_only`: n=82 mean_r=-0.045363550536350716 Δ=-0.093924158943545 PF=0.9200323451799705 win=0.3780487804878049 cost1.5x=-0.060045065330325526
- `low_only`: n=18 mean_r=-0.13052590199094935 Δ=-0.17908651039814363 PF=0.7650533764163021 win=0.4444444444444444 cost1.5x=-0.14500467653941904

## Decision-quality answers

```json
{
  "1_pred_vol_identifies_favorable_BUY": {
    "answer": "partial/unconfirmed",
    "evidence": {
      "buy_high_mean_r": 0.21385302748872684,
      "buy_low_mean_r": -0.20966651909400075,
      "n_high": 59,
      "n_low": 7,
      "sufficient": false
    }
  },
  "2_pred_vol_identifies_favorable_SELL": {
    "answer": "partial/unconfirmed",
    "evidence": {
      "sell_high_mean_r": 0.06606934713446078,
      "sell_low_mean_r": -0.08016369110718934,
      "n_high": 67,
      "n_low": 11
    }
  },
  "3_helps_fav_vs_adverse": {
    "answer": "see mfe_mae_by_regime in h13c_regime_analysis",
    "note": "Uses Phase 26 MFE/MAE research labels joined retrospectively."
  },
  "4_improves_net_expectancy_after_costs": {
    "answer": true,
    "baseline_mean_r": 0.04856060840719428,
    "skip_high_mean_r": -0.06069277379817847,
    "skip_low_mean_r": 0.06405847949934135
  },
  "5_consistent_across_WF1_3": {
    "vol_pred_all_folds": true,
    "skip_high_active_folds_all_positive": false,
    "skip_low_active_folds_all_positive": false
  },
  "6_adds_info_beyond_existing_features": {
    "answer": true,
    "note": "Orthogonal features improve fwd_vol_12 MAE vs baseline features in walk-forward audit."
  },
  "7_justify_future_shadow": {
    "answer": false,
    "note": "Requires CANDIDATE_FOR_FUTURE_SHADOW_TEST; default conservative unless CI/cost/fold gates clear."
  }
}
```

## Statistical notes

- Primary passes: 2 / 6
- Contradictory folds: []

## Safety

```json
{
  "holdout_exists_unopened": true,
  "m5_holdout_flag_false": true,
  "times_le_cutoff": true,
  "h13c_q_low_unchanged": true,
  "h13c_q_high_unchanged": true,
  "broker_orders": true,
  "mt5": true,
  "discord": true,
  "telegram": true,
  "packages": true,
  "oci": true,
  "github_push": true,
  "autonomous_retrain": true,
  "production_wait": true,
  "champion_no_model": true,
  "h13c_experimental": true,
  "phase25_preserved": true,
  "phase26_preserved": true,
  "phase16a_21_hashes_match": true,
  "all_pass": true
}
```

## Commands

```powershell
$env:PYTHONPATH='src'
python -m unittest phase27.tests.test_phase27 -v
python -m phase27.run_phase27
```

