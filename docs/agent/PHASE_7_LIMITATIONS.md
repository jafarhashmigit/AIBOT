# Phase 7 limitations

- The agent does not trade. WAIT-only is the Phase 6 champion, preserved on purpose.
- Raw engine BUY/SELL are not a live policy and were not promoted.
- Observation market OHLC is empty: Phase 2 OOS does not carry bars, and Phase 7 did not join `xauusd_m5.csv`.
- Uncertainty was the Phase 6 default (zeros), not a re-estimated MAE. Re-estimating MAE on OOS would have been tuning.
- Baselines reuse Phases 2–3 definitions. They still show no cost-robust edge.
- Holdout remains unused. No production model. No live signals.
- Predicted vs realized correlations are diagnostics, not a new feature.
