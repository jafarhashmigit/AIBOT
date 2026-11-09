# Phase 15B — Signal Schema Compatibility Audit

**Recipe:** `phase15b_schema_compatibility_v1`  
**Target schema:** `phase15a_signal_schema_v1`  
**Verdict:** `COMPATIBLE_WITH_INJECTION`  
**Champion:** `NO_MODEL` (unchanged)

## Scope

Audit synthetic **VasilyTrader-style** and **AnabelSignals-style** formats against the existing Phase 15A normalized schema.

- Synthetic fixtures only
- No Telegram / external provider message access
- No real provider content stored
- No backtesting or model training
- Phase 1–15A files not modified

## Styles audited

### VasilyTrader-style

Fields exercised: direction (`side`), exact `entry`, `sl`, single `tp`, plus cancel / SL-modify / incomplete cases.

**Mapping notes**

- Exact entry → `entry_type=MARKET`, `entry_min=entry_max=entry`
- Single `tp` → `take_profit_levels=[tp]`
- `permission_reference` and `data_provenance` are **not** in the source style; ingestion must inject them (`SYNTHETIC_FIXTURE` for this audit)

### AnabelSignals-style

Fields exercised: `direction`, `entry` (scalar or `{min,max}` zone), `tps[]`, `sl`, `updates[]` (SL modify, cancel), incomplete.

**Mapping notes**

- Multi-TP maps directly to `take_profit_levels`
- Updates emit child records; `published_at_utc` preserved from original; `last_updated_at_utc` from update time
- Zone entry → `LIMIT_ZONE`

## Missing / ambiguous / optional

| Category | VasilyTrader-style | AnabelSignals-style |
|----------|--------------------|---------------------|
| Missing in source | permission, provenance, multi-TP, zones | permission, provenance |
| Ambiguous | exact entry = market vs limit-at-price; incomplete vs ambiguous | unknown update kinds; empty TP list |
| Optional | `updated_at`, `prior_sl`, parent id | `updates[]`, zone entry, `update_id` |

## Compatibility verdict

Both styles are **compatible** with `phase15a_signal_schema_v1` when AIBOT injects required provenance and permission fields. No schema-blocking gaps found for BUY, SELL, multi-TP, modified SL, cancellation, or incomplete cases under synthetic tests.

## Protections

- Holdout access: 0
- MT5 connections: 0
- Broker orders: 0
- Phase 14 + 15A protected hashes verified
- GitHub push: not performed

## Stop

Audit complete. No Phase 15C started automatically.
