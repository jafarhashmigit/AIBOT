# Phase 15A — Permission & Feasibility Audit

**Recipe:** `phase15a_telegram_feasibility_v1`  
**Conclusion:** `PERMISSION_REQUIRED`  
**Scope:** Feasibility, compliance, schema, and backtest design only. No acquisition. No scrape.

## Telegram compliance (official sources)

Reviewed:

- https://telegram.org/tos/content-licensing
- https://core.telegram.org/api/terms
- https://telegram.org/tos/bot-developers
- https://core.telegram.org/bots/api

### Applicable restrictions

- Public visibility does **not** authorize scraping, aggregation, archival, or AI/ML research use.
- Content licensing prohibits accessing Telegram content for purposes other than ordinary intended use.
- Scraping/harvesting for AI/ML training, fine-tuning, validation, or benchmarking requires explicit, informed, affirmative, continued, non-transferable consent limited to specific content/chat.
- Bot Developer Terms prohibit data collection for large datasets / ML models / AI products and scraping public group or channel contents for those purposes.
- Bot API `getUpdates` is short-retention (~24h) and is **not** a historical channel archive API.

### Uncertainties

- Whether non-ML independent backtesting of scraped channel text still violates “ordinary intended use” without owner consent is unresolved; Phase 15A requires written owner permission before any real acquisition.
- Edit/delete history completeness and permission scope are unverified without authorized access.
- Third-party republishers are not an authorized AIBOT source.

### Written permission must cover

1. Historical message access (or owner-supplied export).
2. Signal storage and retention (including raw text vs structured fields).
3. Backtesting and performance evaluation against independent prices.
4. Use of message edits and deleted-message history.
5. Sharing of derived performance statistics.
6. Any AI/ML use (separate explicit grant; default forbidden).

## Provider inventory (no channel scrape)

| Provider | Handle | Outcome |
|----------|--------|---------|
| VasilyTrader | @vasilytrading | `PERMISSION_REQUIRED` |
| AnabelSignals | @anabelsignals | `PERMISSION_REQUIRED` |
| Gold Trader Sunny | @goldtradersunny | `PERMISSION_REQUIRED` |
| FX Premiere | @forexsignalstrialgroup | `INSUFFICIENT_ACCESS` |
| United Kings | @unitedkings1 | `INSUFFICIENT_ACCESS` |

Evidence is limited to third-party public references where available. **No historical coverage is claimed.** Channel pages were not fetched. No messages collected.

## Authorized acquisition options (not implemented)

| Option | Description | Status |
|--------|-------------|--------|
| A | Written permission + authorized historical export | Not obtained |
| B | Provider CSV/JSON export with research license | Not obtained |
| C | Small manually supplied authorized sample | Synthetic fixtures only in 15A |
| D | Future forwarding to private research bot (owner-authorized) | Not authorized / not implemented |

Scraping, unofficial clients, paid joins, and Bot API historical harvest remain forbidden.

## Integration boundaries

- External signals use source type `EXTERNAL_PROVIDER_SIGNAL`.
- Must **not** merge with `HISTORICAL_HYPOTHETICAL`, `AGENT_PAPER`, or `FORWARD_SHADOW`.
- Phase 6 / 12 / 12C unchanged.
- Champion remains `no_model` / `NO_MODEL`.
- BUY/SELL not enabled.

## Protections observed

- No holdout open.
- No MT5 connection.
- No broker orders.
- No package install.
- No GitHub push.
- Phase 1–14 protected hashes verified (Phase 14 set).
- No Phase 15B started.

## Stop condition

Permission is not established. Work stops at feasibility + schema + backtest design.
