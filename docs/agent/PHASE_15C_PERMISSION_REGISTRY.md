# Phase 15C — Permission Registry

**Registry version:** `permission_registry_v1`  
**Recipe:** `phase15c_permission_readiness_v1`  
**Champion:** `NO_MODEL`

## Purpose

Track explicit, evidence-backed permissions for five external XAUUSD signal providers. Public channel availability and promotional statements never imply permission.

## Tracked scopes

| Scope | Meaning |
|-------|---------|
| `historical_message_access` | Access to historical signals / authorized export |
| `signal_storage` | Store signals in research archive |
| `backtesting_evaluation` | Independent performance evaluation |
| `data_retention` | Retention window / deletion rules |
| `ai_ml_training` | AI/ML training, fine-tuning, validation, benchmarking |

Also tracked: permission expiry, evidence/reference, identity verification, review status.

## Allowed statuses

`NOT_REQUESTED` · `REQUESTED` · `PARTIALLY_GRANTED` · `GRANTED` · `REJECTED` · `EXPIRED` · `REVOKED`

## Live provider posture (Phase 15C)

All five providers initialize to **`NOT_REQUESTED`**:

1. VasilyTrader — `@vasilytrading`
2. AnabelSignals — `@anabelsignals`
3. Gold Trader Sunny — `@goldtradersunny`
4. FX Premiere — `@forexsignalstrialgroup`
5. United Kings — `@unitedkings1`

No requests were sent. No grants recorded.

## Fail-closed enforcement

- No evidence → REJECT  
- Expired → REJECT  
- Revoked → REJECT  
- Backtesting must be explicitly GRANTED  
- AI/ML must be independently GRANTED  
- Storage grant ≠ backtesting grant  
- Backtesting grant ≠ AI/ML grant  
- One provider’s permission never authorizes another provider’s data  

Synthetic scenarios exercise these rules without claiming real grants.

## Isolation

External provider data remains `EXTERNAL_PROVIDER_SIGNAL`, separate from `HISTORICAL_HYPOTHETICAL`, `AGENT_PAPER`, and `FORWARD_SHADOW`.
