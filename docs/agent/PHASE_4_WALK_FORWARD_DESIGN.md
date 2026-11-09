# Phase 4 walk-forward design

Declared before scoring. Same nested chronology as Phase 3. No random splits. No holdout.

## Outer evaluation

| Nested fold | Inner (cuts / calibration) | Outer (scored once) |
|---|---|---|
| N1 | Phase 2 WF1 OOS, purged 12 bars | WF2: 2026-07-23 11:25 → 2026-08-26 13:55 (`< stop`) |
| N2 | WF1+WF2, purged 12 bars | WF3: 2026-08-26 13:55 → 2026-09-29 17:50 (inclusive) |

Session, hour, weekday, and EMA-sign labels are decision-time and need no inner fit.

ATR% tercile cuts are estimated on the **inner** window only and applied to that fold’s outer rows.

## Predeclared confirmatory family

Unconditional: take BUY or SELL on every timestamp in the slice (costs already in `net_r`).

Families:

- session: off_hours, asia, london, london_ny_overlap, new_york
- hour_bucket (corrected UTC): 00–07, 08–12, 13–16, 17–23
- weekday: Mon–Fri
- atr_tercile: low / mid / high (inner cuts)
- trend: ema_9_20_spread > 0 vs ≤ 0

2 sides × those levels. No extra slices after seeing results.

## Gate (frozen)

A slice is a potentially credible conditional edge only if:

- it was in the catalogue above
- pooled n ≥ 100 and each outer fold n ≥ 50
- mean R > 0 after costs in **both** outer folds
- day-cluster 95% CI lower bound > 0 (2,000 draws, seed 42)
- it survives BH-FDR at q = 0.10 among tested slices with n ≥ 50
- mean R at 1.5× spread-floor stress is still > 0

E1-by-session is a diagnostic of the Phase 2 rule, not a member of this family.

## Multiple testing

Unrestricted subgroup search is forbidden. The family size is the catalogue, not every conceivable interaction (session × hour × weekday × vol is not tested).
