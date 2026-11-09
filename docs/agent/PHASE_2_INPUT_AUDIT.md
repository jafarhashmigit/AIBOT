# Phase 2 input audit

Status: completed before model fitting. Research only. Holdout not opened.

## 1. Git / safety

- Branch at start of Phase 2: `cursor/phase2-primary-outcome-modeling` (created from `cursor/phase1-infrastructure`, working tree clean).
- Research cutoff: `2026-09-29 18:50:00` (server clock).
- Last usable decision timestamp: validation end `2026-09-29 17:50:00`.
- `xauusd_m5_test.csv` was not opened (`test_open_attempts = 0`).

## 2. Input files (Phase 1 artifacts, not modified)

| File | Role | Rows | Range | Notes |
|---|---|---|---|---|
| `src/data/m5_side_outcomes.csv` | Per-side hypothetical outcomes | 84,876 (BUY 42,438 + SELL 42,438) | 2026-02-16 12:55 → 2026-09-29 17:50 | Eligible 81,036; ineligible 3,840 |
| `src/data/xauusd_m5_features_utc_corrected.csv` | Decision-time features + corrected UTC columns | 42,450 | 2026-02-16 12:55 → 2026-09-29 18:50 | Includes 12 purge-gap bars after val_end; those are not used as decisions |
| Existing `RF_FEATURES` in `src/train_rf_m5.py` | Historical 30-feature list | — | — | Clock columns replaced by corrected UTC columns (see allowlist) |
| `src/evaluation/` | Walk-forward, purge, metrics, bootstrap, G2 | — | Phase 1 windows | Reused, not copied |
| `docs/agent/DECISION_JOURNAL_SCHEMA.md` | Future journal | — | — | Not implemented this phase |
| `docs/agent/MODEL_REGISTRY_SCHEMA.md` | Registry fields | — | — | Phase 2 entries are experimental only |

No row in either Phase 1 CSV exceeds the cutoff. Outcome `decision_time` never exceeds val_end.

## 3. Side-outcome schema

`decision_time, eligible, incomplete_window, crosses_gap, side, entry_time, entry_fill, stop_price, target_price, exit_time, exit_reason, gross_pnl, costs, net_pnl, initial_risk, net_r`

- Sides: `BUY` and `SELL` as separate rows, same `decision_time`.
- Exit categories in the file: **`TP`, `SL`, `TIME`** (mapped 1:1 to the classification task; source not changed).
- `net_r` = net P&L / initial SL distance, same definition as `backtest_rf_m5` (`R = net / SL`, costs already inside net).
- Eligible BUY = eligible SELL = 40,518 timestamps. Both sides have the same decision-time feature join key.

### 58 gap-crossing backtest discrepancies (unchanged)

Phase 1 documented 58 of 1,518 validation backtest trades that cross a market gap. Labels and this outcome table exclude them. They are **not** used as training targets and were not rewritten.

## 4. Feature availability

Joined modeling table: **81,036** eligible rows, inner join `decision_time = features.time`.

- Features are from the **closed decision bar**.
- Entry is the **next bar open** (`entry_time > decision_time`).
- Outcome fields live only on the outcome table; they are not columns in the UTC feature file.

Corrected UTC columns present: `corrected_hour_utc`, `corrected_weekday_utc`, `corrected_session_*`.

## 5. Targets

| Task | Target | Source | Status |
|---|---|---|---|
| A. Classification | `exit_reason` ∈ {TP, SL, TIME} | side outcomes | Valid |
| B. Regression | `net_r` | side outcomes | Valid (0 missing among eligible) |

## 6. Limitations carried into modeling

- Outcomes for ineligible (gap / incomplete window) rows are empty and are not modeled.
- `stop_price` / `target_price` / `costs` depend on the next-bar fill; they are **not** decision-time features.
- Original `hour_utc` / `session_*` remain in the UTC file for byte-stability but are **not** in the Phase 2 allowlist.
- Phase 1 RF (`rf_m5_baseline.pkl`) is a different task (BUY/SELL/WAIT labels) and is a historical reference only.
