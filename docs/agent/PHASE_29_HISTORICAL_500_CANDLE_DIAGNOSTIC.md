# PHASE 29 — Historical 500-Candle Diagnostic

**HISTORICAL_DIAGNOSTIC_ONLY**
**NOT_FORWARD_VALIDATION**

Do **not** claim a trading edge from this diagnostic alone.

## Window

- First candle UTC: `2026-09-25 21:15:00`
- Last candle UTC: `2026-09-29 18:50:00`
- Candles: **500**
- Research cutoff UTC: `2026-09-29 18:50:00`
- Excluded post-cutoff rows: 0
- Holdout accessed: **False**

## Baseline H13_C counts

- BUY: 1
- SELL: 5
- WAIT: 494
- Signal rate: 0.012000

## Outcome horizons (frozen Phase 18)

- Horizons: H1, H2, H3, H6, H12
- H12 matured: 5
- H12 by status: {'PASS': 1, 'FAIL': 3, 'TIMEOUT': 1, 'PENDING': 1, 'other': 0}

## H12 performance (baseline)

- Combined n=5 mean_r=-0.31032184799999996 median_r=-1.0 win_rate=0.2 PF=0.4915439304411072 maxDD=-2.0
- BUY n=0 mean_r=None win_rate=None PF=None
- SELL n=5 mean_r=-0.31032184799999996 win_rate=0.2 PF=0.4915439304411072

## High-only research (separate)

- Enabled: True
- BUY/SELL/WAIT: {'BUY': 0, 'SELL': 1, 'WAIT': 499, 'n': 500}
- Combined H12: {'n': 1, 'mean_r': 1.5, 'median_r': 1.5, 'win_rate': 1.0, 'profit_factor': 'inf', 'max_drawdown_r': 0.0}
- Not promoted.

## Comparison vs Phase 28 forward (separate evidence)

- Phase28 forward: 100 candles / 0 BUY / 0 SELL / 100 WAIT / INSUFFICIENT_FORWARD_EVIDENCE
- Historical diagnostic: 1 BUY / 5 SELL / 494 WAIT
- Not mixed into one performance number.

## Verdict channels

- `HISTORICAL_DIAGNOSTIC_RESULT`: see metrics above (not an edge claim)
- `FORWARD_EVIDENCE`: Phase 28 = 100 candles / 0 BUY / 0 SELL / INSUFFICIENT (not mixed)
- `PRODUCTION_STATUS`: WAIT

## Safety

- Discord: not sent
- Broker orders: 0
- AGENT_SHADOW written: false
- Experience source: HISTORICAL_HYPOTHETICAL

