# Phase 4 results

Finding class: **exploratory**. No new trading model. Not production-ready. Not live-ready.

Outer sample: Phase 2 WF2+WF3, **12,156** timestamps, 2026-07-23 11:25 → 2026-09-29 17:50, 49 trading days in the nested outer window. Costs already inside `net_r`. Seed 42. Catalogue: 38 predeclared side × regime slices. BH-FDR q = 0.10.

Machine-readable: `reports/phase4/regime_results.json`.

## Coverage

- Approved feature file: 2026-02-16 through cutoff. Phase 2 OOS used here: 2026-06-19 → 2026-09-29 (73 calendar days).
- Phase 1 MT5 probe: earliest **real** window (`n ≥ 100`) starts **2025-06-02 01:30**. Earlier years return a one-bar quirk. Those extra months were **not** added (no download).
- Research history is months, not years. That is enough to see that pooled Phases 1–3 lose after costs, and **not** enough to confirm a seasonal NY-session edge.

Insufficient coverage can hide a real edge or create a short-sample mirage. It does not, by itself, create a tradable rule.

## Data quality (inherited, not rewritten)

- 3,840 ineligible side-outcome rows (gap / incomplete 12-bar window).
- 58 gap-crossing backtest trades remain outside labels.
- 72 OOS bars with `minutes_since_prev_bar > 5` (session reopens).
- Original `hour_utc` was Athens wall-clock mislabeled as UTC; this phase uses **corrected** session/hour columns only.

None of these issues reverse the pooled after-cost loss in Phases 1–3. They do mean session studies on the uncorrected clock would have been wrong.

## Session mixing (outer OOS, always-take that side)

Mean net R after costs:

| Session | BUY n | BUY mean R | SELL n | SELL mean R |
|---|---|---|---|---|
| off_hours | 1,152 | −0.030 | 1,152 | −0.097 |
| asia | 4,032 | −0.126 | 4,032 | −0.001 |
| london | 2,923 | −0.073 | 2,923 | −0.044 |
| london_ny_overlap | 2,339 | +0.011 | 2,339 | −0.102 |
| new_york | 1,710 | −0.139 | 1,710 | **+0.036** |

Asia BUY (−0.126R) and NY BUY (−0.139R) dominate the pooled drag. Mixing sessions in one model is a real structural problem. Isolating NY SELL is the only session×side cell with **both** outer folds positive.

## The one promising slice (not confirmed)

`regime_session:new_york:SELL` — unconditional SELL on every NY-session timestamp (corrected clock).

| | Pooled | WF2 | WF3 |
|---|---|---|---|
| n | 1,710 | 864 | 846 |
| Mean R | +0.036 | +0.057 | +0.014 |
| Net USD/oz | +435 | — | — |
| PF | 1.09 | — | — |
| 1.5× spread-floor mean R | +0.021 | — | — |
| 2.0× spread-floor mean R | +0.005 | — | — |

Day-cluster 95% CI: **[−0.088, +0.160]**. P(mean ≤ 0) = 0.28. FDR: **fail**. Gate: **fail** (CI and FDR).

E1 trades inside NY (diagnostic, not in the family): 1,278 trades, mean R +0.021, CI **[−0.131, +0.165]**. Weaker than always-SELL, still unconfirmed.

## Other positive pooled means (not both folds)

Thu SELL +0.033, Tue SELL +0.025, Wed BUY +0.023, overlap BUY +0.011, UTC 00–07 SELL +0.007. Each fails fold consistency and/or CI. They are **not** promoted.

Vol terciles and EMA trend: no slice cleared both folds and a positive CI.

## Cost stress

Approved costs are already in the targets. Extra spread-floor stress does not create an edge. NY SELL remains slightly positive at 1.5× and 2.0× in this sample, but the CI at 1.0× already includes 0, so cost robustness is not confirmatory.

## Why Phases 1–3 looked uniformly negative

The pooled OOS mean is a mixture of strongly negative cells (Asia BUY, NY BUY, overlap SELL) and one mildly positive cell (NY SELL). A single model trained on all sessions averages those together. That is **mixing**, not proof that NY SELL would pass a holdout or a second year.

## Gate

0 / 38 slices passed. 1 / 38 promising-unconfirmed. Phase 1 permutation A remains `not_run`.

## Conclusion

**PROMISING BUT UNCONFIRMED**

NY-session SELL is the only predeclared cell with positive mean R in both outer folds after costs. The uncertainty interval includes zero, FDR fails, the sample is one summer of gold, and coverage is short. It is **not** a credible conditional edge and is **not** a live rule.
