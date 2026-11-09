# Phase 23 — Market Data Provider Assessment

**Recipe:** `phase23_cloud_architecture_design_v1`  
**Mode:** Design / public-documentation review only  
**No accounts created. No provider APIs contacted from AIBOT runtime.**

**Selection decision:** **NO PROVIDER SELECTED** — qualification incomplete → **PROVIDER_BLOCKER**.

## Qualification criteria (all must pass)

| ID | Criterion | Pass rule |
|----|-----------|-----------|
| Q1 | Free-plan availability | Sustainable Always Free–compatible cost (no surprise billing) |
| Q2 | XAUUSD instrument | Explicit XAUUSD / XAU/USD gold spot or CFD documented |
| Q3 | Historical M5 | Enough history for warmup (ATR14 + H1 trend) and parity window |
| Q4 | Live / streaming | Completed M5 bars available for continuous forward observation |
| Q5 | Timestamp / TZ | Deterministic conversion to UTC; documented precision |
| Q6 | Bid/ask vs mid OHLC | Construction documented; compatible with feature pipeline |
| Q7 | Spread | Spread or bid/ask available (cost assumptions need inputs) |
| Q8 | Rate limits | Supports ≥1 completed-M5 poll per 5 minutes + H1 refresh |
| Q9 | Auth / eligibility | Clear account rules; operable from OCI egress |
| Q10 | Licensing | Allows automated research/shadow journaling; no redistribution traps |
| Q11 | Reliability | Documented gaps/outages; stale data must be detectable |
| Q12 | MT5 parity | Separate empirical parity vs project MT5 dataset (**not done in Phase 23**) |

**Hard rejects:** fabricate candles; substitute D1 for M5; silently reuse stale quotes; auto-inherit MT5 threshold validity.

---

## Candidate assessments (public docs, 2026-11)

### 1) AlgoSpecial OHLC API

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | Free anonymous preview; paid full downloads | Partial |
| Q2 | XAUUSD documented | Pass |
| Q3 | M5 listed; free preview row/date caps (docs conflict 2k/31d vs larger caps) | Partial |
| Q4 | Historical query API; continuous live forward not clearly guaranteed | Fail |
| Q5 | **Broker server time, not UTC** — conversion required, source TZ broker-dependent | Fail |
| Q6 | OHLC stored as feed prices; digits note Exness-style 3dp | Partial |
| Q7 | Spread field may be 0 on legacy exports | Fail |
| Q8 | 60/min, 1000/day/IP — OK for M5 poll if stable | Pass |
| Q9 | No key for preview | Pass |
| Q10 | Free research OK; no resell as data service; as-is warranty | Partial |
| Q11 | Quality scores published; outage SLA unclear | Partial |
| Q12 | Not measured | Fail |

**Verdict:** **NOT QUALIFIED** (UTC/live/spread/parity gaps).

### 2) TickFeed (`api.tickfeed.pro`)

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | Usage-priced (~$0.002/request); $25 promo credit time-limited — not Always Free sustainable | Fail |
| Q2 | XAUUSD candles | Pass |
| Q3 | M5 history documented (months, not multi-year on free credit) | Partial |
| Q4 | REST candles with `complete` flag; UTC labeling | Pass |
| Q5 | UTC start-labeled candles | Pass |
| Q6 | OHLC + spread fields | Pass |
| Q7 | Spread included | Pass |
| Q8 | Depends on credit balance | Partial |
| Q9 | API key / account | Partial |
| Q10 | Commercial API terms apply | Partial |
| Q11 | Gap endpoint documented | Pass |
| Q12 | Not measured | Fail |

**Verdict:** **NOT QUALIFIED** for zero-cost Always Free constraint (Q1).

### 3) Twelve Data Basic

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | Free Basic: 8 credits/min, **800/day** | Partial |
| Q2 | XAU/USD commodity / trial symbol documented | Partial |
| Q3 | Intraday history claimed; free depth/limits unclear for metals | Partial |
| Q4 | `/time_series` intervals include minutes; streaming WS trial-limited | Partial |
| Q5 | Datetime + unix; timezone parameter exists — must pin UTC | Partial |
| Q6 | Typically mid/aggregated OHLC; bid/ask/spread not first-class | Fail |
| Q7 | Spread not guaranteed | Fail |
| Q8 | 800/day allows ~288 M5 polls/day with margin if 1 credit each | Pass* |
| Q9 | API key required | Pass |
| Q10 | Free plan internal/non-display; commercial may need paid | Partial |
| Q11 | 429 on credit exhaustion; SLA not on free | Partial |
| Q12 | Not measured | Fail |

**Verdict:** **NOT QUALIFIED** (spread/construction + metals free-tier uncertainty + no parity).

### 4) Finnhub Free

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | Free tier exists | Pass |
| Q2 | FX gold often via `OANDA:XAU_USD` | Partial |
| Q3–Q4 | Forex/metals candles frequently **paid-gated** on current free plans | Fail |
| Q5 | Unix timestamps when available | Partial |
| Q6–Q7 | Candle OHLC; spread unclear on free | Fail |
| Q8 | 60/min | Pass |
| Q9 | API key | Pass |
| Q10 | Personal free; commercial restricted | Partial |
| Q11 | 403/429 behaviors documented by community | Partial |
| Q12 | Not measured | Fail |

**Verdict:** **NOT QUALIFIED**.

### 5) biquote.io

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | Claims free, no key | Pass* |
| Q2 | XAUUSD listed | Pass |
| Q3 | OHLC endpoints claimed; long history depth not independently verified | Partial |
| Q4 | REST + SignalR streaming claimed | Pass* |
| Q5 | TZ/precision not fully specified in landing docs | Fail |
| Q6 | Mid-oriented ticks; CFD from **some MT5 feed** (not this project's broker) | Partial |
| Q7 | Bid/ask on some widgets; pipeline spread guarantee unclear | Partial |
| Q8 | Claims 15k req/min/IP | Pass* |
| Q9 | None | Pass |
| Q10 | Licensing/redistribution terms not clearly published on landing page | Fail |
| Q11 | No contractual SLA; single-vendor risk | Fail |
| Q12 | Different MT5 feed ≠ project MT5 parity | Fail |

**Verdict:** **NOT QUALIFIED** until licensing, UTC contract, and empirical parity are proven. Treat as high operational risk despite free marketing claims.

### 6) V2BOT FX API

| Criterion | Finding | Result |
|-----------|---------|--------|
| Q1 | “API Free” with account key | Partial |
| Q2 | XAUUSD | Pass |
| Q3 | Docs emphasize last-candle testing; deep history unclear | Fail |
| Q4 | Poll last N candles | Partial |
| Q5 | `datetime` TZ unspecified | Fail |
| Q6–Q7 | OHLC + volume; no spread | Fail |
| Q8–Q11 | Insufficient public reliability/license detail | Fail |
| Q12 | Not measured | Fail |

**Verdict:** **NOT QUALIFIED**.

### 7) Local MT5 (status quo)

| Criterion | Finding | Result |
|-----------|---------|--------|
| Cloud Linux ARM64 | MetaTrader5 package / terminal **not viable** | Fail (for cloud target) |
| Data compatibility | Source of frozen thresholds | Pass (local only) |

**Verdict:** Remains the **compatibility reference**, not the cloud runtime provider.

---

## Compatibility risks (MT5 vs any candidate)

Documented from code + general broker-feed reality:

| Topic | Project MT5 baseline | Cloud risk |
|-------|----------------------|------------|
| Price level | Broker CFD gold quote | Other feeds can differ by dollars/pips |
| Spread | Observed via MT5 bars / floor `0.15` USD (`POINT_SIZE=0.01`, 15 points) | Missing spread → invalid cost/ATR contexts |
| Digits / point | Assumed `0.01` point size in Phase 18 | 3-digit feeds change R multiples |
| Candle build | Completed M5 from MT5 rates | Mid vs bid OHLC shifts features |
| UTC / boundaries | `detect_timestamp_mode` UTC vs Europe/Athens | Wrong TZ → wrong H1 trend & campaign resume |
| Features | `close_to_ema_20`, `ema_9_20_spread` on MT5 closes | Distribution shift → frozen cuts fire rates change |
| Thresholds | WF3 q25/q75 on MT5 train | **Must not auto-transfer**; no recalibration in Phase 23 |

---

## Alternatives if free providers remain blocked

1. **Hybrid:** Keep MT5 read-only on Windows PC for data only; cloud runs decision/journal/Discord (still not “fully cloud”).
2. **Paid Always-budget provider** with explicit operator approval (breaks zero-cost constraint).
3. **Broker REST** from a cloud-allowed practice account (still broker-coupled; parity required).
4. **Stay local** Phase 22 campaign until a qualified provider exists.

---

## Decision

| Field | Value |
|-------|-------|
| Selected provider | **None** |
| Qualification status | **BLOCKED** |
| Architecture impact | Cloud design proceeds with `MarketDataProvider` interface; runtime blocked until Q1–Q12 pass |
| Next required work | Offline/live qualification harness + MT5↔provider parity report (future phase) |
