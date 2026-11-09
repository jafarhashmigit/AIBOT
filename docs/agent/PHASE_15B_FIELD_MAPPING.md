# Phase 15B — Field Mapping Documentation

Target: **`phase15a_signal_schema_v1`**

## VasilyTrader-style → schema v1

| Source | Target | Status |
|--------|--------|--------|
| `side` | `direction` | direct |
| `entry` | `entry_min`, `entry_max` | exact → both set equal |
| (implicit) | `entry_type` | derived `MARKET` |
| `sl` | `stop_loss` | direct |
| `tp` | `take_profit_levels[0]` | wrapped to list |
| `published_at` | `published_at_utc` | direct |
| `updated_at` | `last_updated_at_utc` | optional; else = published |
| `msg_id` | `original_message_reference.message_id` | direct |
| `fixture_id` | `signal_id` | direct |
| `event` / `prior_sl` | `status` / `update_reference` | derived |
| — | `permission_reference` | **injected** (required) |
| — | `data_provenance` | **injected** `SYNTHETIC_FIXTURE` |
| — | `completeness_status` | derived |

## AnabelSignals-style → schema v1

| Source | Target | Status |
|--------|--------|--------|
| `direction` | `direction` | direct |
| `entry` (number) | `entry_min`/`entry_max` + `MARKET` | direct |
| `entry` `{min,max}` | `entry_min`/`entry_max` + `LIMIT_ZONE` | supported |
| `sl` | `stop_loss` | direct |
| `tps[]` | `take_profit_levels` | direct |
| `published_at` | `published_at_utc` | direct (preserved on updates) |
| `updates[].at` | `last_updated_at_utc` (child) | direct |
| `updates[].kind=sl_modified` | `MODIFIED` + `update_reference` | supported |
| `updates[].kind=cancelled` | `CANCELLED` + `update_reference` | supported |
| `msg_id` / `update_id` | `original_message_reference` | direct |
| — | `permission_reference` | **injected** |
| — | `data_provenance` | **injected** `SYNTHETIC_FIXTURE` |

## Provenance rules

- Synthetic audit records use `data_provenance=SYNTHETIC_FIXTURE`
- `permission_reference.covers_ai_ml=false`
- Original `published_at_utc` must never be overwritten by update timestamps

## Machine-readable copy

See `reports/phase15b/field_mapping.json`.
