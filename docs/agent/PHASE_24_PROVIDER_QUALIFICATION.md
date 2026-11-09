# Phase 24 — Provider Qualification

**Recipe:** `phase24_provider_arm64_qualification_v1`  
**Branch:** `cursor/phase24-provider-arm64-qualification`  
**Final decision:** **`PROVIDER_BLOCKED`**

No trading-edge claims. No OCI deploy. No H13_C / threshold changes. No Phase 16A–23 source edits.

## Method

1. Re-evaluate Phase 23 candidates using **official documentation** (not marketing alone).  
2. Discover additional free candidates (notably **Dukascopy public historical**).  
3. Where possible without account creation, measure a **real sample** against project MT5 reference data.  
4. Qualify only if **all mandatory gates + actual data validation** pass.

## Mandatory gates

XAUUSD · free-plan eligibility · historical M5 · live/streaming · bid/ask or spread · UTC timestamps · rate limits · API restrictions · licensing · retention/depth · **actual data validation**.

## Results summary

| Provider | Verdict | Key evidence |
|----------|---------|--------------|
| **AlgoSpecial** | **NOT_QUALIFIED** | Official docs: broker-server time (not UTC); free preview caps. **Measured** 2026-02-16/17 sample vs MT5: median \|Δclose\| ≈ **$12**, max ≈ **$74**; spread medians **4 vs 240** (incompatible units/scale). Parity **FAIL**. |
| Dukascopy public historical | NOT_QUALIFIED | Docs/tools: free UTC XAUUSD M5, bid/ask sides. **No Phase 24 download/parity** → cannot qualify. Live cloud stream not evidenced. |
| TickFeed | NOT_QUALIFIED | Usage-priced; not Always Free. |
| Twelve Data Basic | NOT_QUALIFIED | Key required; spread weak; commodities tier ambiguity; no measured sample (no account). |
| Finnhub Free | NOT_QUALIFIED | FX/metals candles commonly paid-gated. |
| biquote | NOT_QUALIFIED | Marketing-heavy; licensing/UTC insufficient — not qualified on claims. |
| V2BOT | NOT_QUALIFIED | Incomplete public contract. |
| Local MT5 | REFERENCE_ONLY | Compatible reference; **not** Linux ARM64 cloud runtime. |

## Selected provider

**None.**

## Adapter contract

Isolated provider-neutral interface implemented under `src/phase24/adapter.py` (offline-validated):

Normalized fields: `symbol`, `timeframe`, `timestamp_utc`, `open`, `high`, `low`, `close`, `volume`, `bid`/`ask`/`spread`, `source_id`.

Rejects/flags: incomplete, invalid OHLC, duplicates, out-of-order; flags missing gaps.

## Blockers (explicit)

1. No free provider passed measured MT5 parity + UTC + live + licensing together.  
2. AlgoSpecial — only free no-key sample measured — **failed parity hard**.  
3. Dukascopy remains the strongest **unvalidated** historical candidate; validation requires a future controlled download phase (still no threshold recalibration until gates pass).

## Recommended next phase

**Phase 25 (candidate):** Dukascopy historical fetch harness + multi-day MT5 parity (approved period only) **or** operator-approved paid provider with Always Free budget exception — still WAIT-only / NO_MODEL / no holdout / no recalibration until parity PASS.
