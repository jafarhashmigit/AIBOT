# Phase 33 — Research Plan

**Recipe:** `phase33_dukascopy_bidask_qualification_v1`

## Objective

Qualify whether Dukascopy can provide a free, complete, technically compatible
historical XAUUSD bid/ask feed for independent execution validation.
Provider qualification only — not strategy development.

## Safety

- Cutoff: `2026-09-29 18:50:00`
- No holdout, no MT5 connect, no Discord/Telegram/OCI, no broker orders,
  no package installs, no AGENT_SHADOW writes, no commit/push.
- Isolated under `src/phase33/`.

## Stages

1. `preflight`
2. `provider_docs`
3. `sample_acquisition`
4. `raw_data_validation`
5. `candle_builder`
6. `timestamp_validation`
7. `spread_analysis`
8. `mt5_parity_protocol`
9. `execution_comparison`
10. `strategy_diagnostics`
11. `qualification`
12. `final_verdict`

## Download policy

Bounded diagnostic sample only (selected days × session hours), stdlib HTTP GET
of public `datafeed.dukascopy.com` bi5 archives if freely reachable.

## Qualification gates

DOCUMENTATION_ONLY → SAMPLE_DATA_ACQUIRED → HISTORICAL_DATA_QUALITY_PASS →
HISTORICAL_BID_ASK_QUALIFIED; MT5 parity is a separate pending gate.

