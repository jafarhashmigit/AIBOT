# Phase 6 agent contract

Research-only. Not live trading. Not production-ready.

The agent produces exactly one of `BUY`, `SELL`, `WAIT` at each eligible decision timestamp `t`.

```text
OBSERVE
   ↓
ESTIMATE OUTCOMES
   ↓
ESTIMATE UNCERTAINTY
   ↓
DECISION
   ↓
RISK GATE
   ↓
SIGNAL
   ↓
JOURNAL
   ↓
LATER REALIZED OUTCOME
   ↓
EVALUATION / FUTURE RETRAINING
```

## Stages

| Stage | Object | Allowed at t | Forbidden at t |
|---|---|---|---|
| Observe | `Observation` | Closed-bar OHLCV and approved features with history ≤ t | Realized R, exit reason, future bars |
| Estimate outcomes | `Prediction` | Class probabilities and expected net R from a model trained before the evaluation period | Evaluation-block outcomes |
| Estimate uncertainty | `Uncertainty` | Training-window error / penalty | Future residuals |
| Decision | `DecisionEngine.decide` | Prediction + uncertainty + cost estimates | Future candles, realized outcomes |
| Risk gate | `RiskGate.evaluate` | Operational / cost / champion checks | Changing the predicted side |
| Signal | `final_decision` | BUY / SELL / WAIT after the gate | Orders |
| Journal | decision-time row | Versions, prediction snapshot, raw and final action | Realized outcome fields |
| Later outcome | `Outcome` | After the 12-bar window is historically complete | Joining into the next Observation |
| Evaluation / retrain | scheduled, versioned | Only after OOS evaluation is recorded | Automatic per-trade retraining |

## Current honest policy

No model has passed G4/G5. The champion is `no_model`. The default risk gate is **WAIT-only**. A synthetic BUY from the decision engine is blocked unless a later phase promotes a champion.

Phase 4/5 NY-SELL is **not** a signal source.

## Outputs

A signal is a journal record, not an MT5 order. Same observation + same component versions → same `signal_id` and same `final_decision`.
