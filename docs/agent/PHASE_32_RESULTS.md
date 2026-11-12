# PHASE 32 — Results

Verdict: **EXECUTION_REALISM_UNVERIFIED**
Champion: `NO_MODEL` | H13_C: `PAUSED_FROZEN_BENCHMARK` | Production: `WAIT`

## Feature recomputation

- Match within tol: `True`
- Corrected UTC match: `True`
- Totals: `{"exact_match_count": 2947109, "tol_match_count": 2947109, "mismatch_count": 0, "comparable_cells": 2947109, "mismatch_pct": 0.0}`

## Label reconstruction

- Agrees: `True`
- Target mismatches: `0`
- Side outcome mismatches: `0`
- Gaps full/cutoff: `188` / `160`

## Gross vs net

- `H13_C`: n=226 class=positive_net_not_a_promotion gross_mean_r=0.09142278909989394 net_mean_r=0.04856060840719428
- `vol_norm_momentum`: n=6611 class=positive_gross_fails_after_costs gross_mean_r=0.02209060965979898 net_mean_r=-0.032667297112387264
- `m15_trend_m5_trigger`: n=10031 class=positive_gross_fails_after_costs gross_mean_r=0.0062169302308677996 net_mean_r=-0.0494117107544147
- `robust_mad_reversion`: n=2599 class=fails_even_before_costs gross_mean_r=-0.001302009883391183 net_mean_r=-0.04934843607006664
- `body_persistence`: n=152 class=positive_gross_fails_after_costs gross_mean_r=0.05089593498450774 net_mean_r=-0.0024864336014797446

## Execution realism

`ASSUMPTION_BASED`

## Provider

Dukascopy: `NOT_YET_QUALIFIED`

## Runtime

```json
{
  "START_UTC": "2026-11-10T12:53:01Z",
  "END_UTC": "2026-11-10T12:53:23Z",
  "DURATION_SECONDS": 21.4051194190979,
  "DURATION": "0.36 min"
}
```

## Safety

```json
{
  "production": "WAIT",
  "champion": "NO_MODEL",
  "h13c": "PAUSED_FROZEN_BENCHMARK",
  "broker_orders": 0,
  "mt5_connected": false,
  "discord_sent": false,
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

