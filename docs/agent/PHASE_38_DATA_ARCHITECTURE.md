# Phase 38 — Data Architecture

## Layout

- `src/data/phase38/mt5/raw/m5/` — immutable raw M5 chunks
- `src/data/phase38/mt5/raw/ticks/` — immutable raw tick chunks
- `src/data/phase38/mt5/canonical/` — canonical copies (separate from raw)
- `src/data/phase38/manifests/` — retrieval manifests + SHA-256
- `src/data/phase38/rejected/` — rejected records with reasons
- `src/data/phase38/state/acquisition_state.json` — resumable state

## Source limitations

- Server: MetaQuotes-Demo — **not** live broker execution truth.
- Spreads describe demo feed only.
- Liquid-hour tick samples ≠ full-day coverage.

## UTC

All internal timestamps are UTC-aware via `datetime.fromtimestamp(..., tz=UTC)`.
Windows/Pakistan local time is never used for storage.

## Resume

```
PYTHONPATH=src python -m phase38.run_phase38
```

Completed chunks are skipped; checksums verified before reuse.

