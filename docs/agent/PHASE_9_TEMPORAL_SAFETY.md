# Phase 9 temporal safety

Same boundary as Phase 8:

```text
latest_experience_outcome_end < decision_time
max_training_outcome_end < decision_time
```

Violation is a hard failure. The store is not preloaded. Experiences are appended only after `outcome_end <` the next decision time.

The learner is fitted only on that filtered set. Outcome fields never enter the feature vector or the Observation.

RiskGate remains `wait_only=True`, `champion_id=no_model`.
