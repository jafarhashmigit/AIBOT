# Phase 48 — Decision Intelligence Failure Root-Cause Investigation

**Recipe:** `phase48_decision_intelligence_root_cause_audit_v1`
**Champion:** `NO_MODEL` | **Production:** `WAIT`

## Purpose
Forensic audit of Phase47 `EV_ESTIMATION_UNRELIABLE` and 100% WAIT.
No new strategy. No model promotion.

## Primary conclusion
The agent does not work because the current feature/target architecture provides essentially no predictive information about costed H12 net R; models and calibration cannot invent signal; the WAIT policy then correctly refuses nearly all actions.

## Top root causes
1. `FEATURE_INFORMATION_FAILURE` — Max |corr(feature, net_R)|≈0.0794; probability models do not beat constant base-rate (Brier skill buy=-0.0037687968526639304, sell=-0.005155525052180421). The 13 causal M5 features contain no usable linear/predictive association with Phase46 H12 costed net R on exposed dates.
2. `TARGET_DESIGN_FAILURE` — Decision every M5 bar with horizon=12 creates heavily overlapping outcomes. OOF n≈1748 is not an independent sample size; date-level effective N≈7 eval dates in walk-forward. Metrics can look precise while information content is small.
3. `POLICY_DESIGN_FAILURE` — Uncertainty:=1-2*|p-0.5| rejects ~99% of BUY bars at threshold 0.45 (requires |p-0.5|≥0.275). Joint pass-all-gates BUY=0, SELL=0. With uninformative p≈0.5, 100% WAIT is the expected policy outcome. The gate correctly refuses sharp false confidence but is not a calibrated epistemic uncertainty estimator — and must not be relaxed to force trades.

See `reports/phase48/FINAL_REPORT.md`.

No Phase49 started automatically.
