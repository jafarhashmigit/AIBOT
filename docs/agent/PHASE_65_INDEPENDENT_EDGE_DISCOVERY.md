# Phase 65 — Final Report

**Recipe:** `phase65_independent_edge_discovery_v1`
**Verdict:** `NO_NEW_INFORMATION_FAMILY_FOUND`
**Champion:** `NO_MODEL` | **Production:** `WAIT`
**Live:** `NOT_AUTHORIZED` | **Automated Orders:** `DISABLED` | **order_send:** `PROHIBITED`
**Broker Collection:** `READ_ONLY` | **Execution:** `BLOCKED`
**Risk Policy:** `UNAPPROVED` | **Cost model:** `INCOMPLETE` | **Fills:** `NONE_TRADE_FILLS`
**Reason:** Hypothesis budget exhausted; no family survived discovery gates vs WAIT
**Generated:** `2026-11-12T06:23:00Z`

## 1. Executive verdict
`NO_NEW_INFORMATION_FAMILY_FOUND` — Champion remains `NO_MODEL`; Production remains `WAIT`.

## 2. Research inventory
See `RESEARCH_INVENTORY.md`. Retired families enforced. Phase58 holdout sealed.

## 3. Previously failed / retired
- Phase49/50/51/58 failures recorded; DO_NOT_REPEAT n=`44`

## 4. Eligible data and provenance
- Unconsumed days: `['2025-10-07', '2025-10-09', '2025-10-13', '2025-10-14', '2025-10-17', '2025-10-20', '2025-10-28', '2025-11-04', '2025-11-06', '2025-11-13', '2025-11-20']`
- Discovery: `['2025-10-07', '2025-10-09', '2025-10-13', '2025-10-14', '2025-10-17', '2025-10-20', '2025-10-28']` (126 events)
- Validation: `['2025-11-04', '2025-11-06', '2025-11-13', '2025-11-20']` (72 events)

## 5. Sealed holdout protection
- Phase58 holdout: `['2025-09-10', '2025-09-11', '2025-09-12', '2025-09-16', '2025-09-18', '2025-09-19', '2025-09-22', '2025-09-24', '2025-09-25', '2025-10-02']` opened=`False`

## 6. Preregistered hypotheses
- Registry SHA: `5cccb48eb4c871e0fa589cd42b084df3f5890c1a3e66b851ffadaadad7f4df7a`
- `H65_V1_ATR_REGIME_ABSTAIN`
- `H65_C1_COMPRESSION_EXPANSION`
- `H65_S1_SESSION_OPEN_FILTER`

## 7. Leakage
- Pass: `True`

## 8. WAIT / baselines
See `BASELINE_COMPARISON.md`.

## 9. Statistical results
- Discovery survivors: `[]` | Validation survivors: `[]`

## 10. Execution-cost stress
See `EXECUTION_COST_STRESS.md`. Unknown costs not zeroed.

## 11. Dual-experience
- Learning OOS improve: `False` | stores merged: `False`

## 12. Regime robustness
See `REGIME_ROBUSTNESS.md`.

## 13. Rejected candidates
- n=`3` — see `REJECTED_HYPOTHESES.md`

## 14. Surviving research candidate
- `NONE`

## 15. Evidence limitations
- Archive substrate MetaQuotes-Demo XAUUSD ≠ Exness live XAUUSDm execution
- Commission/slippage/swap UNKNOWN — not set to zero; not fully execution-robust
- Exness session schedule applied as research proxy on archive timestamps
- Phase58 holdout remains sealed (not opened)
- Small unconsumed day pool limits statistical power
- Shadow/paper experience empty or unaligned — no dual-learning OOS claim

## 16. Reproducibility
```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m phase65.run_phase65
```

## 17. Security invariants
- Champion: `NO_MODEL`
- Production: `WAIT`
- Live: `NOT_AUTHORIZED`
- AutomatedOrders: `DISABLED`
- RiskPolicy: `UNAPPROVED`
- CostModel: `INCOMPLETE`
- BrokerCollection: `READ_ONLY`
- ExecutionAuthorization: `BLOCKED`
- order_send: `PROHIBITED`
- BROKER_SUBMISSION_ENABLED: `False`
- BROKER_EXECUTION_AUTHORIZED: `False`
- GenuineFills: `NONE_TRADE_FILLS`
- Submission enabled: `False` | Exec authorized: `False`

## 18. Next recommended phase
Keep Champion=NO_MODEL and Production=WAIT. Prefer collecting genuine DEMO broker economics evidence (commission/margin/swap) under READ_ONLY constraints before further strategy churn; if new unconsumed archives appear, preregister a new H65.x family with a fresh budget — do not reopen Phase58 holdout without a survivor.

Runtime s: `13.849128800000472`
