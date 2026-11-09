# Phase 6 architecture

Status: implemented as research-only interfaces. No trading edge is claimed.

Prediction, decision, and risk control are separate objects. They are not one opaque model.

```text
                ┌──────────────────┐
                │ Historical Market│
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │ Observation      │
                │ Builder          │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │ Predictor        │
                └────────┬─────────┘
                         ↓
              ┌──────────────────────┐
              │ Prediction +         │
              │ Uncertainty          │
              └──────────┬───────────┘
                         ↓
                ┌──────────────────┐
                │ Decision Engine  │
                └────────┬─────────┘
                         ↓
                ┌──────────────────┐
                │ Risk Gate        │
                └────────┬─────────┘
                         ↓
                 BUY / SELL / WAIT
                         ↓
                ┌──────────────────┐
                │ Decision Journal │
                └────────┬─────────┘
                         ↓
                  Future Outcome
                         ↓
                ┌──────────────────┐
                │ Experience Store │
                └────────┬─────────┘
                         ↓
                 Future Evaluation
                 / Retraining
```

## Module map

| Piece | File |
|---|---|
| Observation, Prediction, Uncertainty, versions | `src/phase6/schemas.py` |
| Information boundary | `src/phase6/information_boundary.py` |
| Predictor ABC + Null / Scripted | `src/phase6/predictor.py` |
| Outcome (delayed) | `src/phase6/outcome.py` |
| Decision engine | `src/phase6/decision_engine.py` |
| Risk gate | `src/phase6/risk_gate.py` |
| Journal | `src/phase6/journal.py` |
| Experience | `src/phase6/experience.py` |
| Model registry | `src/phase6/model_registry.py` |
| Replay | `src/phase6/replay.py` |

Existing Phase 1–5 files are not modified. `features_m5.py` is referenced by version string only.

## Predictor replacement

`DecisionEngine` depends on `Prediction`, not on Random Forest. A later Logistic Regression, GBM, or other research model can implement `Predictor.fit / predict / predict_proba / metadata` without rewriting the decision layer.

Phase 6 ships `NullPredictor` (uniform probabilities, EV = 0) and `ScriptedPredictor` (tests). No production model is trained.

## Default risk posture

Champion = `no_model`. Risk gate `wait_only=True`. Directional raw decisions are blocked. That is the Phase 2–5 evidence, not a new trading rule.

## What this does not prove

Phase 6 does not establish a profitable trading edge. It does not revive NY-SELL. It does not authorize live signals.
