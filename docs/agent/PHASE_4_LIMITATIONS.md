# Phase 4 limitations

Finding class: exploratory. Status: **not** production-ready or live-ready.

## Safety

- Holdout not opened.
- Max timestamp 2026-09-29 17:50. Cutoff not exceeded.
- Phase 1–3 files unchanged. No downloads. No package changes. No MT5 orders.

## Spec truncation

The Phase 4 prompt ended at safety rule 16. Implementation followed the stated objective, standing AIBOT rules, and a catalogue frozen in `src/phase4/constants.py` before outer scoring. If a later full spec adds required tests, those tests have not been run.

## Incomplete tests

- Phase 1 permutation A remains **`not_run`**.
- No second-year or holdout confirmation of NY SELL.
- Spread stress is the Phase 3 floor approximation, not a fill re-simulation.
- Session × hour × weekday interactions were **not** tested (unrestricted search).

## Why NY SELL is unconfirmed

- 38 tests. BH-FDR did not pass this slice.
- Day-cluster CI includes 0 (49 outer days).
- Mean +0.036R is below the G2 pooled bar of +0.05R.
- Outer window is ~10 weeks × 2 folds in summer/autumn 2026 only.
- Always-SELL in NY is not a decision engine; E1 in the same session is weaker.

## Coverage

Approved modeling data start 2026-02-16. Broker history to 2025-06-02 exists in the Phase 1 probe and was not appended. Gold has strong seasonality; this sample cannot separate “NY SELL works” from “this summer’s path.”

## Multiple testing

Six slices had a positive pooled mean. Only one had both folds positive. Reporting that one as confirmed would be selection bias. The predeclared gate exists to prevent that.

## What was not built

No new classifier, no live signals, no cost-rule rewrite, no holdout peek.
