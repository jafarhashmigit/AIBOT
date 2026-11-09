# Phase 25 — Dukascopy Live Feed Assessment

**Status:** **`DUKASCOPY_LIVE_UNAVAILABLE`**

Historical bi5 downloads **do not** imply live streaming support.

## Evidence

| Topic | Finding |
|-------|---------|
| `datafeed.dukascopy.com` bi5 | Hourly **historical** archives only |
| JForex API | Official path for **live** strategy data via authenticated trade-server sessions |
| DEMO vs LIVE | DEMO realtime ticks ≠ LIVE; historical on DEMO sourced from LIVE (wiki) |
| Latency / frequency / stability / reconnect | **Not measured** — no live socket in Phase 25 |
| Licensing | Personal/non-commercial default; commercial needs supplementary agreement; redistribution/DB/scraping restrictions in public terms |

## Decision

No officially verified, permitted, unattended **cloud** live XAUUSD feed was demonstrated.

**Do not declare CLOUD_READY** from historical parity alone.
