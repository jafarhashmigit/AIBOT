# PHASE 27 — Research Plan

Recipe: `phase27_volatility_aware_decision_v1`

## Objective

Test whether Phase 26's improved `fwd_vol_12` prediction provides **decision-time** value for frozen H13_C BUY/SELL outcomes.

Protected posture: champion `NO_MODEL`, H13_C `EXPERIMENTAL`, production `WAIT`, Phase25 `NO_NEW_EDGE_FOUND`, Phase26 `PROMISING_BUT_UNCONFIRMED`.

## Predeclared methods

- Volatility model: Ridge(alpha=1.0) on baseline + Phase 26 accepted features.
- Walk-forward: WF1–WF3 with purge cutoff = fold_start − 60m.
- Regime method: **`train_predicted_vol_tertiles`** (tertiles of train *predicted* vol; never realized future vol for decision regimes).
- H13_C cuts frozen: q_low=25, q_high=75.
- Hypothetical policies: baseline, skip_high, skip_low, high/medium/low-only (no threshold search).
- Primary hypotheses: 6 (Bonferroni α=0.05/6).

## Preflight

```json
{
  "research_cutoff_utc": "2026-09-29 18:50:00",
  "n_m5": 42450,
  "n_decision_times": 18234,
  "holdout_opened": false,
  "safety_all_pass": true,
  "h13c_q": {
    "low": 25,
    "high": 75
  },
  "regime_method": "train_predicted_vol_tertiles",
  "phase26_accepted_n": 18
}
```

