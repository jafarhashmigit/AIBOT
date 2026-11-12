# Phase 34 — Research Plan

**Recipe:** `phase34_extended_bidask_validation_v1`

Extend Dukascopy XAUUSD bid/ask history (up to 20 trading days) and validate
spread / execution-cost characteristics. No strategy evaluation.

## Selected days

`2026-02-16`, `2026-02-17`, `2026-02-26`, `2026-03-06`, `2026-03-09`, `2026-03-10`, `2026-03-11`, `2026-03-23`, `2026-03-27`, `2026-03-30`, `2026-04-03`, `2026-04-15`, `2026-04-28`, `2026-05-08`, `2026-05-15`, `2026-05-21`, `2026-06-02`, `2026-07-08`, `2026-09-15`, `2026-09-28`

## Offline analysis (no download)

```powershell
$env:PYTHONPATH='src'
python -m phase34.analyze_offline
```

