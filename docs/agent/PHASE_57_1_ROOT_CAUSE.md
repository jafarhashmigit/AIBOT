# Phase 57.1 — Root Cause & Recovery Design

**Recipe:** `phase57_1_durable_experience_recovery_transaction_integrity_v1`

## Root cause (Phase56 / Phase57 gap)

1. **Exit-to-outcome sequence today** (`IntegratedLifecycleEngine._finalize_close` → `persist`):
   - Exit detected in `monitor_and_maybe_exit` / in-bar monitor.
   - `_finalize_close` appends `position_id` to in-memory `closed_position_ids`.
   - Shadow experience is appended **in memory** via `record_agent_shadow` (new random `experience_id`).
   - Later `persist()` writes **two independent files**: `agent_state.json` (includes `closed_ids`) and `experiences.jsonl` (shadow flush).

2. **Crash windows**
   - After exit in memory, before any disk write.
   - After state save with `closed_ids`, before / without durable experience (`after_exit_before_outcome` in Phase57).
   - Partial / truncated JSONL write of experience.
   - Experience file deleted or emptied while state retains `closed_ids`.

3. **Why recovery failed**
   - `closed_position_ids` is only a set of IDs — **no** exit price, reason, BID/ASK side, R-multiple, or decision evidence.
   - There is **no** canonical trade journal.
   - Derived experience store is treated as the only outcome store; deleting it permanently loses committed outcomes.
   - Double-close protection correctly refuses re-finalize, so lost experience cannot be rebuilt from engine state.

4. **Partial writes**
   - ExperienceStore.flush rewrites the whole JSONL; truncate mid-write can corrupt the derived store.
   - State and experience are not one atomic transaction.

## Recovery design (Phase57.1 only — Phase0–57 unmodified)

**Canonical source of truth:** append-only `TradeLifecycleJournal` under `src/data/phase57_1/journal/`.

Transaction stages:

`POSITION_OPEN → EXIT_DETECTED → EXIT_COMMITTED → OUTCOME_DERIVED → EXPERIENCE_COMMITTED`

Guarantees:

- Full closed-trade evidence is durably committed at `EXIT_COMMITTED` **before** a trade is considered outcome-finalized.
- Deterministic `experience_id` derived from `txn_id` (rebuild-stable).
- WAL + atomic file replace for stage commits; invalid checksums quarantined.
- Derived hist/shadow stores are rebuildable from the journal; never merged.
- `closed_ids` remain an idempotency index only — **not** outcome truth.

**Wrapper:** `DurableLifecycleEngine` subclasses Phase56 `IntegratedLifecycleEngine` and overrides `_finalize_close` / open hooks without editing Phase56 source.
