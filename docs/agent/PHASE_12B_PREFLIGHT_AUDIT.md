# Phase 12B — Read-only preflight and RiskGate parity audit

**Conclusion: `PHASE 12B PREFLIGHT INCOMPLETE`**

Stage B is not authorized. Forward observation has not begun. `--start-session` was not executed. MetaTrader5 was not imported, initialized, or connected.

## Why incomplete

Safety audits passed (MT5 adapter, broker-order impossibility, storage isolation, session safety, temporal isolation, Phase 1–11 integrity).

Exact Phase 6 `RiskGate.evaluate()` parity on **forward** timestamps cannot be established without modifying Phase 6:

- `Observation.__post_init__` calls `assert_before_cutoff`.
- `RiskGate.evaluate()` raises `InformationBoundaryError` on timestamps after `2026-09-29 18:50:00`.
- Phase 12 does not change Phase 6.

Pre-cutoff `evaluate()` + `apply_gate` matches Phase 12 `apply_frozen_gate` for WAIT / BUY / SELL, and every compared `final_action` is WAIT. That is a frozen-policy table match, **not** a claim that `evaluate()` supports forward bars.

## Branch

`cursor/phase12b-preflight-audit`

## Tests

| Suite | Run 1 | Run 2 | Deterministic |
|---|---|---|---|
| Phase 12B (`test_phase12b.py`) | 20/20 | 20/20 | yes |
| All Phase 12 (`test_*.py`) | 43/43 | 43/43 | yes |

Mocks and synthetic fixtures only. No live ticks, bars, or MT5.

## MT5 static audit — PASS

Inspected `src/phase12/mt5_readonly.py` and every Python module under `src/phase12/` via AST (never importing MetaTrader5).

Verified:

- No import-time connection.
- No module-level `import MetaTrader5`.
- No automatic terminal launch.
- No reconnect loop (`while True`).
- No background thread.
- No order-execution wrapper.
- No trading API abstraction.
- No writes to broker account state.
- `symbol_select(..., True)` removed (it mutates Market Watch).
- `connect_readonly()` was not invoked.

Adapter calls actually present in source: `initialize`, `last_error`, `terminal_info`, `account_info`, `symbol_info`, `shutdown`. Those sit only inside `connect_readonly()`, which 12B does not call.

### Permitted MT5 API allowlist

```
initialize
shutdown
last_error
terminal_info
account_info
symbol_info
copy_rates_from
copy_rates_from_pos
copy_rates_range
version
```

`copy_rates_*` and `version` are reserved for a later Stage B market-data read. They are not called in the current adapter.

### Denylist (must not be reachable)

```
order_send, order_check, order_calc_margin, order_calc_profit
positions_get, positions_total
orders_get, orders_total
history_orders_get, history_deals_get
buy, sell, Close
symbol_select
```

None of these appear as `mt5.<name>` / `getattr(mt5, ...)` / `from MetaTrader5 import ...` anywhere under `src/phase12/`.

## Broker-order impossibility — PASS

No `order_send`, `order_check`, pending-order, position, modification, or close API is reachable from the Phase 12 adapter call graph. There is no broker-order wrapper. Runtime counters: MT5 connections 0, initialize calls 0, broker orders 0, live market requests 0.

## RiskGate parity — INCOMPLETE

Frozen Phase 6 gate: `wait_only=True`, `champion_id=no_model`, version `phase6_wait_only_no_champion_v1`. Unchanged (`src/phase6/risk_gate.py` SHA-256 still `a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3`).

| Case | Phase 6 `evaluate()` at 2026-06-19 10:00:00 | Phase 12 `apply_frozen_gate` | Forward `evaluate()` |
|---|---|---|---|
| No approved model | raw WAIT → ALLOW / WAIT | WAIT | not reachable |
| Raw BUY | BLOCK / WAIT | BLOCK / WAIT | not reachable |
| Raw SELL | BLOCK / WAIT | BLOCK / WAIT | not reachable |
| Raw WAIT | ALLOW / WAIT | ALLOW / WAIT | not reachable |
| Missing prediction | Phase 12 never predicts; WAIT | WAIT | n/a |
| Invalid prediction | Phase 12 does not consume predictions | WAIT | n/a |
| Uncertainty unavailable | Gate does not use uncertainty | WAIT | n/a |
| Unknown model id | `propose_action` raises; cannot bypass | WAIT | n/a |

Phase 12 does not call `RiskGate.evaluate()` on forward observations. It applies the same WAIT-only branches through Phase 6 `GateResult` + `apply_gate`. That is not silent approximation of `evaluate()` on post-cutoff bars; the gap is reported as INCOMPLETE.

## Post-cutoff / temporal isolation — PASS

- Forward records are accepted only by the Phase 12 shadow path.
- Source type remains `FORWARD_SHADOW` (not `AGENT_PAPER`, not `HISTORICAL_HYPOTHETICAL`).
- Phase 6 Observation construction refuses post-cutoff timestamps.
- Phase 8/9/10/11 loaders do not reference `FORWARD_SHADOW` or `src/data/phase12`.
- `ShadowStore` refuses writes under `src/data` that are outside `src/data/phase12`.
- Historical dataset hashes unchanged.
- Holdout `xauusd_m5_test.csv` open attempts: 0.

## Storage isolation — PASS

Writes are restricted to `src/data/phase12/` (production) or isolated temp dirs (tests).

- Append-safe CSV rewrite of the Phase 12 journal only.
- Duplicate `observation_id` / open timestamp rejected.
- Schema field lists enforced.
- Session identity recorded in `shadow_sessions.csv`.
- Restart skips duplicates.
- No overwrite of Phase 1–11 data.
- Phase 10 paper store artifacts unchanged.
- Historical experience CSVs unchanged.

## Session safety — PASS

- `--start-session` is an explicit flag; import does not start a session.
- `--start-session` was **not** executed in this audit (implementation still refuses to auto-connect).
- One lock file; concurrent `start()` rejected.
- Graceful `stop()` unlinks the lock and **appends** a session row; journals are not deleted.
- In-process ingest exceptions call `record_interrupted()` and leave the lock.
- OS-kill limitation: no interrupted row is written; lock remains; journals remain until `--stop-session`.
- `--status`, `--summary`, `--validate-journal` construct `SessionManager(read_only=True)` and cannot mkdir/write.

## Phase 12B corrections (Phase 12 only)

These Stage A defects were corrected inside `src/phase12/` only:

1. **`mt5_readonly.py`** — removed `symbol_select(..., True)` (Market Watch mutation). Probe uses `symbol_info` only. `shutdown()` in `finally`.
2. **`mt5_allowlist.py`** (new) — AST allowlist/denylist. Never imports MetaTrader5.
3. **`decision_recorder.py`** — `apply_frozen_gate` uses Phase 6 `GateResult` + `apply_gate` without forwarding post-cutoff Observations into `evaluate()`.
4. **`session_manager.py` / `storage.py`** — `read_only` mode; refuse writes outside `src/data/phase12`; `record_interrupted`.
5. **`run_phase12.py`** — `--status` / `--summary` / `--validate-journal` are read-only.

Phase 6 DecisionEngine and RiskGate were not modified.

## Integrity

Protected Phase 1–11 hashes matched before and after this preflight run, including:

- `src/phase6/risk_gate.py`
- `src/phase6/decision_engine.py`
- Phase 2 OOS predictions, labels, outcomes, splits
- Phase 8/9/10/11 stores, runners, and frozen reports

Holdout was not opened. Historical research CSVs were not written. No packages installed or changed. No GitHub push.

## Reports (gitignored under `reports/`)

- `reports/phase12b/mt5_static_audit.json`
- `reports/phase12b/risk_gate_parity.json`
- `reports/phase12b/storage_isolation.json`
- `reports/phase12b/session_safety.json`
- `reports/phase12b/temporal_safety.json`
- `reports/phase12b/integrity.json`
- `reports/phase12b/preflight_summary.json`

## Final counts

| Check | Value |
|---|---|
| MT5 connections | 0 |
| MetaTrader5 initialization calls | 0 |
| Broker orders | 0 |
| Live market requests | 0 |
| Observation sessions started | 0 |
| Historical holdout opens | 0 |
| Model training | 0 |
| Package changes | 0 |
| Phase 1–11 modifications | 0 |
| Historical datasets modified | 0 |
| GitHub pushes | 0 |

## Not authorized

- Stage B live observation
- `--start-session`
- Phase 13
- Model training or promotion
- Any change to the WAIT-only policy
