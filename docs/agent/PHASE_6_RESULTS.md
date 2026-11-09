# Phase 6 results

Finding class: **exploratory architecture**. Not a trading experiment. Not production-ready. Not live-ready.

Machine-readable: `reports/phase6/architecture_validation.json`.

## Repository

- Branch: `cursor/phase6-agent-architecture`
- Working tree: no tracked files modified; Phase 2–6 source/docs untracked
- Files created: `src/phase6/**`, `docs/agent/PHASE_6_*.md`, `reports/phase6/architecture_validation.json`
- Files modified: **none** of the existing Phase 1–5 datasets, labels, splits, models, reports, or `src/features_m5.py`
- Push status: **not pushed**

## Safety

- Holdout open attempts: **0**
- CSV reads during validation: **none**
- Maximum market timestamp accessed: **none** (no price files parsed)
- Frozen Phase 1–5 hashes: **unchanged**
- Live trading: **none**
- MT5 orders: **none**
- NY-SELL retested: **no**

## Architecture

| Piece | Role |
|---|---|
| Observation | Frozen decision-time market state + approved features. Outcome fields rejected. |
| Predictor | ABC (`fit`, `predict`, `predict_proba`, `metadata`). `NullPredictor` shipped; no production fit. |
| Uncertainty | Separate object (training-time penalty). Not future residuals. |
| Decision Engine | Maps prediction + uncertainty + cost estimates → BUY / SELL / WAIT. Does not train. |
| Risk Gate | ALLOW / BLOCK only. Default WAIT-only because champion is `no_model`. Cannot flip WAIT into BUY/SELL. |
| Journal | Decision-time row without realized outcome. Enrichment is a later separate row. |
| Outcome | Created only after the 12-bar horizon. |
| Experience | Observation + prediction + decision snapshots plus later realized outcome. |
| Model Registry | EXPERIMENTAL / VALIDATED / CANDIDATE / REJECTED / PRODUCTION. PRODUCTION raises in Phase 6. |
| Replay | Chronological only. Builder sees `timestamp <= t`. |

## Tests

| | |
|---|---:|
| Total | 29 |
| Passed | 29 |
| Failed | 0 |
| Skipped | 0 |

Synthetic in-memory fixtures only. Not trading evidence.

## Leakage controls

| Surface | Control |
|---|---|
| Observation | Forbidden keys (`realized_*`, `outcome_*`, `future_*`, `net_r`, `exit_reason`, …); `available_history_end == t`; cutoff check |
| Prediction | `ScriptedPredictor.predict` refuses timestamps inside the training window; `NullPredictor.fit` refuses to train |
| Decision | Accepts `Observation` only; no outcome attributes |
| Risk Gate | Refuses post-cutoff timestamps; does not inspect future outcomes; cannot change direction |
| Journal | Decision-time allowlist excludes realized outcome; attach requires completed horizon |
| Training | Phase 6 does not train; registry forbids `PRODUCTION`; OOS/holdout not used for selection |

## Limitations

Phase 6 does **not** establish a profitable trading edge.

It does not:

- beat Phase 2/3 economics
- revive or replace NY-SELL
- promote a champion
- emit live signals
- retrain on a schedule yet
- prove that a future model will pass G1–G5

The default signal under the current champion is WAIT. That is protocol, not an edge.

## Final status

**PHASE 6 ARCHITECTURE COMPLETE — NO TRADING EDGE CLAIM**
