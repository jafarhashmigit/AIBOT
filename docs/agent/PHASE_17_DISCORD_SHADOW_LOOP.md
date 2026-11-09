# Phase 17 — Discord Shadow Signal Loop

**Recipe:** `phase17_discord_shadow_loop_v1`  
**Branch:** `cursor/phase17-discord-shadow-loop`

## Objective

Observe completed XAUUSD M5 candles (read-only), run experimental H13_C, journal decisions, then optionally notify Discord.

```text
Completed M5 → observation → H13_C predictor → Phase 12C gate
→ decision journal → Discord adapter (optional)
```

## Safety

- Champion remains `NO_MODEL`
- H13_C remains `EXPERIMENTAL`
- Production `final_action` is always `WAIT`
- Experimental BUY/SELL labeled `EXPERIMENTAL — NOT A LIVE TRADING SIGNAL`
- No broker orders, no RiskGate bypass, no holdout access
- Phase 16A/16B sources reused, not rewritten
- Discord failure never changes the decision
- **Default CLI does not start MT5 or send Discord**

## Bounded runtime

| Setting | Default |
|---------|---------|
| `max_candles` | **3** |
| Discord | dry-run unless `--discord-live` |

## Commands

```text
# Ready report only (default) — no MT5, no Discord
python src/phase17/run_phase17.py

# First bounded shadow run (explicit) — journal + live Discord
python src/phase17/run_phase17.py --run-bounded --max-candles 3 --discord-live

# Bounded run without Discord POST
python src/phase17/run_phase17.py --run-bounded --max-candles 3 --dry-run-discord
```

## Discord labels

- WAIT: `AIBOT SHADOW — WAIT`
- Experimental BUY/SELL: `AIBOT SHADOW — EXPERIMENTAL BUY/SELL` + disclaimer
