# Phase 3 limitations

Finding class: exploratory. All decision-layer artifacts: **experimental**. None are production-ready or live-ready.

## Safety (verified)

- Holdout `xauusd_m5_test.csv` was not opened (`test_open_attempts = 0`).
- CSV reads: `phase2_oos_predictions.csv` only.
- Max accessed timestamp: 2026-09-29 17:50. Cutoff 18:50 not exceeded.
- Phase 2 OOS SHA-256 unchanged. Phase 2 source/doc hashes unchanged.
- No packages installed or upgraded.
- No MT5 orders, no live signals, no broker connection.

## Incomplete tests (do not treat as passes)

- **Phase 1 permutation A** (200 RF retrains) remains **`not_run`**. Phase 3 did not complete it and does not claim it passed.
- Spread-stress for the frozen policy is not informative (zero trades). It was still executed; extra USD is undefined on an empty trade list.
- Threshold perturbation around the frozen tau is not applicable (policy is Always WAIT).
- Inner class-conditional means and the inner threshold share the same inner window (no inner holdout). Outer evaluation remains the honest test.

## Nested-split limitation

Only two outer folds exist. WF1 cannot be outer-evaluated without using future OOS rows for calibration. Two blocks cannot demonstrate “majority of many folds.”

## Conservative EV is severe

Inner MAE of the probability-weighted EV mapping is ≈ 1.17R, almost the scale of a full stop. Subtracting 1.0×MAE pushes conservative EV below zero on essentially every timestamp. The frozen policy therefore WAITs. A looser penalty would be a **different** predeclared policy; it was not substituted after seeing that WAIT was selected.

## Inner-positive rules that failed outer

META_RIDGE looked strong on inner data (+0.12R) and lost or mixed on outer. C_EV_THRESHOLD was weakly positive in mean R on outer but **negative in USD**, with WF2 negative and a CI that includes 0. These are documented comparisons, not a reason to unfreeze `P3_CONSERVATIVE_EV`.

## Labels still overlap

Adjacent M5 decisions share 12-bar outcome windows. Day-cluster bootstrap (block = calendar day, seed 42, 2,000 draws) is used instead of treating bars as iid. 49 outer days is a modest cluster count.

## BUY/SELL asymmetry

Where policies traded (E1, B, C, META), SELL dominated. That concentration is inherited from Phase 2 predicted-R sign and is reported, not tuned away.

## Pandas DLL block

Windows Application Control blocked `pandas` DLLs in this session. Phase 3 ran with **numpy + sklearn** from the existing approved venv. No packages were installed. Bootstrap and metrics were reimplemented to match the Phase 1 day-cluster / profit-factor / max-drawdown definitions. This is an environment limitation, not a data-boundary failure.

## What was not built (on purpose)

- Live or paper signal generation
- MT5 execution
- Reinforcement learning or online learning
- Autonomous retraining
- Production deployment
- A second meta-model pass on outer outcomes

Those require explicit approval after this STOP.
