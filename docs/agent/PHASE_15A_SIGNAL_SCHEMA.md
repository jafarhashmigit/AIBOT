# Phase 15A — Normalized External Signal Schema

**Schema version:** `phase15a_signal_schema_v1`  
**Fixtures:** Synthetic only. No real provider messages.

## Purpose

Normalize authorized external XAUUSD signal records for future independent research, while preserving timestamps, provenance, and permission references.

## Required fields

| Field | Description |
|-------|-------------|
| `provider_id` | Stable provider key |
| `signal_id` | Unique signal identifier within provider |
| `original_message_reference` | Channel handle / message id / export row id |
| `published_at_utc` | Original publication time (UTC) |
| `last_updated_at_utc` | Last update time (UTC) |
| `instrument` | Expected `XAUUSD` |
| `direction` | `BUY` \| `SELL` \| `UNKNOWN` |
| `entry_type` | `MARKET` \| `LIMIT_ZONE` \| `UNKNOWN` |
| `entry_min` / `entry_max` | Entry price or zone bounds |
| `stop_loss` | Stop loss price or null |
| `take_profit_levels` | Ordered list of TP prices |
| `status` | Lifecycle status |
| `update_reference` | Parent id, update kind, prior SL/TP |
| `permission_reference` | Permission id, grantor, time, AI/ML flag |
| `data_provenance` | `OWNER_EXPORT` \| `AUTHORIZED_SAMPLE` \| `AUTHORIZED_FORWARD` \| `SYNTHETIC_FIXTURE` |
| `completeness_status` | `COMPLETE` \| `PARTIAL` \| `AMBIGUOUS` \| `INCOMPLETE` |

## Supported cases

- BUY and SELL
- Market entry and entry zones
- Multiple take-profit levels
- Modified stop loss (via `update_reference`)
- Cancelled signals
- Ambiguous signals
- Unfilled signals
- Incomplete records
- Original timestamps and provenance preserved

## Status values

`OPEN`, `MODIFIED`, `CANCELLED`, `UNFILLED`, `AMBIGUOUS`, `INCOMPLETE`, `CLOSED_UNKNOWN`

## Synthetic fixtures

Phase 15A ships synthetic examples (`SYN-001` … `SYN-006`) covering market buy, zone sell, modified SL, cancelled, ambiguous, unfilled, and incomplete records. These are **not** real Telegram content.

## Permission gate

Real provider records must carry a non-null `permission_reference` with AI/ML default `covers_ai_ml=false` unless separately granted.

## Independent backtest (design only)

See `reports/phase15a/backtest_design.json`. Publication time is the earliest eligible entry. Unfilled → `NOT_FILLED`. Same-candle SL/TP → conservative adverse. Provider win claims ignored. Not executed in Phase 15A.
