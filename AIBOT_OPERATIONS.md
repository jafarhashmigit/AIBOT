# AIBOT Operations (Final)

**Posture:** Champion `NO_MODEL` · Production `WAIT` · Prompt9 `NO_QUALIFIED_STRATEGY`

This is a **read-only monitoring + shadow-decision** system. It is **not** a profitable production trading bot.

## Start the collector

```powershell
cd C:\Users\Dell\Documents\1\AIBOT
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m phase67.cli start --interval 30
```

## Health check

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m phase67.cli health
```

## Latest evidence

```powershell
.\.venv\Scripts\python.exe -m phase67.cli evidence
.\.venv\Scripts\python.exe -m phase67.cli report
```

## Inspect decisions (orchestrator)

```powershell
.\.venv\Scripts\python.exe -m signal_bot.orchestrator.cli health
.\.venv\Scripts\python.exe -m signal_bot.orchestrator.cli shadow-report
```

## Discord operational reporting

- Default: **SHADOW** (local delivery ledger only; no network).
- Actionable BUY/SELL: **DISABLED** (hard-blocked).
- Optional live **SYSTEM_STATUS** only (never trade alerts):

```powershell
# Requires DISCORD_WEBHOOK_URL in environment or .env (never commit secrets)
$env:AIBOT_DISCORD_OPS_STATUS_LIVE = "1"
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -c "from phase67.service import health_check; from signal_bot.final_delivery.ops_status import build_ops_snapshot_from_health, publish_operational_status; print(publish_operational_status(build_ops_snapshot_from_health(health_check(), event='MANUAL'), force_shadow=False))"
```

A message is **SENT** only if Discord returns HTTP 2xx. Shadow recordings are not claimed as sent.

## Stop the collector

```powershell
.\.venv\Scripts\python.exe -m phase67.cli stop
```

## What WAIT means

NullPolicy / production decision is **WAIT**: no BUY/SELL recommendation. The bot abstains because there is **no qualified strategy**.

## Why actionable trading signals are disabled

- Prompt9 verdict: `NO_QUALIFIED_STRATEGY`
- Strategy approval: `NOT_APPROVED`
- Net profitability: `NOT_ESTABLISHED`
- Risk policy: UNAPPROVED
- Hard safety lock blocks BUY/SELL Discord and `order_send`

## Before strategy activation (future, outside this 10-prompt plan)

1. Evidence-derived frozen strategy rules
2. ≥20 independent complete Exness Asia+London live dates
3. Date-blocked confirmatory validation beating WAIT
4. Cost model with established net profitability (commission/swap/slippage resolved)
5. Risk policy APPROVED
6. Explicit publication authorization
7. Champion registry update (not via env bypass)

## Windows autostart (optional; reboot UNTESTED)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_collector_autostart.ps1 -Action install
powershell -ExecutionPolicy Bypass -File .\scripts\install_collector_autostart.ps1 -Action verify
```

## Safety invariants

- Broker collection: READ_ONLY
- order_send: PROHIBITED
- Live trading: NOT_AUTHORIZED
- Discord actionable: DISABLED
