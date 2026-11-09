# Phase 16A — Controlled MT5 Pilot Results (Reconciled Close-Out)

**Recipe:** `phase16a_h13c_shadow_pilot_v1`  
**Branch:** `cursor/phase16a-h13c-shadow-integration`  
**Close-out verdict:** `CLEANLY_CLOSED`  
**Champion:** `NO_MODEL` · **Candidate:** `H13_C_H1_PULLBACK` / `EXPERIMENTAL`

## Preflight

- Verdict: **PASS** (`reports/phase16a/preflight.json`)
- MT5 probe: `connected_readonly` (MetaQuotes-Demo)
- Forward gate: experimental BUY/SELL blocked → production `WAIT`
- Protected hashes: OK

## Timezone / clock evidence

| Source | Value |
|--------|-------|
| System UTC at recon start | `2026-11-09 12:01:55` |
| System local (PKT) | `2026-11-09 17:01:55` (**UTC+5**) |
| Journal stamps | Naive strings treated as **UTC** (`YYYY-mm-dd HH:MM:SS`) |
| Session B PKT fields from runner | start `16:04:33 PKT`, stop `17:04:33 PKT` (= UTC+5 of 11:04:33 / 12:04:33) |
| File mtimes (UTC) | Observations/decisions last write `12:00:02`; sessions/stop `12:04:33` |

No timestamps were invented or rewritten during close-out.

## Session A — interrupted attempt

| Field | Evidence |
|-------|----------|
| `session_id` | `phase16a_2026-11-09T100953_1ae83652` |
| Start UTC | `2026-11-09 10:09:53` |
| Stop UTC | `2026-11-09 11:04:21` |
| Duration | **3268 s** (not full hour) |
| Status | `interrupted` / `process_interrupted_spawn_aborted` |
| Observations (by `observation_created_at_utc` &lt; B start) | **12** |
| Bar opens | `10:00:00` → `10:55:00` UTC |
| Experimental / final | **WAIT / WAIT** only |

## Session B — completed controlled pilot

| Field | Evidence |
|-------|----------|
| `session_id` | `phase16a_2026-11-09T110433_b95e410d` |
| Start UTC | `2026-11-09 11:04:33` |
| Stop UTC | `2026-11-09 12:04:33` |
| Duration | **3600 s** (exact target) |
| Status | `stopped` / `graceful stop; lock cleared` |
| Observations | **12** |
| Bar opens | `11:00:00` → `11:55:00` UTC |
| Experimental counts | BUY 0 · SELL 0 · **WAIT 12** |
| Final actions | **WAIT 12** |
| Outcomes file | none (`shadow_outcomes.csv` absent; no BUY/SELL to track) |
| Gaps | 0 new gaps in Session B path (`gap_status` first+continuous overall) |
| Broker orders | **0** |
| Paper trades | **0** |

Runner `session_summary.json` matches Session B only (`candles_observed: 12`, `status: completed`).

## Combined journal integrity

- Total observation rows: **24** (12 + 12); **not merged** — sessions kept separate in reconciliation
- Unique `observation_id`, unique `bar_open_timestamp_utc`, unique `decision_id`: **yes**
- All rows: `bar_close_timestamp_utc < observation_created_at_utc` (completed M5 only)
- Model status: `NO_MODEL`; candidate status: `EXPERIMENTAL`
- No fabricated outcomes; no BUY/SELL experimental or final actions

## Lock reconciliation

- During close-out start, lock was **active** and held by live PIDs **3832 / 6780** running `--pilot --duration-seconds 3600`
- Therefore lock was **not orphaned** and was **not force-deleted**
- After natural deadline, process exited; `session.py` `finally` called `clear_lock()`; lock **absent**
- Archived evidence: `reports/phase16a/session_lock_archive.txt`

## Answers required by close-out brief

| Question | Answer |
|----------|--------|
| Full one-hour duration? | **Yes** for Session B (3600 s). Session A no (3268 s interrupted). |
| Interrupted? | Session A **yes**. Session B **no**. |
| Incomplete observations? | No incomplete M5 rows in journals. Outcome horizon N/A (all WAIT). |
| Another controlled session required? | **No** for close-out completeness. Optional later research session is out of scope. |

## Safety

- No MT5 reconnect during close-out
- No new session started
- No Discord
- No Phase 1–15C edits
- No package install
- No H13_C parameter / champion changes
- No git push

## Artifacts

- `reports/phase16a/session_summary.json` (runner Session B)
- `reports/phase16a/session_reconciliation.json` (both sessions)
- `reports/phase16a/session_lock_archive.txt`
- `reports/phase16a/phase16a_summary.json`
- `reports/phase16a/integrity.json`
- `src/data/phase16a/shadow_*.csv`
