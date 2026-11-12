# PHASE 31 — Results

Verdict: **NO_CONFIRMED_IMPLEMENTATION_DEFECT**
Champion: `NO_MODEL` | H13_C: `PAUSED_FROZEN_BENCHMARK` | Production: `WAIT`

## Biggest root cause

```json
{
  "id": "PRECOST_NEGATIVE_robust_mad_reversion",
  "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
  "severity": "high",
  "evidence": {
    "approx_pre_cost_mean_r": -0.001302009883391179,
    "baseline_1x_mean_r": -0.04934843607006664
  },
  "affected_phases": [
    "30"
  ],
  "affected_strategies": [
    "robust_mad_reversion"
  ],
  "changes_previous_conclusions": false
}
```

## Answers

1. M5 internally valid? `True`
2. UTC/DST conversion? see `data_integrity.timezone` (Athens→UTC methodology re-checked).
3. Features causal? `True`
4. Labels reconstruct? `True`
5. TP/SL same-candle? `True`
6. Gaps handled? label contract excludes gap windows; gap count in data audit.
7. Costs once? `True`
8. Execution realism enough? `False`
9. BUY vs SELL? see buy_sell_diagnostics (typically both weak).
10. Least-poor horizon? `H6`
11. Directional prediction > chance? compare accuracy vs majority in prediction_diagnostics.
12. Predictive value failing at execution? see pred_r correlation vs mean net R.
13. Bootstrap reliability? day-cluster preferred; IID may understate dependence.
14. Phase30 permutation appropriate? sign-randomization has limited timing interpretation.
15. Multiple-testing sufficient? log(n) penalty is heuristic, not Holm/BH.
16. Negative before costs? see cost_sensitivity.recomputed.*.negative_even_before_approx_cost_addback
17. Prior conclusions invalidated? `False`
18. Biggest root cause: `PRECOST_NEGATIVE_robust_mad_reversion`
19. Missing evidence: historical bid/ask; tick-level MFE/MAE; independent full feature recompute.
20. Next phase: either execution-realism data collection OR new authorized research with revised stats — not H13_C tuning.

## Runtime

```json
{
  "START_UTC": "2026-11-10T12:40:23Z",
  "END_UTC": "2026-11-10T12:40:50Z",
  "DURATION_SECONDS": 27.124500036239624,
  "DURATION": "0.45 min"
}
```

## Safety

```json
{
  "production": "WAIT",
  "champion": "NO_MODEL",
  "h13c": "PAUSED_FROZEN_BENCHMARK",
  "broker_orders": 0,
  "mt5_connections": 0,
  "discord_sent": 0,
  "telegram_sent": 0,
  "holdout_accessed": false,
  "holdout_file_exists": true,
  "agent_shadow_writes": 0,
  "packages_installed": false,
  "github_push": false,
  "protected_artifacts_intact": true,
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
  },
  "research_cutoff_utc": "2026-09-29 18:50:00",
  "cutoff_ok": true
}
```

