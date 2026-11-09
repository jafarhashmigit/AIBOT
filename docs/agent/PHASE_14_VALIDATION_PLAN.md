# Phase 14 validation plan (pre-declared)

Candidate under test: **`H13_C_H1_PULLBACK`** (Phase 13 EXPERIMENTAL).

Champion remains **`NO_MODEL`**. No BUY/SELL enablement. No Stage B. No holdout. No MT5.

## Frozen economic definition (from Phase 13 plan)

- **H1 trend:** last fully closed H1 bar; trend up iff `h1_close > h1_ema20`, else down. EMA20: SMA seed on first 20 closes, then recursive EMA with α = 2/21.
- **M5 pullback BUY:** H1 up AND `close_to_ema_20 <= train_p25` AND `ema_9_20_spread > 0`.
- **M5 pullback SELL:** H1 down AND `close_to_ema_20 >= train_p75` AND `ema_9_20_spread < 0`.
- **Train cuts:** expanding feature history with 12-bar purge before each Phase 2 WF eval start; percentiles on `close_to_ema_20` only for H13_C.
- **Entry:** decision at completed M5 bar `decision_time` (feature timestamp).
- **Exit / TP/SL / costs:** existing eligible `m5_side_outcomes` `net_r` / `net_pnl` / `initial_risk` (costs already inside). Incomplete or gap-crossing rows excluded at load.
- **Universe:** Phase 2 OOS timestamps through `2026-09-29 17:50:00`.

## Independence rule

Phase 14 reimplements H1 EMA, train percentiles, signal selection, and trade journaling under `src/phase14/`.

Phase 13 modules may be used **only as a reference comparator**, never as the validated implementation path.

Shared utilities allowed: `phase3.nplib` CSV/bootstrap helpers (documented, audited).

## Confirmatory criteria (must all pass for `READY_FOR_CONTROLLED_PAPER_RESEARCH`)

1. **Replication:** independent trade set matches Phase 13 reference on `(decision_time, side)` with ≤ 0 mismatches; n = 226 (±0).
2. **No leakage:** features and H1 context use only information available at decision time; no holdout; max decision ≤ 17:50.
3. **Walk-forward:** mean R after costs **> 0 in WF1, WF2, and WF3** (each with n ≥ 30).
4. **Cost robustness (confirmatory):** pooled mean R > 0 at 1.0×, 1.25×, 1.5× spread-floor stress.
5. **Statistics (confirmatory):** day-cluster bootstrap 2000 draws, seed 42; CI lower bound **> 0**; P(mean R ≤ 0) < 0.05.
6. **Sample:** ≥ 100 trades; ≥ 40 distinct decision days; H1 coverage ≥ 95%.

If any confirmatory criterion fails → cannot be `READY_FOR_CONTROLLED_PAPER_RESEARCH`.

## Exploratory sensitivity (predeclared limited grid; not used to invent a new strategy)

| Knob | Values | Role |
|---|---|---|
| Pullback quantile | p20, **p25**, p30 | exploratory |
| H1 comparison | **`>`**, `>=` | exploratory |
| Entry delay | **0**, +1 M5 bar | exploratory |
| Extra slippage USD | 0, 0.05 | exploratory |
| Session slice | all / NY / non-NY | diagnostic |
| ATR tercile of trade bar | low/mid/high | diagnostic |

Do **not** promote the best grid cell. Report whether the primary rule’s sign is stable.

## Decision outcomes

- `REJECTED` — not reproducible, or confirmatory evidence clearly negative / collapsed.
- `RETAINED_EXPERIMENTAL` — reproducible but confirmatory gate incomplete (e.g. one WF window negative, CI includes 0).
- `READY_FOR_CONTROLLED_PAPER_RESEARCH` — all confirmatory criteria pass. Still **not** production; still **not** live BUY/SELL; champion stays `NO_MODEL`.

## Known fragility entering this phase

Phase 13: WF1 −0.108, WF2 +0.188, WF3 +0.054; CI [−0.138, +0.217]; FDR fail. Expectation: confirmatory all-windows rule likely fails unless replication reveals a scoring error.
