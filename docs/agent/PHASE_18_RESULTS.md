# Phase 18 Results

**Recipe:** `phase18_multi_horizon_shadow_learning_v1`  
**Date:** 2026-11-09  
**Mode:** Implementation + offline verification (no live MT5 auto-run)

## Verdict

Phase 18 multi-horizon shadow-learning scaffolding is implemented and tested offline.  
**No profitable edge is claimed** for 5M / 10M / 15M / 30M / 60M signals.  
Purpose: auditable multi-horizon shadow evidence collection for later validation.

## Test results

| Suite | Result |
|-------|--------|
| `phase18.tests.test_phase18` | **21 tests OK** |
| `phase17.tests.test_phase17` (regression) | **7 tests OK** |

Covered cases include: all five horizons; outcome timing; PASS/FAIL/TIMEOUT/PENDING; WAIT non-trade; BUY/SELL simulation; historical vs shadow experience separation; PASS/FAIL experience retention; duplicate outcome/Discord prevention; restart recovery; PKT daily aggregation; pending excluded from PASS/FAIL rate; WAIT excluded from trade stats; Expected Horizon / Expected Outcome Check wording; no guarantee language; production WAIT; champion `NO_MODEL`; H13_C `EXPERIMENTAL`; broker orders 0; Phase 16A/16B/17 hash integrity.

## Final verification checklist

| # | Item | Status |
|---|------|--------|
| 1 | Tests passed | YES (Phase 18 + Phase 17 regression) |
| 2 | Phase 16A integrity | UNCHANGED (hash match) |
| 3 | Phase 16B integrity | UNCHANGED (hash match) |
| 4 | Phase 17 regression | PASSING |
| 5 | Holdout access count | 0 |
| 6 | MT5 mode | read-only when explicitly `--run-bounded`; default readiness-only |
| 7 | Broker order count | 0 |
| 8 | Discord messages sent (this verification) | 0 (ready/dry-run path; no live bounded run executed by default) |
| 9 | Duplicate messages prevented | YES (ledger + deterministic IDs; tested) |
| 10 | Pending outcomes | Supported (`PENDING`) |
| 11 | PASS outcomes | Supported |
| 12 | FAIL outcomes | Supported |
| 13 | TIMEOUT outcomes | Supported |
| 14 | Shadow experience records added | Via `AGENT_SHADOW` store when outcomes finalize (tested) |
| 15 | Historical experience records | Separate `HISTORICAL_HYPOTHETICAL` store (tested; not merged) |
| 16 | Champion status | `NO_MODEL` |
| 17 | H13_C status | `EXPERIMENTAL` |
| 18 | Production `final_action` | `WAIT` |
| 19 | Git status | Local branch `cursor/phase18-multi-horizon-shadow` with Phase 18 artifacts (uncommitted unless requested) |
| 20 | GitHub push | **None performed** |

## Selected Horizon

`NOT ESTABLISHED` — no validated selection rule; do not invent confidence.

**Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.**

## Safety reminders

- Protected Phase 16A / 16B / Phase 17 core files not modified
- No holdout reads
- No package installs
- No MT5 orders
- Webhook secrets not printed
- Default CLI does not start observation

## First explicit live bounded command (operator)

```text
python src/phase18/run_phase18.py --run-bounded --max-candles 3 --discord-live
```
