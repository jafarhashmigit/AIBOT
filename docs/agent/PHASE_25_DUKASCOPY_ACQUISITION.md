# Phase 25 — Dukascopy Historical Acquisition

**Recipe:** `phase25_dukascopy_mt5_parity_v1`  
**Branch:** `cursor/phase25-dukascopy-mt5-parity`

## Source

| Item | Detail |
|------|--------|
| Endpoint | `https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM0}/{DD}/{HH}h_ticks.bi5` |
| Month indexing | **Zero-based** in URL (`00`=January) |
| Format | LZMA-compressed `.bi5`; 20-byte big-endian ticks `(ms, ask, bid, ask_vol, bid_vol)` |
| XAUUSD scale | Prices ÷ **1000** |
| Time | Milliseconds from hour start → reconstructed **UTC** |
| Bid/Ask | Both present per tick |
| Empty hours | HTTP 200 + **empty body** (weekend / daily break) — not fabricated |

Implementation: `src/phase25/download.py` (Python **stdlib** only: `urllib`, `lzma`, `struct`). No new packages installed.

## Storage separation

| Path | Contents |
|------|----------|
| `src/data/phase25/dukascopy_raw/` | Raw `.bi5`, manifests, decoded tick JSONL |
| `src/data/phase25/dukascopy_m5/` | Built M5 JSONL (bid/ask/mid) |
| MT5 reference | Unchanged `src/data/xauusd_m5_features_utc_corrected.csv` |

## Integrity

- SHA256 recorded per non-empty hour file in day `manifest.json`
- Resume-safe (existing hours not re-fetched)
- Research cutoff enforced: no timestamps after `2026-09-29 18:50:00` UTC
- Holdout never accessed

## Licensing / usage (research note)

Public historical feed used for **offline parity research** only. JForex/website terms emphasize **personal, non-commercial** use and restrict redistribution / database construction / scraping-style acquisition. **Cloud commercial clearance is not established.**

## Parity days (approved window)

`2026-02-17`, `2026-03-10` (all before research cutoff; Asia/London/NY hours covered).

| Day | Ticks | OK hours | Empty hours |
|-----|-------|----------|-------------|
| 2026-02-17 | 324,507 | 23 | 1 (daily break) |
| 2026-03-10 | 313,745 | 23 | 1 |

Raw data under `src/data/phase25/dukascopy_raw/` (SHA256 per non-empty hour in manifests).

## M5 construction

Ticks → M5 OHLC for sides `mid`, `bid`, `ask`. **Gaps omitted** (never invented).
