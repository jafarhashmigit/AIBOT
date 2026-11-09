# Phase 7 results

Finding class: **exploratory evaluation**. Not confirmatory. Not production-ready.

Policy was frozen in `PHASE_7_POLICY_FREEZE.md` before these numbers. Machine-readable: `reports/phase7/oos_agent_results.json`.

## Repository

- Branch: `cursor/phase7-oos-agent-evaluation`
- Working tree: no tracked files modified
- Created: `src/phase7/`, `docs/agent/PHASE_7_*.md`, `reports/phase7/`, `src/data/phase7_oos_agent_*.csv`
- Modified: none of Phases 1–6 artifacts
- Push status: **not pushed**

## Safety

- Holdout opens: **0**
- CSV reads: `phase2_oos_predictions.csv` only
- Maximum timestamp accessed: `2026-09-29 17:50:00`
- Live trading: none
- Package changes: none
- NY-SELL: not used
- Retrain: none

## OOS input

| | |
|---|---|
| Rows | 36,468 |
| BUY / SELL | 18,234 / 18,234 |
| Timestamps | 18,234 |
| Range | `2026-06-19 03:05:00` → `2026-09-29 17:50:00` |
| SHA-256 | `6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f` |
| Unchanged | **yes** |
| After cutoff | 0 |
| Chronology violations | 0 |

## Agent policy

| Piece | Frozen value |
|---|---|
| Predictor | `Phase2PredictorAdapter` (lookup only) |
| Uncertainty | none / 0, 0 |
| DecisionEngine | Phase 6 `tau=0`, `min_gap=0.02`, `k=1.0` |
| RiskGate | WAIT-only, champion `no_model` |
| Final policy | `P7_PHASE6_DEFAULT` → WAIT after gate |

## Decision distribution (final)

| | Count | % |
|---|---:|---:|
| BUY | 0 | 0% |
| SELL | 0 | 0% |
| WAIT | 18,234 | 100% |

Pre-gate raw engine (blocked, not traded): BUY 1,420 / SELL 9,903 / WAIT 6,911.

## WF1

Agent: 6,078 decisions, 0 BUY, 0 SELL, 6,078 WAIT, 0 trades.

## WF2

Agent: 6,078 decisions, 0 BUY, 0 SELL, 6,078 WAIT, 0 trades.

## WF3

Agent: 6,078 decisions, 0 BUY, 0 SELL, 6,078 WAIT, 0 trades.

## Pooled OOS (agent)

0 trades. Mean R n/a. Net P&L 0. Max DD 0. Bootstrap of trade R undefined (`n_days=0`).

## Statistical results

Agent: no trade-R CI (no trades). Seed 42, 2,000 draws, day cluster — applied to baselines that trade.

## Baseline comparison

| Policy | Trades | BUY | SELL | WAIT | Mean R | PF | Win rate | Max DD USD | 95% CI mean R | P(mean≤0) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| **P7 agent** | 0 | 0 | 0 | 18,234 | — | — | — | 0 | n/a | n/a |
| Always WAIT | 0 | 0 | 0 | 18,234 | — | — | — | 0 | n/a | n/a |
| Phase 3 conservative EV | 0 | 0 | 0 | 18,234 | — | — | — | 0 | n/a | n/a |
| Phase 2 E1 | 11,418 | 1,466 | 9,952 | 6,816 | −0.021 | 0.956 | 40.6% | 1,642 | [−0.060, +0.017] | 0.86 |
| Direction | 18,234 | 3,150 | 15,084 | 0 | −0.029 | 0.943 | 40.1% | 3,379 | [−0.063, +0.004] | 0.96 |

E1 and Direction lose after approved costs in every fold (WF2 worst). The agent matches Always WAIT / Phase 3 frozen WAIT. The gate was not weakened to copy E1.

## Error analysis

See `PHASE_7_ERROR_ANALYSIS.md`. Final false BUY/SELL = 0. Predicted R vs realized R correlation ≈ 0.01–0.02. No new rule.

## Conclusion

**ARCHITECTURE VALIDATED — NO ECONOMIC EDGE**
