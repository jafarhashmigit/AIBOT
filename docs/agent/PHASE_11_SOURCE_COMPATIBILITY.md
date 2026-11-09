# Phase 11 source compatibility

**Implemented:** a read-only comparison of schemas and concepts. Raw records are not merged. Values are not normalized in place.

The sources are **not** equivalent populations.

| Concept | Historical | Paper |
|---|---|---|
| Identity | `hist:{ts}:{side}` | `paper:{ts}:XAUUSD:M5` |
| Action | BUY or SELL hypothetical | BUY / SELL / WAIT proposal and final action |
| Realized R | `actual_net_r` | `simulated_realized_r` (none today) |
| Provenance | Phase 2 OOS | Phase 9 replay journal |
| Costs | embedded in approved labels | not a field on `PaperDecision` |

A future shared learner **requires an explicit adapter**. That adapter is documented, not implemented.

**Not implemented:** combined learning, silent field coercion, treating a hypothetical BUY as an agent paper BUY.
