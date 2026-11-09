# Phase 18 — Multi-Horizon Shadow Signals, Outcome Learning, Daily Discord Reporting

**Recipe:** `phase18_multi_horizon_shadow_learning_v1`  
**Branch:** `cursor/phase18-multi-horizon-shadow`

## Objective

Extend the Phase 17 Discord shadow loop so experimental H13_C decisions are evaluated across independent M5 horizons, with clear Discord wording, outcome learning, and a daily PKT monitoring report.

```text
Observation
→ H13_C experimental prediction
→ decision/gate (production WAIT)
→ shadow journal
→ Discord signal (immediate)
→ future market outcomes (H1/H2/H3/H6/H12)
→ experience memory (AGENT_SHADOW vs HISTORICAL_HYPOTHETICAL)
→ controlled learning/evaluation (no auto-promote)
```

## Horizon definitions

| Horizon | M5 bars | Label | Approx duration |
|---------|--------:|-------|-----------------|
| H1 | 1 | 5M | 5 minutes |
| H2 | 2 | 10M | 10 minutes |
| H3 | 3 | 15M | 15 minutes |
| H6 | 6 | 30M | 30 minutes |
| H12 | 12 | 60M | 60 minutes |

Each BUY/SELL decision creates **independent** pending outcomes for all five horizons. Longest horizon is **not** assumed best.

## Signal timing

Do **not** wait for any horizon before the initial Discord signal.

Example:

```text
17:35 PKT → M5 closes → H13_C experimental decision → journal → Discord signal
```

Outcomes are evaluated later from actual M5 candle availability (not wall-clock timers alone).

## Expected Horizon meaning

**Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.**

Discord BUY/SELL signals use wording such as:

- `Expected Horizon: …`
- `Expected Outcome Check: HH:MM PKT`

They must **not** say “BUY will hit target in 15 minutes” or similar guarantee language.

### Selected Horizon policy

No validated horizon-selection rule exists yet.

- `Selected Horizon: NOT ESTABLISHED`
- `Expected Horizon: NOT ESTABLISHED`

Signals list per-horizon expected outcome-check times and a horizon board of the experimental action. Do not invent “longest BUY wins” or other arbitrary selection rules.

## Outcome timing

Approximate eligibility from decision close + horizon minutes (messaging), with actual finalize requiring contiguous M5 bars:

```text
Signal 17:35 PKT
H1  → ~17:40
H2  → ~17:45
H3  → ~17:50
H6  → ~18:05
H12 → ~18:35
```

## TP/SL methodology

Reuses the validated cost-aware triple-barrier rules (parameterized horizon bars; does not rewrite `backtest_rf_m5.simulate_trade`):

- Entry at next bar open with spread floor + per-side costs
- TP = 1.5×ATR(14), SL = 1.0×ATR(14) from entry fill
- Same-candle: SL checked before TP (conservative adverse)
- Gap open beyond SL fills at worse open
- If neither barrier hits within horizon bars → `TIME` / `TIMEOUT` at horizon close

H12 (12 bars) preserves established 60-minute behavior shape.

## Outcome states

| State | Meaning |
|-------|---------|
| `PENDING` | Horizon window not yet available |
| `PASS` | TP barrier completed |
| `FAIL` | SL barrier completed |
| `TIMEOUT` | No TP/SL within horizon (`TIME` exit) |
| `N_A_WAIT` | WAIT is not a trade |

WAIT creates **no** trade outcome rows.

## Discord formats

### Signal (BUY/SELL)

```text
EXPERIMENTAL SHADOW SIGNAL — NOT A LIVE TRADING SIGNAL
…
Selected Horizon: NOT ESTABLISHED
Expected Horizon: NOT ESTABLISHED
Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit.
Expected Outcome Checks (PKT): …
Strategy: H13_C
Status: EXPERIMENTAL
Production Action: WAIT
Champion: NO_MODEL
```

### Outcome

```text
SHADOW OUTCOME
Horizon: 15M
Outcome: PASS|FAIL|TIMEOUT
…
Status: EXPERIMENTAL
NOT A LIVE TRADING RESULT
```

### Daily report (Asia/Karachi, default 23:59 PKT)

Aggregates by **decision** PKT calendar day. Pending stay `PENDING` (including late signals whose 60M window crosses midnight). Idempotent `daily_shadow_YYYY-MM-DD`.

## Experience separation

| Source | Store |
|--------|-------|
| `HISTORICAL_HYPOTHETICAL` | `historical_hypothetical_experience.jsonl` |
| `AGENT_SHADOW` | `agent_shadow_experience.jsonl` |

Both PASS and FAIL (and TIMEOUT when finalized) are retained for shadow experience. Sources are never silently merged.

## Controlled learning

New experience feeds evaluation only. **No** automatic retrain/promote. Champion remains `NO_MODEL`. H13_C remains `EXPERIMENTAL`. Production `final_action` remains `WAIT`.

## Restart / recovery / idempotency

On startup:

1. Load pending decisions/outcomes  
2. Evaluate newly eligible horizons from cached/available M5 bars  
3. Record finalized outcomes + shadow experience  
4. Send only missing Discord notifications  
5. Continue observation  

Deterministic IDs:

- Signal: `p18_dec_{bar_open}`
- Horizon outcome: `{decision_id}__{H*}`
- Daily report: `daily_shadow_{YYYY-MM-DD}`

## Bounded execution

```text
# Ready only (default) — no MT5, no Discord
python src/phase18/run_phase18.py

# Explicit bounded run
python src/phase18/run_phase18.py --run-bounded --max-candles 3 --discord-live

# Offline dry-run Discord
python src/phase18/run_phase18.py --run-bounded --max-candles 3 --dry-run-discord
```

Default CLI remains readiness-only. Importing the module does not start MT5.

## Safety

- Do not modify protected Phase 16A / 16B / Phase 17 core hashes
- No holdout access
- MT5 read-only only when explicitly `--run-bounded`
- No broker orders
- No Discord webhook secrets in logs/reports
- No package installs / no GitHub push from this phase

## Package layout

```text
src/phase18/
docs/agent/PHASE_18_MULTI_HORIZON_SHADOW_LEARNING.md
docs/agent/PHASE_18_RESULTS.md
reports/phase18/
src/data/phase18/
```
