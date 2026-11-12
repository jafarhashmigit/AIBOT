# PHASE 28 — Forward Shadow Validation (Research Plan)

## Objective

Validate whether Phase 27’s volatility-aware findings persist on genuinely new, forward-observed XAUUSD M5 candles using two strictly separate research observers:

1. `H13C_BASELINE` — frozen Phase 14 H13_C logic and q25/q75 thresholds.
2. `H13C_HIGH_VOL_RESEARCH` — Phase 27 high-only policy with a frozen, leakage-free predicted-volatility model.

This is forward shadow research only. It is not a production trading strategy.

## Frozen artifacts (no retuning on forward data)

| Artifact | Source | Rule |
|---|---|---|
| H13_C cuts | Phase 14 / 16A WF3 | q_low=25, q_high=75; close_ema thresholds frozen |
| High-only policy | Phase 27 | Accept H13_C BUY/SELL only when decision-time pred regime == `high` |
| Predicted-vol model | Phase 28 frozen fit | Ridge on approved history ≤ WF3 train cutoff; tertiles from train *predicted* vol |
| Outcome contract | Phase 18 | H1/H2/H3/H6/H12 pending → mature after horizon bars |

Frozen live vol features = Phase 26 accepted orthogonal set (OHLC-computable). Phase 27 OOF also used baseline store columns; the live artifact documents this subset for MT5 reproducibility.

## Forward observation rules

- Only completed M5 candles received after Phase 28 starts (never historical replay as forward).
- Never fabricate missing candles; process each candle at most once (restart-safe).
- MT5 read-only only; no broker orders; no Discord/Telegram.
- Preserve research cutoff `2026-09-29 18:50 UTC`; do not open protected holdout.
- Default runner mode = readiness/report only; live shadow requires `--run-live-shadow`.

## Evidence gates (predeclared)

Until all gates pass, status remains `INSUFFICIENT_FORWARD_EVIDENCE`:

- ≥ 500 new forward candles
- ≥ 50 baseline BUY/SELL decisions
- ≥ 30 high-only accepted decisions
- ≥ 30 matured H12 outcomes
- ≥ 10 distinct trading days

Do not claim validation from a 100-candle batch.

## Safety gates (unchanged)

- Champion: `NO_MODEL`
- H13_C: `EXPERIMENTAL`
- Production action: `WAIT`
- No production promotion, no paid APIs, no package installs, no commits/pushes from this phase runner
