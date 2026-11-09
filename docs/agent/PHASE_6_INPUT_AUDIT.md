# Phase 6 input audit

Recorded **before** Phase 6 code was written. Architecture and protocol only. Holdout not opened. Phase 1–5 files not modified.

## Git

- Branch: `cursor/phase6-agent-architecture` (from `cursor/phase5-ny-sell-replication`)
- Working tree at audit: untracked Phase 2–5 source/docs only; no tracked Phase 1 files modified
- Nothing pushed

## Frozen hashes at Phase 6 start

| Artifact | SHA-256 |
|---|---|
| `src/data/xauusd_m5.csv` | `ac34d06fdede8a71bfcc2170badb7c04acfad83e5ecb79a928f85276ef5a4760` |
| `src/data/phase2_oos_predictions.csv` | `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f` |
| `src/data/phase3_decision_journal.csv` | `b8cc1da7cc5918d9fd17131c67913aad183f58098b2671d04c7cc1b024d5324a` |
| `reports/phase4/regime_results.json` | `c8565408b35f66c799c8183b6d39fa3ee0f9943c3e2144982e0dc2a8dc6efe55` |
| `reports/phase5/replication_results.json` | `39b74769bc63de7ec5c6b74d356aaca66f5d108cff24d8918998607741d05785` |
| `src/phase4/run_phase4.py` | `cf22e164e90c365f3e2968009b516d7103515db8f55eda339bad71d91bff8542` |
| `src/phase4/constants.py` | `4880f03f76f4f93e9fa78f66e9a2fa189e6d39290b1efd568f0109362d4778b2` |
| `src/phase3/run_phase3.py` | `a237fd43b930a506f4b743ad9976627e300bf257eb23a337a6d7dd73c941fff0` |
| `src/phase5/run_phase5.py` | `f3281a0e8e7d90624d39625b46341b3e2b6d79bc4053d09f8c24b91e8c6d65ac` |
| `src/features_m5.py` | `b97a3ae579a72128d2a83ec6988f084b96a233b5bb698096b26c0a83d5212ccd` |
| `src/label_m5.py` | `72e5b6c525999fde30f9514dc7c1e0b8e825006bba173547adea9e2b64be81d2` |

## Holdout

`src/data/xauusd_m5_test.csv` exists and is not opened. Guard target: `test_open_attempts = 0`.

Maximum market timestamp accessed for Phase 6 work: **none**. This phase does not parse price files.

## What Phases 0–5 established (read-only)

| Phase | Result used as architecture input |
|---|---|
| 0 | Agent loop A–J designed; WAIT default; no live trading |
| 1 | Cost-aware labels, holdout guards, evaluation module; RF baseline not an economic edge |
| 2 | Side-outcome RF beats class prior on OOS classification; mean OOS net R ≈ −0.057; no economic edge |
| 3 | Frozen conservative EV → Always WAIT on outer OOS (12,156 WAIT). No credible economic edge |
| 4 | NY exclusive session + SELL was PROMISING BUT UNCONFIRMED (CI includes 0, FDR fail) |
| 5 | That frozen NY-SELL hypothesis is **NOT REPLICATED**. Do not revive it |

Current champion per `ACCEPTANCE_CRITERIA.md` section 8: **`no_model` (WAIT-only)**.

## What Phase 6 will not do

- Open the holdout or any bar after `2026-09-29 18:50:00`
- Modify Phase 1–5 datasets, labels, splits, models, or reports
- Retrain a production model
- Mine features or subgroups
- Optimize a BUY/SELL rule
- Mark any model `PRODUCTION`
- Place MT5 orders
