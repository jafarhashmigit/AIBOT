# Phase 24 — MT5 vs Provider Data Parity

**Recipe:** `phase24_provider_arm64_qualification_v1`  
**Overall parity status:** **FAIL**  
**Holdout accessed:** **No**  
**H13_C / frozen thresholds recalibrated:** **No**

## Approved research window

| Field | Value |
|-------|-------|
| MT5 reference | `src/data/xauusd_m5_features_utc_corrected.csv` |
| Research cutoff | `2026-09-29 18:50:00` UTC |
| Holdout file | `xauusd_m5_test.csv` — **not opened** |
| Parity window | `2026-02-16 00:00:00` → `2026-02-17 23:55:00` UTC |

## Comparison executed: AlgoSpecial vs MT5

### Evidence sources

- AlgoSpecial official OHLC preview API sample persisted as  
  `src/phase24/fixtures/algospecial_xauusd_m5_2026-02-16_17.json` (522 M5 rows).  
- MT5 slice for the same calendar window:  
  `src/phase24/fixtures/mt5_reference_xauusd_m5_2026-02-16_17.json` (379 rows; MT5 series starts mid-day 16 Feb).

### Timestamp alignment

- AlgoSpecial docs: **broker server time**, not UTC.  
- Exploratory offsets 0–3h: **offset 0** maximized overlap quality among tested offsets; still failed price gates.  
- Common timestamps (UTC assumption): **343**.  
- Only on MT5 (in window): present; only on provider: present (MT5 starts later on 16 Feb).

### OHLC differences (absolute, common stamps)

| Metric | Approx value |
|--------|----------------|
| Median \|Δclose\| | **~$12.08** |
| Max \|Δclose\| | **~$73.98** |
| Mean \|Δclose\| | **~$18.43** |

**Parity gates (research):** median \< $0.50 and max \< $5.00 → **FAIL**.

### Price precision

- MT5 closes: typically 2 decimal places in sample.  
- AlgoSpecial: up to 3 decimal places.  
- Not the primary failure mode versus dollar-level divergence.

### M5 boundaries

- Common stamps align to `:00` / `:05` minutes under the UTC assumption.

### ATR / feature distribution

- Wilder ATR absolute differences computed on aligned common series (see `reports/phase24/data_parity.json`).  
- Feature fields (`close_to_ema_20`, `ema_9_20_spread`) remain MT5-defined; provider OHLC divergence implies feature distributions **cannot** be assumed transferable.  
- **No threshold recalibration** performed.

### Spread / cost

| Source | Median spread field (window) |
|--------|------------------------------|
| MT5 features `spread` | **4** |
| AlgoSpecial `Spread` | **240** |

Units/scale are incompatible with a naive swap into Phase 18 cost assumptions (`POINT_SIZE=0.01`, spread floor 0.15 USD). Provider data **must not** inherit MT5 cost validity.

## Other providers

No additional measured parity runs (account creation forbidden; paid providers excluded; Dukascopy binary feed not downloaded this phase). Documented as `NOT_RUN` in `data_parity.json`.

## Conclusion

Measured free preview data (**AlgoSpecial**) is **not parity-compatible** with the project MT5 reference on the approved window.  
Therefore provider qualification cannot proceed to cloud runtime on this evidence.

**Provider data does not inherit the validity of MT5-trained H13_C thresholds.**
