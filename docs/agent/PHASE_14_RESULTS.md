# Phase 14 results

**Candidate decision: `RETAINED_EXPERIMENTAL`**

Champion: **`NO_MODEL`** (unchanged). BUY/SELL not authorized. Stage B not authorized. Not production.

## Replication (Part A)

Independent reconstruction under `src/phase14/` (own H1 EMA binary-search join, own linear percentile cuts, own signal code) was compared to a Phase 13 **reference-only** rebuild.

| Metric | Independent | Phase 13 reference |
|---|---:|---:|
| Trades | 226 | 226 |
| Set match | exact | exact |
| Mean R | +0.04856060840719428 | +0.04856060840719428 |
| Only-independent / only-reference | 0 / 0 | — |

No mismatches. Original 226 trades reproduced.

## Walk-forward (Part B)

| Fold | n | Mean R | Median R | PF | Win rate | Net USD/oz | Day-cluster CI |
|---|---:|---:|---:|---:|---:|---:|---|
| WF1 | 63 | **−0.108** | −1.000 | 0.827 | 0.365 | −37.04 | [−0.401, +0.201] |
| WF2 | 67 | +0.188 | −0.228 | 1.393 | 0.478 | +119.12 | [−0.126, +0.458] |
| WF3 | 96 | +0.054 | −1.000 | 1.102 | 0.448 | +5.51 | [−0.215, +0.351] |
| Pooled | 226 | +0.049 | — | 1.090 | 0.434 | +87.59 | [−0.138, +0.217] |

### Why WF1 is negative (descriptive only)

- WF1 BUY mean R ≈ −0.249 (21 trades); SELL ≈ −0.037 (42 trades).
- NY-session share ~0.46–0.51 across folds (not a simple NY-only artifact).
- Parameters were **not** changed to repair WF1.

Confirmatory rule “all WF windows positive” **fails**.

## Cost robustness (Part C, confirmatory)

| Stress | Mean R | Positive? |
|---|---:|---|
| 1.0× | +0.049 | yes |
| 1.25× | +0.042 | yes |
| 1.5× | +0.036 | yes |
| 2.0× | +0.023 | yes |

Cost stress alone does not fail; walk-forward instability and CI do.

### Exploratory sensitivity (not used to pick a new strategy)

24 predeclared grid cells (pullback q20/25/30 × H1 `>`/`>=` × delay 0/1 × slippage 0/0.05). About one-third of cells with n≥30 have positive mean R. Best cell is **not** promoted.

## Statistical validation (Part D)

- Day-cluster bootstrap: 2000 draws, seed 42.
- Pooled CI: [−0.138, +0.217] — **includes 0**.
- P(mean R ≤ 0) ≈ 0.29 — not < 0.05.
- No statistical significance claimed.
- Phase 13 BH-FDR already failed for this candidate among four hypotheses.

## Data sufficiency (Part E)

- 226 trades / 66 decision days / H1 coverage 100%.
- M5 labeled OOS still ~3 months (WF1–WF3).
- `sufficient_for_confirmation = False`.
- Independent longer labeled M5 history would be required for confirmation; no external download and no fabricated bars in this phase.

## Candidate decision (Part F)

**`RETAINED_EXPERIMENTAL`**

| Confirmatory check | Result |
|---|---|
| Exact replication of 226 trades | PASS |
| No holdout / cutoff respected | PASS |
| All WF windows mean R > 0 | **FAIL (WF1)** |
| Cost stress 1.0–1.5× mean R > 0 | PASS |
| CI lower > 0 | **FAIL** |
| Sufficient for confirmation | **FAIL** |

Not `READY_FOR_CONTROLLED_PAPER_RESEARCH`. Not `REJECTED` (reproducible and not clearly CI-negative overall). Remains fragile experimental research only. Champion stays `NO_MODEL`.

## Safety

- Holdout opens: 0
- MT5 connections: 0
- Broker orders: 0
- Tests: Phase 14 8/8 ×2; Phase 12 43/43 ×2; Phase 12C 20/20 ×2
- Protected Phase 1–13 hashes: unchanged
- GitHub pushed: no
