# PHASE 30 — Research Plan (Multi-Strategy Discovery & Ranking)

Recipe: `phase30_multi_strategy_discovery_v1`

## Objective

Discover whether any independently specified strategy family produces a more credible
cost-aware OOS edge than frozen H13_C (`PAUSED_FROZEN_BENCHMARK`).

## Safety

- Isolated under `src/phase30/`
- No holdout / MT5 / Discord / Telegram / OCI / installs / git push
- No AGENT_SHADOW writes; production remains WAIT; champion NO_MODEL
- H13_C thresholds frozen (not tuned)

Research cutoff: `2026-09-29 18:50:00`

## Why not Phase 25 repeats

Each Phase 30 family documents `vs_phase25` in predeclared params.

## Predeclared parameters

```json
{
  "vol_norm_momentum": {
    "family": "A_trend_persistence",
    "ret_bars": 6,
    "vol_bars": 24,
    "ema_fast": 8,
    "ema_slow": 21,
    "accel_lookback": 3,
    "entry_z": 1.0,
    "vs_phase25": "Not EMA pullback; vol-normalized multi-bar return + EMA slope acceleration."
  },
  "compression_expansion": {
    "family": "B_volatility_breakout",
    "range_n": 12,
    "compress_ratio": 0.65,
    "expand_ratio": 1.25,
    "break_atr_frac": 0.25,
    "vs_phase25": "Not Donchian retest; compression\u2192expansion transition + close break of prior range."
  },
  "robust_mad_reversion": {
    "family": "C_standardized_mean_reversion",
    "window": 48,
    "mad_entry": 2.5,
    "atr_pct_min": 0.00025,
    "atr_pct_max": 0.003,
    "vs_phase25": "Median/MAD robust z (not mean/std z+RSI) with different window/threshold."
  },
  "regression_residual_mr": {
    "family": "D_statistical_residual",
    "trend_n": 40,
    "resid_z_n": 40,
    "entry_z": 1.8,
    "vs_phase25": "OLS residual-to-trend MR; Phase25 had no regression residual family."
  },
  "wick_exhaustion": {
    "family": "E_candle_path_structure",
    "seq_n": 3,
    "wick_body_min": 1.5,
    "range_atr_min": 0.4,
    "vs_phase25": "Wick rejection sequences + body imbalance; not SMC FVG/BOS."
  },
  "regime_cond_momentum": {
    "family": "F_vol_regime_conditional",
    "atr_pct_lookback": 96,
    "high_pctile": 0.67,
    "mom_bars": 4,
    "mom_atr_min": 0.35,
    "vs_phase25": "Past ATR-percentile regime gate then momentum; not Phase25 regime_router EMA/MR switch."
  },
  "london_open_imbalance": {
    "family": "G_time_session",
    "utc_hour_start": 7,
    "utc_hour_end": 10,
    "imb_bars": 6,
    "imb_min": 0.55,
    "vs_phase25": "London UTC imbalance (not NY SELL / Phase4-5). Independently fold-checked."
  },
  "m15_trend_m5_trigger": {
    "family": "H_multi_timeframe",
    "m15_ema": 8,
    "m5_pullback_atr": 0.3,
    "m5_confirm_bars": 2,
    "vs_phase25": "M15 constructed from closed M5 + M5 trigger; not Phase25 H1+RSI mtf_h1_m5."
  },
  "body_persistence": {
    "family": "I_path_aware_entry",
    "persist_n": 4,
    "body_range_min": 0.45,
    "vs_phase25": "Executable multi-bar body persistence; not optimized on future MFE/MAE."
  },
  "momentum_structure_ensemble": {
    "family": "J_simple_ensemble",
    "mom_entry_z": 0.85,
    "wick_body_min": 1.2,
    "vs_phase25": "Agreement of vol-norm momentum + wick structure; Phase25 had no ensemble."
  }
}
```

## Preflight

```json
{
  "recipe": "phase30_multi_strategy_discovery_v1",
  "research_cutoff_utc": "2026-09-29 18:50:00",
  "n_oos_timestamps": 18234,
  "fold_counts": {
    "WF1": 6078,
    "WF2": 6078,
    "WF3": 6078
  },
  "n_strategies": 10,
  "strategy_ids": [
    "vol_norm_momentum",
    "compression_expansion",
    "robust_mad_reversion",
    "regression_residual_mr",
    "wick_exhaustion",
    "regime_cond_momentum",
    "london_open_imbalance",
    "m15_trend_m5_trigger",
    "body_persistence",
    "momentum_structure_ensemble"
  ],
  "safety_all_pass": true,
  "start_utc": "2026-11-10T09:54:09Z"
}
```

## Safety snapshot

```json
{
  "checks": {
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
    "agent_shadow_writes": true,
    "production_final_action_wait": true,
    "champion_no_model": true,
    "protected_hashes_intact": true,
    "cutoff_is_2026_09_29_1850": true,
    "all_pass": true
  },
  "protected_hashes": {
    "all_ok": true,
    "files": {
      "src/phase16a/constants.py": {
        "ok": true,
        "expected": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
        "actual": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926"
      },
      "src/phase16a/predictor.py": {
        "ok": true,
        "expected": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
        "actual": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d"
      },
      "src/phase18/outcomes.py": {
        "ok": true,
        "expected": "b4bbfc481606d33a3d5f2cd25422adbb45d5fa68e891b1cdfeac542099d64464",
        "actual": "b4bbfc481606d33a3d5f2cd25422adbb45d5fa68e891b1cdfeac542099d64464"
      },
      "src/phase18/barrier.py": {
        "ok": true,
        "expected": "4db1972b52a47f3b8ef510d62ac1e6fca5763950ca190457271ff275c548f06d",
        "actual": "4db1972b52a47f3b8ef510d62ac1e6fca5763950ca190457271ff275c548f06d"
      },
      "src/phase18/experience.py": {
        "ok": true,
        "expected": "eab2109d62ec3dd36615395cc70ab39fa9c0bf8b1eb9e055e22b7f103200335c",
        "actual": "eab2109d62ec3dd36615395cc70ab39fa9c0bf8b1eb9e055e22b7f103200335c"
      },
      "src/phase18/store.py": {
        "ok": true,
        "expected": "079458f58df8fef99f827ae00fbc5639e10735fe8d32714711492351813e0416",
        "actual": "079458f58df8fef99f827ae00fbc5639e10735fe8d32714711492351813e0416"
      },
      "src/phase20/loop.py": {
        "ok": true,
        "expected": "542f4a84c85578c33c68b4a0b7143b2226026aa3da7d6b059f8f4dc9b1d16e0f",
        "actual": "542f4a84c85578c33c68b4a0b7143b2226026aa3da7d6b059f8f4dc9b1d16e0f"
      },
      "src/phase20/constants.py": {
        "ok": true,
        "expected": "13dc30b30ea1d04c80a7fc41da724736e71b64671d0012d26eb3c8efc74460c0",
        "actual": "13dc30b30ea1d04c80a7fc41da724736e71b64671d0012d26eb3c8efc74460c0"
      },
      "src/phase20/messages.py": {
        "ok": true,
        "expected": "58d041566f5a885ae3aa18f8a2f5225f1ac4d5d10bc5e3120036265877525b55",
        "actual": "58d041566f5a885ae3aa18f8a2f5225f1ac4d5d10bc5e3120036265877525b55"
      },
      "src/phase20/candles.py": {
        "ok": true,
        "expected": "03027a4739c1e1651fdf9721518c2acfff581e8ad5683afda2cd2699103e3eda",
        "actual": "03027a4739c1e1651fdf9721518c2acfff581e8ad5683afda2cd2699103e3eda"
      },
      "src/phase21/constants.py": {
        "ok": true,
        "expected": "c12a784fbb80ed2759283c2075e06fecfd9d92c2808d3322aceb086c229f6e40",
        "actual": "c12a784fbb80ed2759283c2075e06fecfd9d92c2808d3322aceb086c229f6e40"
      },
      "src/phase21/analysis.py": {
        "ok": true,
        "expected": "03b9cb8187c1c81684a8b35872790006e142d187db9fbd0dd9786d82580e7c55",
        "actual": "03b9cb8187c1c81684a8b35872790006e142d187db9fbd0dd9786d82580e7c55"
      }
    }
  }
}
```

