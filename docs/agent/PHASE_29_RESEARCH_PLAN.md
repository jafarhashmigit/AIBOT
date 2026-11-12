# PHASE 29 — Forward Shadow Continuation (Research Plan)

## Objective

Continue genuine forward XAUUSD M5 shadow observation after Phase 28’s 100-candle / 0-signal batch, until enough real BUY/SELL decisions and matured outcomes exist for evaluation — without changing H13_C, high-only research policy, or production gates.

## Frozen posture (unchanged)

- Champion: `NO_MODEL`
- H13_C: `EXPERIMENTAL`
- Production action: `WAIT`
- Phase 14 q25/q75 cuts frozen
- Phase 27 high-only = research observer only
- MT5 read-only; Discord notification-only; no broker orders

## Forward rule

Freeze `forward_observation_start_utc` at first live session start. Persist across restarts. Ignore any candle with close ≤ watermark. Never replay history as forward.

## Observers

1. `H13C_BASELINE` — frozen Phase 14 H13_C
2. `H13C_HIGH_VOL_RESEARCH` — frozen Phase 27 high-only (separate journal; never alters production)

## Discord

Concise BUY / SELL / WAIT templates with UTC|PKT clocks. WAIT Discord off by default. Idempotent ledger. Never triggers orders.

## Campaign targets (predeclared)

- ≥ 200 forward candles
- ≥ 5 baseline BUY/SELL decisions
- ≥ 5 matured outcomes

Continue beyond 200 candles if signals/outcomes are still insufficient. Do not manufacture signals.

## Outcomes

Reuse Phase 18 H1/H2/H3/H6/H12 lifecycle and cost model. Write `AGENT_SHADOW` only; never `HISTORICAL_HYPOTHETICAL`.
