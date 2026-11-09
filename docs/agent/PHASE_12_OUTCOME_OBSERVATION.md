# Phase 12 outcome observation

Horizon: 12 M5 bars (60 minutes), same as approved research.

Stored fields describe the later market path (high/low/close, completeness, gaps). They are **not** executed-trade P&L.

`outcome_end_timestamp < as_of_timestamp` is required. Equality stays pending. Incomplete paths stay pending. A gap inside the horizon excludes the outcome (`excluded_gap`).

Future bars never enter the original observation row.
