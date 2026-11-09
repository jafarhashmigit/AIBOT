# Phase 16B — Configuration

## Required secret

| Key | Location | Committed? |
|-----|----------|------------|
| `DISCORD_WEBHOOK_URL` | process env or gitignored `.env` | **Never** |

## Setup

1. Ensure `.env` is listed in `.gitignore` (already present).
2. Copy `.env.example` to `.env`.
3. Paste your Discord webhook URL as the value of `DISCORD_WEBHOOK_URL`.
4. Do not put the webhook in source, docs, reports, or chat logs.
5. If a webhook was ever exposed in chat or logs, **rotate it** in Discord and update `.env`.

## Verification without revealing the secret

```text
python src/phase16b/run_phase16b.py --dry-run
```

Reports show `webhook_configured: true|false` only — never the URL.

## Explicit first live test (manual)

Only after `.env` is set:

```text
python src/phase16b/run_phase16b.py --send-test
```

This is the only supported path for a real Discord message from Phase 16B.
