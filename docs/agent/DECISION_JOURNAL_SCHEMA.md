# Decision journal schema

Status: documentation only (Phase 1). No inference engine writes this journal yet.

The journal records **every** closed-bar decision, including WAIT. Decision-time
fields are written when the bar closes. Outcome fields are attached later, only
after the 12-bar hypothetical window is historically complete. Outcome fields
must never be visible to the inference engine, feature store, or model inputs.

Timestamps are UTC after the corrected conversion (`Europe/Athens` server clock
→ UTC). Until that feature file is the production source, `timestamp_server`
is also stored.

## 1. Decision-time record (known at bar close)

| Field | Type | Required | Notes |
|---|---|---|---|
| `decision_id` | string | yes | Stable unique id. Suggested: `{iso_timestamp_utc}_{symbol}_{timeframe}` |
| `timestamp_utc` | datetime | yes | Bar-close time in UTC (decision time) |
| `timestamp_server` | datetime | yes | Naive broker server wall clock (Europe/Athens face) |
| `symbol` | string | yes | `XAUUSD` |
| `timeframe` | string | yes | `M5` |
| `action` | string | yes | `BUY` / `SELL` / `WAIT` — the action the agent would have taken |
| `selected_action` | string | yes | Same as `action`; kept so later outcome joins cannot overwrite intent |
| `primary_model_version` | string | yes | Registry id of the primary classifier |
| `meta_model_version` | string | no | Registry id, or empty if no meta-model |
| `p_buy` | float | yes | Primary (or calibrated) P(BUY) at decision time |
| `p_sell` | float | yes | P(SELL) |
| `p_wait` | float | yes | P(WAIT); the three probabilities must sum to 1 ± 1e-9 |
| `expected_buy_r` | float | yes | Decision-time E[net R \| BUY] |
| `expected_sell_r` | float | yes | Decision-time E[net R \| SELL] |
| `risk_gate_status` | string | yes | `pass` / `block` |
| `block_reason` | string | no | Empty when the gate passed. Why WAIT was forced otherwise |
| `feature_version` | string | yes | Feature-file / schema version |
| `data_hash` | string | yes | Hash of the feature row (or of the causal prefix used) |
| `model_configuration_hash` | string | yes | Hash of model ids + hyperparameters + cost assumptions |
| `recipe_hash` | string | yes | Pre-registration recipe hash |
| `journal_schema_version` | string | yes | This document's version, currently `1.0` |

WAIT is a first-class action. A blocked BUY/SELL is recorded as `action=WAIT`
with `block_reason` set; the raw argmax is **not** silently dropped.

## 2. Outcome record (attached after the window is historically complete)

These fields live in a **separate** store or a clearly marked suffix (`outcome_*`).
They are not present at decision time and must not be joined into the feature
matrix or the live prompt.

| Field | Type | Notes |
|---|---|---|
| `outcome_attached_at_utc` | datetime | When the outcome was computed |
| `outcome_eligible` | bool | False if the window was incomplete or crossed a market gap |
| `hypothetical_buy_net_r` | float | Label/cost methodology; empty if ineligible |
| `hypothetical_sell_net_r` | float | Same |
| `selected_action_net_r` | float | Outcome of `selected_action`; empty if WAIT or ineligible |
| `outcome_timestamp` | datetime | Exit time of the selected (or hypothetical) trade |
| `exit_reason` | string | `TP` / `SL` / `TIME` / empty |

Hypothetical BUY and SELL outcomes are always stored, even when the agent
chose WAIT, so later meta-labeling can use them. They are still future
information relative to `timestamp_utc`.

## 3. Separation rule

- Writer A (inference): may write section 1 only.
- Writer B (outcome attach): may write section 2 only, and only for rows whose
  window end is ≤ the research cutoff (or, after G4, the then-approved range).
- Reader for training/inference: section 1 only.
- Reader for evaluation: sections 1 and 2, with `finding_class` marked.

## 4. Completeness

Every closed bar in the evaluated range must have a section-1 row. Missing WAIT
rows are a data-quality failure, not an optional skip.
