# Phase 6 learning loop

Future process. Phase 6 implements the loop as interfaces, not as an automatic trainer.

```text
Historical data
      ↓
Feature construction
      ↓
Training period
      ↓
Model
      ↓
OOS prediction
      ↓
Decision
      ↓
Future outcome
      ↓
Journal
      ↓
Evaluation
      ↓
Retraining candidate
```

## Experience

Experience means: previously observed decision + subsequently realized outcome.

```text
Experience
    observation_snapshot
    prediction_snapshot
    decision_snapshot
    realized_outcome
```

It does **not** mean the model remembers arbitrary future market patterns. Experience may later be used for calibration, retraining, error analysis, regime analysis, and policy evaluation, only with rows whose `outcome_known_at` is before the relevant training cutoff.

## Retraining rules

The agent does **not** retrain after every trade.

Retraining must be:

1. **Scheduled** — calendar or N new labeled rows, never “because last week was good”
2. **Versioned** — new `model_id`, recipe hash, registry row
3. **Reproducible** — frozen hyperparameters, seed, feature version
4. **Evaluated OOS** — untouched block, G0–G3 as registered
5. **Approved before promotion** — champion/challenger rule in `ACCEPTANCE_CRITERIA.md` section 8

While no model has passed G4/G5, the champion remains `no_model` (WAIT-only).

## Explicitly out of this phase

Reinforcement learning, Q-learning, PPO, DQN, policy gradients, autonomous reward optimization, live retraining, NY-SELL revival, and new feature mining.
