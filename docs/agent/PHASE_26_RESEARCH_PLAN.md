# PHASE 26 — Research Plan (predeclared)

Recipe: `phase26_orthogonal_feature_outcome_v1`

## Objective

Investigate whether orthogonal features and richer outcome labels add incremental *predictive* information beyond the existing approved feature store and net-R labels — without repeating Phase 25 strategies.

Protected posture must remain: champion `NO_MODEL`, H13_C `EXPERIMENTAL`, production `WAIT`, Phase 25 `NO_NEW_EDGE_FOUND`.

## Preflight summary

```json
{
  "research_cutoff_utc": "2026-09-29 18:50:00",
  "n_m5_bars": 42450,
  "n_h1_bars": 51461,
  "n_decision_times_in_wf": 18234,
  "first_m5": "2026-02-16 12:55:00",
  "last_m5": "2026-09-29 18:50:00",
  "holdout_opened": false,
  "safety_all_pass": true,
  "orthogonal_candidates": [
    "rv_6",
    "rv_24",
    "atr_accel_6",
    "range_exp_24",
    "vol_persist_12",
    "er_20",
    "consec_dir",
    "ret_ac1_24",
    "chop_14",
    "dist_prior_high_20_atr",
    "dist_prior_low_20_atr",
    "wick_reject_up_atr",
    "wick_reject_dn_atr",
    "fail_break_up",
    "fail_break_dn",
    "range_compression_6_48",
    "h1_atr_pct",
    "h1_er_10",
    "m5_move_vs_h1_range"
  ],
  "decision_index_missing": 0
}
```

## Existing information already represented

- Trend / EMA geometry: `ema_*`, `close_to_ema_*`, spreads
- Volatility: `atr_14`, `atr_14_pct`, `volatility_12/48`, `volatility_ratio_12_48`, `bb_width`
- Candle anatomy: body/wicks/range ratios
- Short returns/momentum/ROC
- Sessions / clock features
- Outcomes: triple-barrier `net_r` / costs in `m5_side_outcomes.csv` (not MFE/MAE)

## Predeclared orthogonal candidates

| Feature | Formula |
|---------|---------|
| `rv_6` | stdev(log_return, 6) past-only incl. current closed bar |
| `rv_24` | stdev(log_return, 24) past-only |
| `atr_accel_6` | atr_14[t]/atr_14[t-6]-1 |
| `range_exp_24` | range[t]/SMA(range,24) |
| `vol_persist_12` | mean(rv_6>rv_24 over last 12 closed bars) |
| `er_20` | Kaufman ER: |close-close_20|/sum(|Δclose|) over 20 |
| `consec_dir` | signed consecutive close direction streak |
| `ret_ac1_24` | corr(r_t, r_{t-1}) over 24 closed log returns |
| `chop_14` | 100*log10(sum(TR)/|HH-LL|)/log10(14) |
| `dist_prior_high_20_atr` | (close-max(high[-20:-1]))/atr_14 |
| `dist_prior_low_20_atr` | (close-min(low[-20:-1]))/atr_14 |
| `wick_reject_up_atr` | upper_wick/atr_14 |
| `wick_reject_dn_atr` | lower_wick/atr_14 |
| `fail_break_up` | 1 if prior close > prior Donchian20 high and current close back <= that high |
| `fail_break_dn` | 1 if prior close < prior Donchian20 low and current close back >= that low |
| `range_compression_6_48` | SMA(range,6)/SMA(range,48) |
| `h1_atr_pct` | ATR(14)/close on last fully closed H1 bar |
| `h1_er_10` | Kaufman ER(10) on last fully closed H1 bar |
| `m5_move_vs_h1_range` | (close-h1_low)/(h1_high-h1_low)-0.5 using completed H1 |

Skipped families: `{"vwap": "Skipped \u2014 tick_volume/real_volume assumptions not validated for true VWAP."}`

Redundancy gate (predeclared): reject if max |corr| vs baseline ≥ **0.92** on WF1 train cutoff sample.

## Richer outcomes (research labels)

- Entry: next bar **open** after decision close `t`
- Horizons: [1, 2, 3, 4, 6, 8, 12] M5 bars
- MFE/MAE in ATR units of decision bar (separate from net R)
- Forward return, forward vol, time-to-fav/adv, fav-before-adv, neither
- Gap/incomplete windows excluded

## Predictive configs (predeclared)

```json
[
  {
    "id": "fwd_vol_12",
    "kind": "regression",
    "horizon": 12
  },
  {
    "id": "mfe_buy_12_atr",
    "kind": "regression",
    "horizon": 12
  },
  {
    "id": "mae_buy_12_atr",
    "kind": "regression",
    "horizon": 12
  },
  {
    "id": "fwd_ret_buy_6",
    "kind": "regression",
    "horizon": 6
  },
  {
    "id": "fav_before_adv_buy_12",
    "kind": "classification",
    "horizon": 12
  }
]
```

Models: Ridge (regression), LogisticRegression (classification). Chronological WF1–WF3 with purge=60 minutes. No iterative retuning.

## Experience sources

- `HISTORICAL_HYPOTHETICAL` and `AGENT_SHADOW` remain separate; Phase 26 does not merge them or change production policy.

