# Phase 11 future learning contract

**Status: PROPOSED — NOT IMPLEMENTED.**

A future learner, if ever approved, must preserve:

- original `source_type`
- original experience / decision id
- decision timestamp
- outcome completion timestamp
- side or action
- feature provenance
- outcome provenance
- approved cost convention
- sample eligibility
- as-of availability (`outcome_end <` learning-step time)

It must be able to filter by source and to evaluate, in order:

- **A.** Historical source only
- **B.** Paper source only
- **C.** A and B separately before any controlled combination

WAIT and BLOCKED paper rows are not executed-trade samples.

This phase does not implement the learner, does not pool unlabeled rows, and does not train a model.
