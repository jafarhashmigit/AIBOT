# Phase 20A — WAIT Root-Cause Diagnostic

**Mode:** Diagnostic only  
**Trading logic changed:** No  
**MT5 / Discord / orders / holdout / packages / push:** None  

**Infrastructure diagnosis only — no trading edge claimed.**

---

## Root cause (one sentence)

**Experimental BUY/SELL never appear because `decide_h13c` returns `WAIT` with reason `h1_up_pullback_not_met` on every real Phase 16A and Phase 20 observation — the frozen WF3 pullback threshold is not met; RiskGate and Discord are not the suppressors of `experimental_action`.**

---

## Exact stage where BUY/SELL disappears

```text
M5 features + H1 trend
→ decide_h13c  ← BUY/SELL die here (experimental_action = WAIT)
→ ForwardGateAdapter  (ALLOW on raw WAIT; would BLOCK final if raw BUY/SELL)
→ production final_action = WAIT
→ Phase 20 Discord (BUY/SELL-only) sends nothing
```

| Stage | Emits BUY/SELL? | Evidence |
|-------|-----------------|----------|
| Probabilistic “raw model” scores | **N/A** | H13_C is a rule, not a classifier with BUY/SELL/WAIT probabilities |
| H13_C `decide_h13c` | **No** (0/12 Phase 20; 0/24 Phase 16A) | `decision_reason = h1_up_pullback_not_met` |
| Phase 15C permission registry | **Not in path** | `predict_h13c_experimental` never calls `evaluate_permission` |
| Phase 12C RiskGate | Does not clear experimental BUY (none exist) | Gate `ALLOW` / `raw_wait` on all observed rows |
| Production `final_action` | Always WAIT | Expected under `NO_MODEL` |
| Discord | No BUY/SELL messages | Correct given experimental WAIT |

---

## Architecture note: no raw BUY/SELL/WAIT probabilities

Live H13_C uses:

- `close_to_ema_20`
- `ema_9_20_spread`
- `h1_trend`

against **frozen WF3 q25/q75 cuts** (`FROZEN_CUTS` in Phase 16A).

There is **no** logged raw model BUY/SELL/WAIT probability in the Phase 16A/20 journals. That field is **missing by design**, not by a logging bug.

Parity smoke tests prove the rule *can* emit BUY/SELL on synthetic feature extremes; live bars simply do not reach those extremes.

---

## Frozen WF3 thresholds

| Field | Value |
|-------|------:|
| `q_low` / `q_high` | 25 / 75 |
| `close_ema_low` (BUY pullback cut) | **-0.0010069324198160867** |
| `close_ema_high` (SELL extension cut) | **0.0009989244530461683** |
| Source | `phase14_replication.json:cuts_independent.WF3` |

### BUY rule

`h1_trend == up` **and** `close_to_ema_20 <= close_ema_low` **and** `ema_9_20_spread > 0`

### SELL rule

`h1_trend == down` **and** `close_to_ema_20 >= close_ema_high` **and** `ema_9_20_spread < 0`

---

## Phase 20 real observations (n=12)

| Metric | Count |
|--------|------:|
| H13_C experimental BUY | 0 |
| H13_C experimental SELL | 0 |
| H13_C experimental WAIT | 12 |
| WAIT reason `h1_up_pullback_not_met` | 12 |
| Risk gate ALLOW | 12 |
| Risk gate BLOCK | 0 |
| Production final WAIT | 12 |
| Permission ALLOW/BLOCK | N/A (not invoked) |

### Features vs thresholds (Phase 20)

| Statistic | Value |
|-----------|------:|
| `close_to_ema_20` min / max / mean | +3.3e-05 / +0.00300 / +0.00127 |
| `ema_9_20_spread` min / max / mean | +0.00052 / +0.00122 / +0.00089 |
| `c2e <= close_ema_low` | **0 / 12** |
| `spread > 0` | **12 / 12** |
| Full BUY condition | **0 / 12** |
| Full SELL condition | **0 / 12** |

Interpretation: market context is **H1 up** with short EMA still above EMA20 (`spread > 0`), but price is **not pulled back** to the frozen q25 distance below EMA20. Closest Phase 20 `c2e` values remain **above zero**, while BUY needs ≈ **-0.10%** below EMA20.

Seven bars have `c2e >= close_ema_high`, but SELL still fails because H1 is up and `spread` is never negative.

---

## Sample-by-sample table (Phase 20)

| decision_timestamp_utc | close_to_ema_20 | ema_9_20_spread | c2e≤low | spread>0 | BUY ok | reason | exp | gate | final |
|------------------------|----------------:|----------------:|:-------:|:--------:|:------:|--------|-----|------|-------|
| 2026-11-09 13:20:00 | 0.002997 | 0.001136 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:25:00 | 0.002719 | 0.001223 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:30:00 | 0.001843 | 0.001192 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:35:00 | 0.001834 | 0.001166 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:40:00 | 0.001369 | 0.001091 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:45:00 | 0.000033 | 0.000876 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:50:00 | 0.000278 | 0.000733 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 13:55:00 | 0.001652 | 0.000778 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 14:00:00 | 0.001049 | 0.000744 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 14:05:00 | 0.000618 | 0.000666 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 14:10:00 | 0.000067 | 0.000541 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |
| 2026-11-09 14:15:00 | 0.000735 | 0.000518 | N | Y | N | h1_up_pullback_not_met | WAIT | ALLOW | WAIT |

Machine-readable copy: `reports/phase20a/phase20_sample_table.json`.

---

## Historical comparison (Phase 16A)

| Item | Phase 16A | Phase 20 |
|------|-----------|----------|
| Decision rows with features | 24 | 12 |
| Experimental BUY/SELL | 0 / 0 | 0 / 0 |
| Dominant WAIT reason | `h1_up_pullback_not_met` (24) | same (12) |
| Risk gate | ALLOW × 24 | ALLOW × 12 |
| `n_c2e_le_low` | 0 | 0 |
| `n_buy_cond` | 0 | 0 |

**Same failure point:** H13_C pullback rule not satisfied under live H1-up conditions.  
Phase 16A pilot summary also recorded experimental WAIT-only (BUY 0, SELL 0, WAIT 12 in the timed session report).

RiskGate preflight separately shows that **if** experimental BUY were produced, production `final_action` would still be WAIT (`wait_only_no_champion`). That is a **second, intentional** layer and is **not** what is currently removing experimental BUY/SELL from journals.

---

## Permission registry (Phase 15C)

Phase 15C governs **external signal-provider import** scopes. It is **not consulted** by `predict_h13c_experimental`.  
Conclusion: permission registry is **not** blocking experimental H13_C signals.

---

## Risk gate behavior

Under champion `NO_MODEL` / `wait_only`:

| Raw experimental | Gate status | Gate reason | `final_action` |
|------------------|-------------|-------------|----------------|
| WAIT | ALLOW | `raw_wait` | WAIT |
| BUY | BLOCK | `wait_only_no_champion` | WAIT |
| SELL | BLOCK | `wait_only_no_champion` | WAIT |

On all real Phase 16A/20 rows: raw = WAIT → gate ALLOW → final WAIT.  
Therefore RiskGate is **not** converting experimental BUY/SELL to experimental WAIT in these runs (none existed to convert).

---

## Missing information (explicit)

1. **No probabilistic BUY/SELL/WAIT scores** in the live journal (architecture limitation).  
2. **H1 trend object** is not stored as a full JSON column (inferred as `up` from `h1_up_pullback_not_met` / `market_regime` where present).  
3. Phase 16A timed pilot report aggregates counts but the detailed feature table above uses the on-disk `shadow_decisions.csv` (24 rows across sessions).  
4. No multi-day live distribution yet — conclusions cover available real shadow journals only.

---

## Answers to investigation questions

| Question | Answer |
|----------|--------|
| Does a raw model itself predict WAIT? | **N/A** — no classifier scores; rule outputs WAIT |
| Are H13_C thresholds never satisfied? | **Yes** for BUY on all observed bars (`c2e <= low` never true) |
| Missing/invalid features? | **No** — features present and finite |
| Permission registry blocks? | **No** — not in path |
| Risk gate converts experimental BUY/SELL → experimental WAIT? | **No** on these rows; it would only force **final** WAIT if experimental BUY/SELL appeared |
| Other integration bug suppressing signals? | **No evidence** — behavior matches coded rule + observed features |

---

## Is a future calibration experiment justified?

**Conditionally yes, as research only:** measure how often live M5/H1 states meet frozen WF3 q25/q75 pullbacks over a longer shadow window, and compare to historical WF rates — **without** loosening production thresholds, forcing signals, or claiming edge.

**Not justified** as an immediate live threshold change or strategy swap.

---

## Safety confirmation

- No H13_C threshold changes  
- No forced BUY/SELL  
- No Phase 12C / 14–20 behavior changes  
- No production WAIT weakening  
- No training, holdout, orders, Discord, MT5, packages, commit, or push  

Artifacts: `docs/agent/PHASE_20A_WAIT_ROOT_CAUSE.md`, `reports/phase20a/`.
