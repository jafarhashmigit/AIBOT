# Phase 25 — Dukascopy vs MT5 Historical Parity

**Recipe:** `phase25_dukascopy_mt5_parity_v1`  
**Historical status:** **`DUKASCOPY_HISTORICAL_FAIL`**

## Frozen tolerances (declared before evaluation)

| Gate | Limit |
|------|-------|
| Coverage of MT5 timestamps | ≥ 0.95 |
| Median \|Δclose\| | ≤ $0.50 |
| p95 \|Δclose\| | ≤ $2.00 |
| Max \|Δclose\| | ≤ $5.00 |
| Median \|ΔATR14\| | ≤ $0.50 |
| H13_C action agreement (shared MT5 H1) | ≥ 0.99 |
| Primary price side | `mid` = (bid+ask)/2 |

Tolerances were **not** loosened after seeing results.

## Method

1. Download Dukascopy XAUUSD ticks for approved days (before `2026-09-29 18:50`).  
2. Build M5 OHLC (mid/bid/ask); omit gaps (no fabrication).  
3. Compare to MT5 feature CSV OHLC on exact timestamps.  
4. Recompute OHLC-derived features; compare ATR14 and feature diffs.  
5. Run `decide_h13c` with frozen WF3 cuts; features from each M5 series; **shared MT5 H1** context.  
6. Include Phase 24 AlgoSpecial failure as reference.

Holdout: **not accessed**. Thresholds: **not recalibrated**.

## Results (primary side = mid)

| Day | Coverage | Median \|Δclose\| | p95 | Max | H13_C agree | Day pass |
|-----|----------|-------------------|-----|-----|-------------|----------|
| 2026-02-17 | 0.957 | **$12.29** | $62.49 | $73.82 | 0.963 | FAIL |
| 2026-03-10 | 0.955 | **$13.81** | $40.22 | $55.18 | 0.979 | FAIL |

Aggregate: min coverage 0.955; median-of-daily-median \|Δclose\| **$12.29**; max-of-daily-max **$73.82**.

### Phase 24 AlgoSpecial reference

Still **FAIL** (median \|Δclose\| ≈ $12.08, max ≈ $74) — same order of magnitude as Dukascopy vs this project's MT5 feed.

## Limitations

- MT5 `spread` column is broker **points**; Dukascopy spread is **ask−bid price** — not interchangeable.  
- Feature CSV has 75 columns; OHLC-recomputable subset compared explicitly.  
- Price-level mismatch (~$12 median) means MT5-trained H13_C thresholds **must not** be assumed valid on Dukascopy OHLC.  
- Licensing may still block cloud commercial use even if prices had matched.

## Exact artifacts

`reports/phase25/historical_parity.json`
