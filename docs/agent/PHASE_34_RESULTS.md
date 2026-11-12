# Phase 34 — Results

**Final verdict:** `PARTIAL_HISTORICAL_BID_ASK_QUALITY`
**Complete trading days:** `6` / `20`
**Ticks:** `3339545`
**Spread median / mean / P95 USD:** `0.7270000000007713` / `0.7365352798060835` / `1.006999999999607`
**vs Phase 33:** `PHASE33_SAMPLE_APPEARS_REPRESENTATIVE`
**MT5 parity:** `MT5_PARITY_PENDING`
**License:** `RESEARCH_PERSONAL_USE_REVIEWED_COMMERCIAL_NOT_CLEARED`
**Production:** `WAIT` | **Champion:** `NO_MODEL`

## Coverage

- Complete: `2026-02-17`, `2026-03-06`, `2026-03-10`, `2026-05-15`, `2026-07-08`, `2026-09-15`
- Incomplete/not fully acquired: `2026-02-16`, `2026-02-26`, `2026-03-09`, `2026-03-11`, `2026-03-23`, `2026-03-27`, `2026-03-30`, `2026-04-03`, `2026-04-15`, `2026-04-28`, `2026-05-08`, `2026-05-21`, `2026-06-02`, `2026-09-28`
- Note: Selected 20 trading days; network 503/timeouts prevented full completion. Exact achieved coverage reported; dates not substituted.

## Runtime

- START_UTC: `2026-11-10T13:41:02Z`
- END_UTC: `2026-11-10T20:17:41Z`
- DURATION: `53.10 min`

## Offline re-run

```powershell
$env:PYTHONPATH='src'
python -m phase34.analyze_offline
```

