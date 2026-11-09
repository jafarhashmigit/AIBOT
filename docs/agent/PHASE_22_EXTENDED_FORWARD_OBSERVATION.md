# Phase 22 — Extended Forward Shadow Observation

**Recipe:** `phase22_extended_forward_observation_v1`  
**Branch:** `cursor/phase22-extended-forward-observation`  
**Mode:** Forward observation infrastructure (readiness-only by default)

**Forward shadow observation infrastructure only — no trading edge claimed.**

## Objective

Collect a meaningful sample of **real forward** XAUUSD M5 market observations to evaluate the existing H13_C experimental rule against Phase 21 historical reachability baselines.

Phase 21 (historical condition frequencies, not live trade rates):

| Side | Hits / N | Rate |
|------|----------|------|
| BUY | 283 / 42,450 | 0.667% |
| SELL | 401 / 42,450 | 0.945% |

Phase 22 compares those baselines with **forward experimental signal frequency** and multi-horizon **outcome statistics**, without claiming significance or profitability.

## Architecture (reuse only)

Reuses without modification:

- Phase 14 H13_C + frozen WF3 thresholds
- Phase 16A `predict_h13c_experimental`
- Phase 16B Discord delivery / dedupe
- Phase 18 multi-horizon outcomes + experience stores
- Phase 19 synthetic validation (excluded from this campaign)
- Phase 20 real MT5 candle validation + outcome resolution + shadow messages
- Phase 20A WAIT diagnostics context
- Phase 21 reachability rates (comparison only)

Does **not** create a new strategy, loosen thresholds, or overwrite Phase 18/19/20 data roots.

## Campaign design

| Setting | Value |
|---------|-------|
| Observation target | 1,000 newly completed M5 candles |
| Default session bound | 100 candles |
| Resumable | Yes (`campaign_state.json`) |
| Historical replay | Forbidden |
| Incomplete candles | Rejected |
| Duplicate candles | Rejected / skipped |
| Auto full campaign | Forbidden — each session needs `--run-bounded` |

The 1,000-candle figure is an **observation target**, not a deadline and not a guarantee of BUY/SELL signals.

## Signal generation

For every completed candle:

1. Evaluate existing BUY conditions (frozen).
2. Evaluate existing SELL conditions (frozen).
3. Record WAIT + exact reason when neither qualifies.
4. Journal feature values and threshold comparisons.

Never force BUY/SELL. Never loosen thresholds. Never add filters.

## Diagnostics journal

Per candle: UTC + PKT timestamps, OHLC, H1 direction, `close_to_ema_20`, `ema_9_20_spread`, frozen cuts, BUY/SELL condition booleans, experimental action, WAIT reason, production `final_action`, data quality, pending/completed outcome counts.

## Five-horizon outcomes

For naturally generated experimental BUY/SELL only:

| ID | Horizon |
|----|---------|
| H1 | 5M |
| H2 | 10M |
| H3 | 15M |
| H6 | 30M |
| H12 | 60M |

PASS / FAIL / TIMEOUT / PENDING tracked independently. Expected Horizon display remains `NOT ESTABLISHED`. Production `final_action` remains `WAIT`.

## Experience separation

| Source | Role |
|--------|------|
| `AGENT_SHADOW` | Real forward experimental decisions |
| `HISTORICAL_HYPOTHETICAL` | Historical hypothetical (separate) |
| `PHASE19_SYNTHETIC_TEST` | Synthetic validation only — excluded |

No production model training from these observations.

## Discord

- Disabled unless `--discord-live`
- BUY/SELL only (never WAIT)
- Disclaimer: `AIBOT SHADOW — NOT A REAL TRADING SIGNAL`
- Existing dedupe / delivery ledger

## CLI

```text
python src/phase22/run_phase22.py
python src/phase22/run_phase22.py --campaign-status
python src/phase22/run_phase22.py --run-bounded --max-candles 100
python src/phase22/run_phase22.py --run-bounded --max-candles 100 --discord-live
```

## Safety

| Constraint | Enforcement |
|------------|-------------|
| Champion | `NO_MODEL` |
| H13_C | `EXPERIMENTAL` |
| Production final_action | `WAIT` |
| Broker orders | 0 |
| Holdout | Not accessed |
| Frozen WF3 cuts | Hash + value checks |
| Phase 20 data | Write-isolated |
| Packages / GitHub push | None |

## Artifacts

```text
src/phase22/
docs/agent/PHASE_22_EXTENDED_FORWARD_OBSERVATION.md
docs/agent/PHASE_22_RESULTS.md
reports/phase22/
src/data/phase22/
```
