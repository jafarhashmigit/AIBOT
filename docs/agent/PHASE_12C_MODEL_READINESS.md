# Phase 12C — Model readiness audit

**Champion status: `NO_MODEL`**

No candidate meets the evidence bar for `EXPERIMENTAL_CANDIDATE` or `VALIDATED_CANDIDATE`. Production promotion is refused. BUY/SELL signals remain unauthorized.

## Selection rules applied

- Classification accuracy alone is not trading ability.
- Do not pick the least-bad loser among weak candidates.
- Do not combine historical hypothetical and agent paper experiences without a separately justified learner (Phase 11 explicitly deferred that).
- Independent replication failures veto promising slices.

## Candidate summary

| Model / artifact | Phase | Verdict | Why |
|---|---|---|---|
| RF M5 baseline | 1 | REJECTED | Different task; losing after costs; not Phase 2 OOS-comparable |
| RF side-outcome | 2 | REJECTED | Beats class prior; E1 mean R −0.021, all folds negative |
| Ridge side-outcome | 2 | REJECTED | ≈ constant baseline; no economic actionability |
| P3 conservative EV | 3 | REJECTED | Frozen WAIT refusal; not a directional model |
| Phase 3 META_RIDGE | 3 | REJECTED | Inner positive, outer collapses |
| NY-SELL slice | 4 | REJECTED | Promising slice only; not confirmed |
| NY-SELL replication | 5 | REJECTED | Independent sample mean R −0.082; CI entirely below 0 |
| NullPredictor | 6 | REJECTED | Architecture scaffold |
| P7 Phase 6 default | 7 | REJECTED | Architecture validated; no economic edge; WAIT after gate |
| Experience ridge v1 | 9 | REJECTED | Did not improve OOS decision quality |
| Dual-source stores | 10–11 | REJECTED | Validation only; paper completed outcomes = 0; no combined learner |

## Evidence highlights

- Phase 2 E1: CI [−0.060, +0.017], P(mean ≤ 0) = 0.86.
- Phase 3 frozen policy: 0 trades.
- Phase 5 NY-SELL: CI [−0.139, −0.025], 0/3 blocks positive.
- Phase 7: 18,234 WAIT; E1/Direction lose after costs.
- Phase 9: mean R difference vs Phase 6 = 0 after gate.
- Phase 11: no shared learner; paper metrics unavailable (null), not zero.

## Decision

Retain champion `no_model`.

This is not a temporary placeholder chosen for convenience. It is the only status consistent with the audited OOS, replication, and dual-source evidence. Further isolated research would require new positive evidence that does not yet exist; inventing an `EXPERIMENTAL_CANDIDATE` from losing models would violate the selection rules.

## Coupling to forward path

The Phase 12C forward adapter forces WAIT when `no_model` is the champion. Even if a raw BUY/SELL were proposed, frozen `wait_only` RiskGate configuration blocks it via reused `apply_gate`. No Stage B observation is authorized by this readiness result.
