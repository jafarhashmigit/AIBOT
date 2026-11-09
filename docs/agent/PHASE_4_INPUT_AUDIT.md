# Phase 4 input audit

Status: completed before regime scoring. Research only. Holdout not opened.

The Phase 4 request arrived truncated after safety rule 16. This phase still follows the stated objective, the standing AIBOT safety rules from Phases 0–3, and the finite predeclared catalogue in `src/phase4/constants.py`. No new trading model is trained.

## 1. Git / safety

- Branch: `cursor/phase4-regime-edge-investigation` (from `cursor/phase3-decision-layer`).
- Phase 1/2/3 scripts, datasets, labels, splits, models, and reports are not modified.
- Holdout `xauusd_m5_test.csv` is not opened.
- Cutoff: `2026-09-29 18:50:00`. Last decision used: `2026-09-29 17:50:00`.
- No downloads. No package changes. Nothing pushed.

## 2. Inputs (read-only)

| File | Use |
|---|---|
| `src/data/phase2_oos_predictions.csv` | Genuine OOS primary predictions + actual outcomes for scoring |
| `src/data/xauusd_m5_features_utc_corrected.csv` | Decision-time session/hour/ATR/trend columns through val_end only |
| `reports/phase1/m5_history_depth_probe.json` | Existing coverage probe (no new MT5 pull) |
| `reports/phase1/side_outcomes_verification.json` | Ineligible / 58 gap-crossing counts |
| Phase 2/3 docs | Inherited limitations |

OOS SHA-256 must remain `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f`.

## 3. What is not an input

- Holdout CSV
- Any bar after the cutoff
- Future outcomes as features
- New labels or resplit data
- Phase 3 meta-model actions as a new search surface (E1-by-session is a diagnostic only)

## 4. Confirmatory question

On outer OOS timestamps (Phase 2 WF2+WF3), does any **predeclared** regime × side slice have a stable, cost-aware mean net R that survives both folds, a day-cluster CI above 0, BH-FDR, and 1.5× spread stress?

If not, the correct result is that Phases 1–3 did not hide a usable conditional edge in this catalogue.
