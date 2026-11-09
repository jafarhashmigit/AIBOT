# Phase 5 independent data quality

Audit of `src/data/phase5_independent_m5.csv` only. Gaps were **not** filled. Bars were **not** interpolated. Suspicious rows were **not** dropped. The approved file `src/data/xauusd_m5.csv` was not appended to.

Machine-readable: `reports/phase5/data_quality.json`, `reports/phase5/fetch.json`.

## Source

Existing MetaTrader 5 installation, `XAUUSD` M5, monthly `copy_rates_range` from 2025-06 through 2026-02, then drop any bar at or after the approved-file start `2026-02-16 08:50:00`. No other broker. No external download.

## Coverage

| | |
|---|---|
| Rows | 50,000 |
| Earliest | 2025-06-02 01:30:00 |
| Latest | 2026-02-16 08:45:00 |
| After approved start | none |
| After research cutoff | none |
| Appended to `xauusd_m5.csv` | no |

The earliest stamp matches the Phase 1 probe’s first real window (`2025-06-02 01:30`). The last stamp is the M5 bar immediately before the approved file. The independent sample is therefore **before** the Phase 4 evaluation period.

## Integrity

| Check | Result |
|---|---|
| Duplicate timestamps | 0 |
| Backwards / tied timestamps | 0 |
| Invalid OHLC | 0 |
| Negative tick volume | 0 |
| Prices not on 0.01 point grid | 0 |
| DST unlocalizable | 0 |
| Zero / negative high−low range | 53 (left in place) |
| Gaps > 5 minutes | 219 |
| Gaps > 12 hours | 39 |
| Weekday gaps > 8 hours | 40 |
| Median gap when > 5 min | 65 minutes |

Gaps are the expected gold weekend / daily-break / holiday holes. They were not repaired. Incomplete or gap-crossing 12-bar windows are ineligible under the frozen outcome rule, same as Phase 1–4.

The 53 zero-range bars are valid OHLC dojis (`high == low`). They were not removed.

## Timezone / DST

Naive `time` is treated as Europe/Athens wall clock, then converted to UTC with IANA DST, identical to the Phase 4 corrected clock. America/New_York and Europe/London hours are taken from that UTC instant. DST fold/gap bars that cannot be localized are not used as NY decisions (`dst_unlocalizable = 0` in this file).

## Material-quality decision

`passed: true`. `material_quality_problem: false`.

Coverage is months, not years, and starts at the broker’s available history rather than a multi-year archive. That is a **limitation**, not a reason to fabricate or splice another vendor. It is sufficient to score the frozen NY-SELL rule on an independent period.

## Files written (separate research set)

- `src/data/phase5_independent_m5.csv`
- `src/data/phase5_independent_features.csv`
- `src/data/phase5_independent_sell_outcomes.csv`

Holdout `src/data/xauusd_m5_test.csv` was not opened. `xauusd_m5.csv` SHA-256 unchanged: `ac34d06fdede8a71bfcc2170badb7c04acfad83e5ecb79a928f85276ef5a4760`.
