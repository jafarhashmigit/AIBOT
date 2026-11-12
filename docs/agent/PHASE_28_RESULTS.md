# PHASE 28 — Results

Status: **IMPLEMENTATION + READINESS COMPLETE** — forward campaign **not started**.
Evidence: **INSUFFICIENT_FORWARD_EVIDENCE** (0 genuinely new forward candles).

Champion `NO_MODEL` | H13_C `EXPERIMENTAL` | Production `WAIT`

## 1. What was implemented

Isolated Phase 28 under `src/phase28/`, `docs/agent/PHASE_28_*.md`, `reports/phase28/`:

- Dual observers with separate journals: `H13C_BASELINE`, `H13C_HIGH_VOL_RESEARCH`
- Frozen predicted-vol artifact (`artifacts/frozen_vol_model_v1.json`) using Phase 27 regime method (Ridge + train-predicted tertiles)
- Decision-time OHLC feature path; completed-candle-only processing; restart-safe campaign state
- Phase 18 outcome lifecycle (H1/H2/H3/H6/H12)
- Default readiness runner; explicit `--run-live-shadow` for MT5 read-only batches (≤100)

## 2. Frozen artifacts verified

Readiness checks (`reports/phase28/integrity.json` / summary):

| Check | Result |
|---|---|
| Phase 14 / 16A WF3 q25/q75 cuts | OK |
| Phase 27 high-only policy (`regime == high`) | OK |
| Frozen vol model (historical fit ≤ WF3 train cutoff) | OK |
| Phase 22 protected historical hashes | OK |

## 3. Observers operational

| Observer | Operational |
|---|---|
| `H13C_BASELINE` | Yes |
| `H13C_HIGH_VOL_RESEARCH` | Yes |

## 4. Genuinely new forward candles

First live attempt (MT5 history buffer) was quarantined as `INVALID_HISTORICAL_REPLAY`.

Corrected forward session completed: **100** valid new candles after watermark `2026-11-09 17:05:24` UTC (last close `2026-11-10 01:25:00` UTC). Still far below the 500-candle evidence gate.

## 5. Eligible / matured decisions

Eligible BUY/SELL: **0** baseline · **0** high-only accepted (all 100 bars H13_C `WAIT`). Matured outcomes: **0**.

## 6. Baseline vs high-only

**n/a** — no accepted forward trades yet. Do not treat a 100-candle batch as validation.

## 7. Tests and regression

| Suite | Result |
|---|---|
| `phase28.tests.test_phase28` | 21 OK |
| Phase 17–22 regression | OK |
| Phase 17, 23–27 regression | 40 OK |

Details: `reports/phase28/test_results.json`.

## 8. Blockers

None blocking readiness. Note: live frozen vol uses Phase 26 accepted orthogonal features (OHLC-computable). Phase 27 OOF also used baseline store columns; this is documented and not retuned on forward data.

## 9. Evidence still insufficient?

**Yes** — `INSUFFICIENT_FORWARD_EVIDENCE`. Gates require ≥500 new candles, ≥50 baseline BUY/SELL, ≥30 high-only accepts, ≥30 matured H12, ≥10 trading days.

## 10. Production remains WAIT

Confirmed. No Discord/Telegram, no broker orders, no promotion, no automatic campaign start, no commits/pushes.

### Manual live shadow (later)

```text
python src/phase28/run_phase28.py --run-live-shadow --max-candles 100
```
