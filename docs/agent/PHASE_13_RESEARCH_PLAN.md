# Phase 13 research plan (pre-registered)

Declared **before** economic scoring. Finding class: exploratory discovery. Not production. Not live trading. Champion remains `NO_MODEL` unless an evidence gate is met.

## Protected boundaries

- Cutoff: `2026-09-29 18:50:00 UTC`
- Max decision timestamp used: `2026-09-29 17:50:00` (matches Phase 2 OOS end)
- Holdout `xauusd_m5_test.csv`: never opened
- No MT5, no broker orders, no Stage B, no package changes, no GitHub push
- Phase 1–12C artifacts frozen

## Part A — Why prior work failed (do not repeat as-is)

| Prior | Result | Why not repeated blindly |
|---|---|---|
| Phase 1 RF baseline | Losing after costs | Different task; superseded by Phase 2 labels |
| Phase 2 E1 (max pred R > 0) | Mean R −0.021; all folds negative | Baseline reference only |
| Phase 3 conservative EV / META | WAIT or outer collapse | No retune of same decision layer |
| Phase 4 session×side catalogue | NY SELL promising-unconfirmed; FDR fail | Unconditional session slice rejected after Phase 5 |
| Phase 5 NY-SELL replication | CI entirely below 0 | **Do not retest unconditional NY SELL** |
| Phase 7–9 agent / experience ridge | WAIT / no improvement | No learner retrain here |
| Phase 10–11 dual source | Paper trades = 0; no combined learner | Keep sources separate |

### Gaps remaining

- Joint **volatility × structure** rules with **train-only** cuts (Phase 4 used inner cuts for ATR terciles, but tested unconditional slices, not breakout-failure structure).
- **Multi-timeframe** H1 context on M5 decisions (H1 history exists; not used as a pullback filter in Phases 2–5).
- **Conviction-gap** overlay on Phase 2 predictions (distinct from raw E1).
- Feature families with thin economic evidence: calendar/macro overlays, Kronos forecasts — deferred (external/complex; not in this limited set).
- Sample length: research OOS is ~3 months (WF1–WF3). Meaningful for rejection; weak for confirmation. Independent long history exists for H1, but M5 labeled OOS does not extend earlier without new labeling — sufficiency call is part of the conclusion.

## Part B — Pre-registered hypotheses (exactly four)

Shared contract:

- Symbol/timeframe: XAUUSD M5
- Outcomes: existing `m5_side_outcomes` `net_r` / `net_pnl` (costs already inside)
- WAIT is a valid action
- One side per timestamp; conflict → WAIT
- Walk-forward: Phase 2 WF1/WF2/WF3 windows; 12-bar purge for train-only thresholds
- Train-only percentile cuts: never fit on the scored fold’s evaluation block
- Min pooled trades for gate consideration: 100; per-fold diagnostic floor: 30
- Bootstrap: day-cluster, 2000 draws, seed 42
- Multiple testing: BH-FDR q = 0.10 across the four hypotheses
- Cost stress: approximate 1.5× and 2.0× spread-floor by subtracting `(mult-1)*0.15/initial_risk` from `net_r` when `initial_risk > 0`
- Sensitivity: breakout lookback 12 (primary) vs 8 (diagnostic); reject if primary and sensitivity disagree on sign of pooled mean R
- Rejection if results depend on one fold, CI lower ≤ 0, FDR fail, or cost stress mean R ≤ 0

### H13_A — Volatility-contraction breakout failure

- **Hypothesis:** In low realized volatility, failed range breaks mean-revert.
- **Economic rationale:** Stops cluster beyond recent ranges; failed breaks reverse toward value.
- **Features:** `atr_14_pct`, OHLC path; train p33 ATR cut.
- **Entry:** If `atr_14_pct <= train_p33` and bar wicks beyond prior 12-bar range but closes back inside → fade (SELL after upside failure, BUY after downside failure).
- **Exit:** Existing side-outcome triple barrier (not redesigned).
- **Reject if:** gate fails or sensitivity lookback flips sign.

### H13_B — Volatility-expansion trend continuation

- **Hypothesis:** High volatility with aligned EMAs continues short-horizon directional moves.
- **Economic rationale:** Expansion regimes sustain impulse; aligned EMA stack proxies short-horizon trend.
- **Features:** `atr_14_pct` train p67; `ema_9_20_spread`, `ema_20_50_spread`.
- **Entry:** High vol + both spreads > 0 → BUY; high vol + both < 0 → SELL; else WAIT.
- **Methodological improvement vs Phase 4:** joint filter (not unconditional ATR tercile or EMA-sign alone) and train-only cuts.
- **Reject if:** gate fails.

### H13_C — H1 trend with M5 pullback

- **Hypothesis:** M5 pullbacks in the direction of the closed H1 EMA20 trend have asymmetric continuation odds.
- **Economic rationale:** Higher-timeframe drift; enter on M5 discount/premium to EMA20.
- **Features:** H1 close vs H1 EMA20 (causal, last fully closed H1); `close_to_ema_20`, `ema_9_20_spread`; train p25/p75 on `close_to_ema_20`.
- **Entry:** H1 up + deep M5 discount (`close_to_ema_20 <= p25`) + `ema_9_20_spread > 0` → BUY; symmetric SELL when H1 down.
- **Reject if:** gate fails or H1 join coverage < 95% of OOS timestamps.

### H13_D — Prediction conviction gap in mid-volatility

- **Hypothesis:** Phase 2 RF expected-R is only economically usable when side gap is large and volatility is not extreme.
- **Economic rationale:** Filters noisy near-ties and crash/spike regimes where costs dominate.
- **Features:** OOS `pred_r_rf` by side; `atr_14_pct` between train p33 and p67; pre-declared `gap_min = 0.05` (not grid-searched).
- **Entry:** If mid-vol and `|pred_buy - pred_sell| >= 0.05` and max pred > 0 → take that side; else WAIT.
- **Methodological improvement vs E1:** gap + mid-vol filter; E1 remains an untouched baseline.
- **Reject if:** gate fails.

### Baselines (not candidates)

- `B_WAIT` — always WAIT
- `B_E1` — frozen Phase 2 E1 rule on the same OOS predictions

## Part E — Candidate statuses

Only `REJECTED` / `EXPERIMENTAL` / `VALIDATED_CANDIDATE`. Never `PRODUCTION`.

`VALIDATED_CANDIDATE` requires full gate including CI lower > 0, FDR pass, cost stress, multi-fold consistency.

`EXPERIMENTAL` only if economically interesting but gate incomplete (e.g. positive folds, CI includes 0) **and** not a rejected prior hypothesis in disguise.

Champion stays `NO_MODEL` unless `VALIDATED_CANDIDATE` is achieved.

## Part F — Experience sources

`HISTORICAL_HYPOTHETICAL` and `AGENT_PAPER` remain separate. No combined learner. Paper completed trades remain zero; none are fabricated.

## Data sufficiency note

If all four hypotheses reject and the limiting factor is short OOS span rather than a clear negative CI, conclusion may be `INSUFFICIENT_DATA` or `NO_CREDIBLE_EDGE_FOUND` depending on whether estimates are informative (tight negative) or underpowered.
