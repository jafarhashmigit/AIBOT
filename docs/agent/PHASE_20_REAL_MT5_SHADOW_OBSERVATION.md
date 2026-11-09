# Phase 20 — Real MT5 Shadow Observation & Outcome Learning

**Recipe:** `phase20_real_mt5_shadow_observation_v1`  
**Branch:** `cursor/phase20-real-mt5-shadow`

## Objective

Move from Phase 19 synthetic validation to the **real MT5 read-only shadow pipeline**.

When experimental H13_C naturally emits BUY/SELL on newly completed XAUUSD M5 candles:

1. Journal the experimental decision  
2. Discord-notify (BUY/SELL only)  
3. Track H1–H12 outcomes independently  
4. Store completed results as `AGENT_SHADOW`  
5. Keep historical / synthetic sources separate  

**Infrastructure/shadow validation only — no trading edge claimed.**

## Architecture

```text
MT5 RO completed M5
→ incomplete-candle filter
→ H13_C experimental prediction (unchanged)
→ production gate → final_action=WAIT
→ Phase 20 journal (src/data/phase20)
→ Discord BUY/SELL only (Phase 16B client)
→ Phase 18 barrier/outcome engine (H1/H2/H3/H6/H12)
→ AGENT_SHADOW experience (phase20 store only)
```

Reuses Phase 16A reader/predictor, Phase 16B Discord client/dedupe, Phase 18 store/outcomes/barrier/experience — **without modifying** those packages.

## Safety boundaries

| Rule | Status |
|------|--------|
| Broker orders | Forbidden (count = 0) |
| Live trading / account mutation | Forbidden |
| Fabricate / force BUY/SELL | Forbidden |
| Change H13_C thresholds | Forbidden |
| Modify Phase 16–19 sources | Forbidden (hash-protected) |
| Holdout access | Forbidden |
| Champion | `NO_MODEL` |
| H13_C | `EXPERIMENTAL` |
| Production `final_action` | `WAIT` |
| Phase 19 synthetic mix-in | Forbidden |
| Auto-start MT5 on import/default CLI | Disabled |

## Real MT5 data flow

- Only **newly completed** M5 candles (`as_of > bar_close`)
- No CSV historical replay as live source
- No fabricating/filling gaps
- No processing the forming candle
- Duplicate open-timestamps rejected

## Signal lifecycle

- WAIT → journal observation/decision; **no** trade outcomes; **no** Discord signal  
- BUY/SELL → journal + 5 pending horizons + Discord shadow signal  
- Selected Horizon remains `NOT ESTABLISHED`  
- Expected Horizon is an **evaluation horizon**, not guaranteed time-to-profit  
- Disclaimer: `AIBOT SHADOW — NOT A REAL TRADING SIGNAL`

## Five-horizon outcomes

Independent PASS / FAIL / TIMEOUT / PENDING per H1–H12 using validated Phase 18 cost-aware barriers. Shorter-horizon completion does not skip longer horizons.

## Experience separation

| Source | Location |
|--------|----------|
| `AGENT_SHADOW` | `src/data/phase20/` only |
| `HISTORICAL_HYPOTHETICAL` | separate file in same store if seeded |
| Phase 19 synthetic | excluded; real loop refuses Phase 19 paths |

## Restart behavior

On start: load pending outcomes → evaluate newly available M5 bars → finalize → Discord/experience once (deduped). No signal replay as new.

## Discord behavior

- BUY/SELL signals + outcome updates only  
- Uses Phase 16B webhook client when `--discord-live`  
- Default / dry-run never POSTs  
- Secrets never logged  

## Commands

```text
# Ready only (default)
python src/phase20/run_phase20.py

# Explicit bounded real shadow (operator-requested)
python src/phase20/run_phase20.py --run-bounded --max-candles 12 --discord-live

# Bounded without Discord POST
python src/phase20/run_phase20.py --run-bounded --max-candles 12 --dry-run-discord
```

## Limitations

- BUY/SELL sample size depends on natural H13_C emissions (may be zero in a short bound)  
- Shadow R statistics are **not** validated trading performance  
- Does not train or promote models  
- Does not establish edge  

## Package

```text
src/phase20/
docs/agent/PHASE_20_REAL_MT5_SHADOW_OBSERVATION.md
docs/agent/PHASE_20_RESULTS.md
reports/phase20/
src/data/phase20/
```
