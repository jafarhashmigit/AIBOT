# Phase 5 input audit

Recorded before independent history fetch. Research only. Holdout not opened.

## Git

- Branch: `cursor/phase5-ny-sell-replication` (from `cursor/phase4-regime-edge-investigation`)
- Working tree: untracked Phase 2–4 source/docs only; no tracked Phase 1 files modified
- Nothing pushed

## Frozen hashes at Phase 5 start

| Artifact | SHA-256 |
|---|---|
| `src/data/phase2_oos_predictions.csv` | `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f` (unchanged from Phase 2/3/4) |
| `src/data/phase3_decision_journal.csv` (prefix) | `b8cc1da7cc5918d9` |
| `reports/phase4/regime_results.json` (prefix) | `c8565408b35f66c7` |
| `src/phase4/run_phase4.py` (prefix) | `cf22e164e90c365f` |
| `src/phase4/constants.py` (prefix) | `4880f03f76f4f93e` |
| `src/phase3/run_phase3.py` (prefix) | `a237fd43b930a506` |

Phase 1–4 scripts, labels, splits, models, and reports will not be overwritten. New outputs go under `src/phase5/`, `docs/agent/PHASE_5_*.md`, `reports/phase5/`, and `src/data/phase5_independent_*.csv`.

## Holdout

`src/data/xauusd_m5_test.csv` exists and is not opened. Guard target: `test_open_attempts = 0`.

## Phase 4 finding being replicated (not re-estimated here)

NY exclusive session + SELL, Phase 4 outer OOS: n=1,710, mean R ≈ +0.036, both WF folds positive, PF ≈ 1.09, 1.5× stress positive, day-cluster CI ≈ [−0.088, +0.160], FDR fail, gate fail. Status: PROMISING BUT UNCONFIRMED.

## What this phase will not read for scoring

- Final holdout
- Any price after `2026-09-29 18:50:00`
- Phase 4 outer timestamps as part of the independent test
- Approved `xauusd_m5.csv` as a source of independent bars (not appended; not used to complete independent windows)
