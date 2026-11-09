# Phase 2 feature leakage report

Machine-readable twin: `reports/phase2/feature_audit.json`.

## Allowlist (30 columns)

Scale-free trend, RSI/BB, ATR%, realized vol, candle shape, lagged returns, tick volume, `minutes_since_prev_bar`, and **corrected** UTC hour / weekday / session flags.

Explicitly **excluded**:

- All outcome columns (`exit_*`, fills, P&L, `net_r`, eligibility flags).
- Next-bar `entry_fill`, `stop_price`, `target_price`, `costs` (not known at decision time).
- Raw OHLC, `time`, `time_utc`.
- Original `hour_utc`, `weekday`, `session_*`, `session_id` (Athens clock mislabeled as UTC).
- `corrected_time_utc` string and `corrected_session_id` (redundant with the four session flags).

If a column’s availability at the decision bar could not be established, it is not in the allowlist.

## Checks (all passed before fitting)

1. Allowlist is explicit (not “every numeric column”).
2. No outcome field is in the allowlist.
3. Features join on `decision_time = features.time` (many_to_one).
4. No duplicate `(decision_time, side)`.
5. Every timestamp has both BUY and SELL.
6. No missing or infinite allowlist values on the modeling table.
7. `entry_time` is strictly after `decision_time` (next-bar entry).
8. Corrected UTC columns are used; broken clock columns are not.
9. Max decision time = val_end; cutoff not exceeded.
10. Holdout file not opened.

## Remaining structural overlap (not leakage of future prices)

M5 labels use a 12-bar window, so nearby **training** labels overlap each other. That is why a 12-bar **purge** is applied at each eval boundary. Adjacent training rows are still overlapping; block bootstrap is used later rather than treating bars as iid.
