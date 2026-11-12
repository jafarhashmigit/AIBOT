# Phase 33 — Results

**Recipe:** `phase33_dukascopy_bidask_qualification_v1`  
**Branch:** `cursor/phase33-dukascopy-bidask-qualification`  
**Final verdict:** `SAMPLE_DATA_ONLY`  
**Provider qualification:** `HISTORICAL_DATA_QUALITY_PASS` (not `HISTORICAL_BID_ASK_QUALIFIED`)  
**MT5 parity:** `MT5_PARITY_PENDING`  
**Execution realism:** `ASSUMPTION_BASED`  
**Objective status:** `EXECUTION_REALISM_STILL_UNVERIFIED`

## Sample acquisition

| Item | Value |
|------|-------|
| Instrument | XAUUSD |
| Source | `https://datafeed.dukascopy.com/datafeed` hourly `.bi5` |
| Days | 2026-02-17, 2026-03-10, 2026-05-15, 2026-07-08 |
| Hours UTC | 01, 08, 13, 15, 20 |
| Ticks | 445,108 |
| M5 candles | 240 (gaps omitted, not fabricated) |
| Network probe | Live GET observed (free, no account) |
| Seed fallback | Read-only Phase25 raw when local/network hour missing |

## Data quality

Hard checks passed: no bid>ask, no negative spreads, no after-cutoff ticks, no ordering violations, no fabricated prices. Large gaps are expected (sparse hour sampling).

## Spread distribution (ask − bid)

| Metric | USD | Points ($0.01) |
|--------|-----|----------------|
| Median | ~0.70 | ~70 |
| Mean | ~0.71 | ~71 |
| P95 | ~1.01 | ~101 |
| Frozen floor | 0.15 | 15 |

Almost all sample ticks are **above** the frozen 15-point floor — the floor understates Dukascopy sample median/tail costs. Extra $0.05/side is separate from spread (no double-count in `label_m5`).

## Strategy diagnostic

**Skipped** — 240 M5 candles insufficient to re-price frozen strategy ledgers across the research window.

## MT5 parity

Protocol defined under `reports/phase33/mt5_parity_protocol.json`. Not executed (MT5 connect forbidden). Approved MT5 feature file lacks separate bid/ask OHLC — genuine parity cannot PASS yet.

## Confirmed findings

- Official Historical Data Export page reachable.
- Acquired 445,108 XAUUSD ticks with separate bid/ask.
- Sample passed hard data-quality checks (no fabricate).
- Spread distribution computed from ask−bid.
- MT5 not connected; parity protocol defined only.
- Frozen strategy signals/thresholds not modified.

## Unresolved limitations

- Full-history bid/ask coverage for strategy ledger re-pricing not acquired.
- Genuine MT5 bid/ask parity not measured.
- Intrabar TP/SL ordering remains ambiguous on M5.
- Licensing: personal/research use reviewed; commercial redistribution not cleared.
- Live feed quality not assumed from historical bi5.

## Safety verification

- Holdout accessed: `false`
- Protected artifacts: `INTACT`
- Phase0–32 modified by Phase33: `false`
- MT5 connected: `false`
- Discord sent: `false`
- Broker orders: `0`
- AGENT_SHADOW modified: `false`
- Git commit: `false`
- Git push: `false`
- Production: `WAIT`
- Champion: `NO_MODEL`
- H13_C: `PAUSED_FROZEN_BENCHMARK`

## Runtime

- START_UTC: `2026-11-10T13:11:51Z`
- END_UTC: `2026-11-10T13:14:03Z`
- DURATION: `2.19 min`
