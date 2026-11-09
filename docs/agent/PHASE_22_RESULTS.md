# Phase 22 Results

**Recipe:** `phase22_extended_forward_observation_v1`  
**Date:** 2026-11-09  
**Branch:** `cursor/phase22-extended-forward-observation`

## Verdict

Phase 22 extended forward shadow observation package is implemented and unit-tested offline.  
Default CLI remains readiness-only (no automatic MT5 session in this verification).

**Forward shadow observation infrastructure only — no trading edge claimed.**

## Tests

| Suite | Result |
|-------|--------|
| `phase22.tests.test_phase22` | **12 OK** |
| `phase21.tests.test_phase21` | **8 OK** |
| `phase20.tests.test_phase20` | **14 OK** |
| `phase19.tests.test_phase19` | **20 OK** |
| `phase18.tests.test_phase18` | **21 OK** |
| `phase17.tests.test_phase17` | **7 OK** |
| `phase16a.tests.test_phase16a` | **7 OK** |
| `phase16b.tests.test_phase16b` | **13 OK** |
| Combined 16A–22 | **102 OK** |

## Campaign (readiness)

| Field | Value |
|-------|-------|
| Campaign ID | None yet (created on first `--run-bounded`) |
| Target candles | 1,000 |
| Default session max | 100 |
| Observed candles | 0 |
| Sessions | 0 |
| BUY / SELL / WAIT | 0 / 0 / 0 |
| Discord | Disabled (CLI default; enable with `--discord-live`) |
| Discord signals sent | 0 |
| Pending / completed outcomes | 0 / 0 |
| AGENT_SHADOW experience | 0 |
| HISTORICAL_HYPOTHETICAL | 0 |
| Phase 19 synthetic | Excluded |
| Broker orders | 0 |
| Holdout access | 0 |
| MT5 session started | False |
| Champion | `NO_MODEL` |
| H13_C | `EXPERIMENTAL` |
| Production final_action | `WAIT` |

## Phase 21 comparison baselines (historical reachability only)

| Metric | Value |
|--------|-------|
| Historical BUY rate | 283 / 42,450 ≈ 0.667% |
| Historical SELL rate | 401 / 42,450 ≈ 0.945% |
| Forward experimental BUY/SELL rates | Not yet observed (no MT5 session) |

Distinguish: (1) historical reachability, (2) forward experimental signal frequency, (3) outcome statistics. No statistical significance or profitability claimed.

## Integrity

- Protected Phase 16A–21 hashes: **OK**
- Frozen WF3 thresholds: **intact**
- Phase 20 data: not overwritten
- Packages installed: none
- GitHub push / commit: none

## Operator commands (explicit)

```text
python src/phase22/run_phase22.py
python src/phase22/run_phase22.py --campaign-status
python src/phase22/run_phase22.py --run-bounded --max-candles 100
python src/phase22/run_phase22.py --run-bounded --max-candles 100 --discord-live
```

## Explicit statement

This phase does **NOT** establish a trading edge. Campaign statistics, once collected via explicit bounded sessions, are observations only — not validated trading performance.
