# Phase 12 shadow journal

Every valid completed observation produces one `FORWARD_SHADOW` decision.

With champion `no_model`:

- `model_status = NO_MODEL`
- `raw_action = WAIT`
- `final_action = WAIT`
- `reason = NO_APPROVED_MODEL`
- `is_paper_trade = false`
- `is_paper_execution = false`

WAIT is not a paper trade. Shadow decisions are not written to the Phase 10 paper store.
