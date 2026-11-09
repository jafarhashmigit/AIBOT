# Phase 16B — Discord Signal Delivery

**Recipe:** `phase16b_discord_delivery_v1`  
**Branch:** `cursor/phase16b-discord-delivery`  
**Role:** Notification layer only

## Scope

Deliver AIBOT journalled decisions to a private Discord channel via webhook.

```text
AIBOT decision → decision journal → Discord notification adapter → webhook → Discord channel
```

Discord must **not** make trading decisions, change BUY/SELL/WAIT, bypass RiskGate/champion, modify H13_C, or create broker orders. Delivery failure never mutates the underlying decision.

## Destination metadata

- Server ID: `1569306936757719090`
- Channel ID: `1569306937428803667`

Webhook URL is **not** stored in source. Use environment configuration only.

## Configuration

1. Copy `.env.example` → `.env` (gitignored).
2. Set `DISCORD_WEBHOOK_URL` to your Discord webhook.
3. Never commit `.env`. Never log or print the URL.

```text
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Message types

| Type | Purpose |
|------|---------|
| `WAIT` | WAIT observation/decision |
| `EXPERIMENTAL_BUY` | Experimental BUY + disclaimer |
| `EXPERIMENTAL_SELL` | Experimental SELL + disclaimer |
| `PILOT_STATUS` | Session/pilot status |
| `ERROR_DELIVERY_FAILURE` | Delivery failure notice |

Experimental BUY/SELL always include:

`EXPERIMENTAL — NOT A LIVE TRADING SIGNAL`

Under champion `NO_MODEL`, production `final_action` remains WAIT; experimental BUY/SELL notifications still carry the disclaimer and show gated final WAIT.

## Reliability

- HTTP timeout (default 5s)
- Bounded retries (default 3) with backoff
- Structured delivery result (`SENT`, `DRY_RUN`, `FAILED_*`, `SKIPPED_DUPLICATE`, …)
- Dedupe ledger by `message_type:decision_id`
- Graceful failure if Discord unavailable
- No effect on decision engine on failure

## Commands

```text
# Default: dry-run, no network send
python src/phase16b/run_phase16b.py --dry-run

# Explicit live test (only if DISCORD_WEBHOOK_URL configured)
python src/phase16b/run_phase16b.py --send-test
```

Phase 16B implementation **does not** auto-send Discord messages.

## Safety

- No MT5 connection
- No market observation
- No broker orders
- No Phase 1–16A modifications
- Champion remains `NO_MODEL`
- H13_C remains `EXPERIMENTAL`
