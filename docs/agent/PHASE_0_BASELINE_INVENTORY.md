# Phase 0 — Baseline Inventory

Project: AIBOT self-learning XAUUSD research agent (BUY / SELL / WAIT). Research only; no live trading or order execution.
Audit date: 2026-11-08. Audit type: read-only inspection of scripts, report files and file metadata.

## 0. How this inventory was produced

- Sources: the Python scripts in `src/`, the text reports and result CSVs in `src/data/`, file sizes and timestamps, and the project's own integrity sections inside each report.
- Nothing was executed, retrained, regenerated, renamed or deleted. No package was installed.
- **Not opened:** `src/data/xauusd_m5_test.csv` (final holdout), and the legacy files `src/data/test.csv`, `src/data/train.csv`, `src/data/validation.csv` and `src/data/gold_history.csv`. Their date ranges are unknown and may overlap the holdout.
- Every figure below is copied from a project report. Where a result was never written to a project file, it is marked **UNAVAILABLE**.
- One result comes from the chat record and not from a project file: the 20-seed shuffled-label check for M15 H4 (experiment E14). It is labelled as such.

## 1. Reserved final holdout (binding for all future work)

| Item | Definition |
|---|---|
| Research cutoff | **2026-09-29 18:50:00** (MT5 server clock). This is the last M5 validation row (17:50) plus the 12-bar purge. |
| Holdout | Every XAUUSD bar after the cutoff, on every timeframe. That includes `xauusd_m5_test.csv` and the post-cutoff rows inside `xauusd_m5.csv`, `xauusd_m5_features.csv` and `xauusd_m5_labeled.csv`. |
| Holdout size | About 7,150 labeled M5 rows (about 6 weeks). **Derived from the 70/15/15 split arithmetic; the file was not opened.** |
| Files that contain holdout rows | `xauusd_m5.csv`, `xauusd_m5_features.csv`, `xauusd_m5_labeled.csv`, `xauusd_m5_test.csv`. The first three must only be read with a row cap at the cutoff (existing guards: `install_guards`, `rows_through`, `assert_no_test_rows` in `src/research_kronos_m5.py`). |
| Files that end before the cutoff | `xauusd_h1_mt5.csv`, `xauusd_m15.csv`, `external_dxy_basket_m5.csv`, `external_us_treasury_daily.csv`, the train and validation splits, and every research output. |
| Status | Never loaded by any experiment. Every report from E7 onward states and checks this. |

## 2. Project structure

```
AIBOT/
├── requirements.txt            pandas, numpy, scikit-learn, yfinance, matplotlib (incomplete: see section 7)
├── verify_labels.py            independent slow re-check of label_m5 output
├── where, src/main.py          empty files
└── src/
    ├── features.py, models/train_model.py, models/evaluate_model.py, models/gold_model.pkl   LEGACY daily pipeline
    ├── mt5_test.py                                     MT5 connection test (no data saved)
    ├── features_m5.py, label_m5.py, split_m5.py        M5 data pipeline
    ├── train_rf_m5.py, backtest_rf_m5.py               RF baseline + backtester
    ├── analyze_rf_m5_trades.py, analyze_rf_m5_confidence.py
    ├── research_*.py (11 scripts)                      research experiments
    ├── fetch_m5_macro_data.py, fetch_xauusd_h1_history.py   read-only data downloads
    ├── models/rf_m5_baseline.pkl                       saved RF baseline
    └── data/                                           datasets, outputs and reports
```

There is no git repository and no `docs/` folder existed before this audit.

## 3. Component status

| Component | Status | Evidence | Known gaps |
|---|---|---|---|
| MT5 historical data pipeline | **Partial.** Two read-only download scripts exist: `fetch_m5_macro_data.py` (six FX pairs, M5) and `fetch_xauusd_h1_history.py` (XAUUSD H1 from 2018). | Feed check: H1 and M5 OHLC are identical on 3,537/3,537 complete hours. DXY feed is on the same clock. | **No script in the project produced `xauusd_m5.csv`**; it predates the recorded work. The MT5 terminal limit is `maxbars` = 100,000. There is no incremental or append ingestion. |
| M5 dataset | Exists. `xauusd_m5.csv` starts 2026-02-16 08:50. Through the cutoff: 42,499 rows. | Bar-for-bar identical to MetaQuotes-Demo. | Only about 7.5 months before the cutoff. The file also contains holdout rows. |
| M15 dataset | Exists. `xauusd_m15.csv`: 14,163 candles, 2026-02-16 09:00 → 2026-09-29 18:30. | Built only from complete triples of M5 bars; 7 incomplete slots rejected. | Same 7.5-month span as M5. |
| H1 dataset | Exists. `xauusd_h1_mt5.csv`: 51,461 bars, 2018-01-02 09:00 → 2026-09-29 17:00. | Exact OHLC match with M5 over the overlap. | H1 `spread` is the hourly **minimum** spread. |
| Feature engineering | Exists. `features_m5.py` (about 70 causal columns; the RF uses 30 `RF_FEATURES`). Research-only families exist inside research scripts. | Truncation-invariance checks passed in E8–E10 and E13. | **Clock defect:** `features_m5.py` treats server time as UTC. The server clock is Europe/Athens (UTC+2/+3), so `hour_utc` and the `session_*` columns are shifted 2–3 hours. Later research scripts convert correctly. |
| Cost-aware labeling | Exists. `label_m5.py`: triple barrier, TP 1.5×ATR14, SL 1.0×ATR14, 12 bars, entry at the next open. Spread floored at 15 points, plus $0.05 per side. Same-bar TP and SL counts as SL. Windows that cross a gap are excluded. | `verify_labels.py`: 0 mismatches in a 3,000-row sample. | BUY/SELL/WAIT only; per-side outcome (TP, SL or time exit) and realized R are not stored. |
| Chronological splits | Exists. `split_m5.py`: 70/15/15 with a 12-row purge. Train 33,366 rows (2026-02-16 12:55 → 2026-08-20 08:20); validation 7,140 rows (2026-08-20 09:25 → 2026-09-29 17:50); test never opened. | Leakage assertions inside the script. | The validation period has been reused by about 12 experiments, so it is no longer a clean estimate. |
| Random Forest baseline | Exists. `train_rf_m5.py` → `models/rf_m5_baseline.pkl`. Fixed parameters (section 5, E2). | Reproduced exactly by E6–E13. | Probabilities are uncalibrated vote shares (0.33–0.57). |
| Backtesting engine | Exists. `backtest_rf_m5.py`: next-bar entry, one position at a time, SL checked before TP, gap-through-SL fills at the open, 12-bar time exit, market-closed rejection. | Imports cost rules from `label_m5.py`; prefix-invariance assertion. | Bar-level only; minimum-spread data; no swap. Drawdown counts closed trades only. Hard-wired to the RF model and the validation period. |
| Walk-forward validation | **Exists in research scripts only, not as a shared module.** M5 windows WF1–WF3 (from 0.55/0.70/0.85 of rows) with an expanding, purged training set. H1/H4 strategies use DEV plus WF1–WF3 calendar fractions. | Identical windows across E7–E13. | Three windows of about 5 weeks; WF3 overlaps the main validation period. Windows reused across many experiments. |
| Trade and confidence analysis | Exists (E4, E5). | Reports listed below. | Descriptive only, one period. |
| EMA pullback and crossover | Exists (E15, E16) on H1/H4/D1 built from MT5 H1. | Reports listed below. | Fixed rules, no learning. |
| Macro, calendar, conditional edge | Exists (E9, E10, E12). | Reports listed below. | External data covers 2026-02 → 2026-09 only. |
| Future-return predictability | Exists (E13 M5, E14 M15). | Reports listed below. | Direction only, no costs. |
| Kronos experiment | Exists (E11). Pretrained Kronos-mini, inference only, GTX 1050. | Report listed below. | No fine-tuning; one sampled path per forecast. |

## 4. Datasets available (pre-cutoff only)

| File | Content | Range (server clock) | Rows | Used by |
|---|---|---|---|---|
| `xauusd_m5.csv` | Raw M5 OHLC, tick volume, minimum spread | 2026-02-16 08:50 → cutoff (holdout rows follow) | 42,499 through the cutoff; total not counted | All M5 work |
| `xauusd_m5_features.csv` | Causal features | Through the cutoff (holdout follows) | 42,450 through the cutoff | E2–E14 |
| `xauusd_m5_labeled.csv` | Features + `target` | Through the cutoff (holdout follows) | 40,518 research rows (1,920 excluded for gaps) | Splits |
| `xauusd_m5_train.csv` | Train split | 2026-02-16 12:55 → 2026-08-20 08:20 | 33,366 (BUY 32.0%, SELL 36.0%, WAIT 32.0%) | E2 onward |
| `xauusd_m5_validation.csv` | Validation split | 2026-08-20 09:25 → 2026-09-29 17:50 | 7,140 | E2 onward |
| `xauusd_m5_test.csv` | **Final holdout** | After the cutoff | Not opened | Nobody |
| `xauusd_m15.csv` | M15 from complete M5 triples | 2026-02-16 09:00 → 2026-09-29 18:30 | 14,163 | E14 |
| `xauusd_h1_mt5.csv` | H1 from MT5 | 2018-01-02 09:00 → 2026-09-29 17:00 | 51,461 | E15, E16 |
| `external_dxy_basket_m5.csv` | Six DXY component pairs, M5 closes | 2026-02-01 → cutoff | 49,375 timestamps | E9 |
| `external_us_treasury_daily.csv` | FRED DGS2, DGS10 | 2025-10-01 → 2026-09-29 | 249 days | E9 |
| `economic_calendar_m5_features.csv` | CPI/NFP/FOMC timing features (point-in-time) | Research rows | 40,518 | E10 |
| `kronos_m5_predictions.csv` | Kronos 12-bar forecasts | 2026-06-19 → 2026-09-29 | 19,098 | E11 |
| `rf_m5_validation_trades.csv` | Baseline validation trades | 2026-08-20 → 2026-09-29 | 1,518 | E4, E5, E12 |
| Legacy `gold_history.csv`, `train.csv`, `validation.csv`, `test.csv` | Daily gold, legacy splits (code expects Open/High/Low/Close/Volume) | **Not inspected** | Not inspected | E0 only |

## 5. Experiment inventory

Every experiment except E0 uses the cost model from `label_m5.py`/`backtest_rf_m5.py`: spread = max(bar spread, 15 points) × $0.01, plus $0.05 per side. R = net P&L / SL distance. Balanced accuracy: chance is 0.333 for the three classes and 0.5 for UP/DOWN.

The fixed RF used everywhere ("fixed RF"): `n_estimators=300, max_depth=8, min_samples_leaf=50, max_features="sqrt", max_samples=0.5, bootstrap=True, class_weight="balanced", criterion="gini", random_state=42, n_jobs=-1`.

The M5 walk-forward windows ("M5 WF"): WF1 2026-06-19 03:05 → 07-23 11:25; WF2 → 08-26 13:55; WF3 → 09-29 17:50. Training is expanding with a 12-bar purge. WF3 overlaps the main validation split.

### E0 — Legacy daily RF (pre-M5 prototype)
- **Scripts:** `src/features.py`, `src/models/train_model.py`, `src/models/evaluate_model.py`. **Output:** `src/models/gold_model.pkl`.
- **Dataset:** legacy `train.csv` / `validation.csv` / `test.csv` (daily, Yahoo-style columns; `yfinance` is in requirements).
- **Model:** RF with 200 trees, depth 8, leaf 10; next-close-up target; raw price levels used as features.
- **Results:** **UNAVAILABLE.** No report was saved. The training script prints only in-sample metrics.
- **Walk-forward:** none.
- **Limitations:** raw price levels as features; in-sample diagnostics only; the evaluation script reads a legacy `test.csv` of unknown range.
- **Credible edge:** **Not assessable.** This is superseded and should not be reused.

### E1 — M5 data pipeline (infrastructure, not an experiment)
- **Scripts:** `features_m5.py` → `xauusd_m5_features.csv`; `label_m5.py` → `xauusd_m5_labeled.csv`; `split_m5.py` → the train/validation/test CSVs; `verify_labels.py`.
- **Results:** research rows BUY 32.0%, SELL 35.8%, WAIT 32.2%. 1,920 rows excluded because their window crosses a gap. Median round-trip cost is 3.2% of the TP distance. Label check: 0/3,000 mismatches.
- **Limitations:** session and hour features carry the server-clock error described in section 3.

### E2 — RF baseline
- **Script:** `train_rf_m5.py`. **Output:** `models/rf_m5_baseline.pkl` (SHA-256 `12239ed0…e1cb1`).
- **Dataset:** train and validation splits, 30 `RF_FEATURES`. **Model:** fixed RF.
- **Main results (validation):** accuracy 38.57%, balanced accuracy 0.3862 (chance 0.333, majority class 34.7%); train balanced accuracy 0.4735 (gap +0.087). Precision: BUY 35.1%, SELL 40.0%, WAIT 40.8%; the theoretical TP/SL break-even is 40.0%.
- **Walk-forward (from E7/E10):** balanced accuracy 0.3723 / 0.3763 / 0.3847 (mean 0.3777).
- **Limitations:** uncalibrated probabilities; one validation period; session clock error.
- **Credible edge:** **No.** The class skill is weak (+0.04–0.05 over chance) and does not become profit (E3, E12).

### E3 — Baseline backtest
- **Script:** `backtest_rf_m5.py`. **Output:** `rf_m5_validation_trades.csv`.
- **Main results (validation, 2026-08-20 → 09-29):** 1,518 trades (BUY 862, SELL 656). Exits: TP 576, SL 887, time 55. Win rate 40.3%. Gross $229.97/oz, costs $392.63/oz, **net −$162.66/oz**. **Average −0.0169R, total −25.65R.** Profit factor 0.965. Maximum closed-trade drawdown $389.95/oz, not recovered by the end of the period. Longest losing streak 16. By side: BUY −0.0729R, SELL +0.0566R.
- **Walk-forward (from E12, models retrained per window):** 3,877 trades; average R −0.0257 / −0.0785 / −0.0321; pooled 95% CI [−0.087, −0.006].
- **Limitations:** bar-level fills; minimum spreads; no swap. P&L moves a lot when training rows change slightly: the same baseline configuration gave −$162.66, −$351.96 and −$529.08 per oz in E3, E8 and E9 depending on the warm-up and row set.
- **Credible edge:** **No.** The walk-forward CI is entirely negative.

### E4 — Trade analysis
- **Script:** `analyze_rf_m5_trades.py`. **Outputs:** `rf_m5_trade_analysis.csv`, `rf_m5_trade_loss_streaks.csv`, `rf_m5_trade_drawdowns.csv`.
- **Dataset:** E3 trades plus signal-bar features. Groups: side, hour, session, RSI bucket, ATR% quartile (edges from training).
- **Main results:** overall average R −0.0169 (CI −0.079 to +0.045). TP exits +1.500R, SL exits −1.015R (gap slippage), time exits +0.198R (55 trades). The deepest drawdown ran $389.95/oz over 700 trades (2026-08-28 → 09-16) and had not recovered after 1,163 trades.
- **Walk-forward:** none (one period).
- **Limitations:** descriptive; many groups; one period; hour and session use the shifted clock.
- **Credible edge:** **No.** E12 tested these subgroup ideas properly.

### E5 — Confidence analysis
- **Script:** `analyze_rf_m5_confidence.py`. **Outputs:** `rf_m5_confidence_analysis.csv`, `rf_m5_confidence_report.txt`.
- **Main results:** maximum class probability on traded rows ranges 0.334–0.476 (median 0.363). 94% of trades fall in the 0.33–0.40 bucket. Average R by confidence decile is not monotonic (D1 −0.014, D6 +0.236, D10 −0.094). Correlation of confidence with R: Pearson −0.012, Spearman −0.036.
- **Walk-forward:** none.
- **Limitations:** uncalibrated vote shares; single-position selection; one period.
- **Credible edge:** **No.** RF confidence carries no usable ranking information, so a confidence threshold cannot rescue the baseline.

### E6 — Pre-defined model comparison (7 RF configurations)
- **Script:** `research_rf_m5_model_comparison.py`. **Outputs:** `rf_m5_model_comparison.csv`, `rf_m5_model_comparison_report.txt`.
- **Model:** baseline plus candidates A–F (depth 10–12, leaf 25–50, max_samples 0.5 or all rows).
- **Main results (validation):** balanced accuracy 0.3787–0.3889. Average R −0.0159 (A) to −0.0658 (F). Profit factor 0.923–0.981. Every candidate widened the train–validation gap by more than 0.03. The best R gain (A, +0.0010R) is within 2 SE (0.045).
- **Walk-forward:** not run.
- **Limitations:** seven configurations on one period, so the best is optimistically biased.
- **Credible edge:** **No.** More capacity means more overfitting, not more out-of-sample skill.

### E7 — Label-horizon research
- **Script:** `research_m5_label_horizon.py`. **Outputs:** `m5_label_horizon_research.csv`, `m5_label_horizon_research_report.txt`.
- **Configurations:** CONFIG_0 (TP 1.5 / SL 1.0 / 12 bars), A = C (1.5 / 1.0 / 24 bars), B (2.0 / 1.0 / 24 bars); fixed RF.
- **Main results:** CONFIG_0 balanced accuracy 0.3862 (main). A: −0.047; B: −0.029 against CONFIG_0.
- **Walk-forward:** CONFIG_0 0.3723 / 0.3763 / 0.3847. A 0.3401–0.3664. B 0.3462–0.3666. No alternative was better by more than 0.01 in any window.
- **Limitations:** classification only; three windows.
- **Credible edge:** **No.** The bottleneck is information in the features, not the horizon.

### E8 — Feature-family research
- **Script:** `research_m5_feature_families.py`. **Outputs:** `m5_feature_family_research.csv`, `m5_feature_family_research_report.txt`.
- **Families:** A higher-timeframe trend (M15/M30/H1, 24 features), B regime (7), C price structure (12), D session clock (11), and combinations E/F/G.
- **Main results:** walk-forward mean balanced accuracy 0.3731–0.3826 against a baseline of 0.3761. Best: C +0.0055, D +0.0064. No family was better by more than 0.01 in all three windows. Paired block-bootstrap CIs mostly include zero.
- **Walk-forward:** as above. All checks for causality and forming candles passed, including a leaky control that was detected.
- **Limitations:** seven configurations; three windows; backtest appendix not used for selection.
- **Credible edge:** **No.** OHLC-derived context appears saturated.

### E9 — External macro features (DXY, US 2Y/10Y)
- **Scripts:** `fetch_m5_macro_data.py`, `research_m5_macro_features.py`. **Outputs:** `external_dxy_basket_m5.csv`, `external_us_treasury_daily.csv`, `m5_macro_feature_research.csv`, `m5_macro_feature_research_report.txt`.
- **Features:** DXY rebuilt with the ICE formula from MT5 FX (10 features). FRED yields lagged 2 days (6 features).
- **Main results:** walk-forward mean balanced accuracy: baseline 0.3775, DXY 0.3737, yields 0.3741, both 0.3726. Some windows are significantly worse (WF2 for DXY, yields and both combined).
- **Limitations:** FRED latest vintage only; 7.5 months.
- **Credible edge:** **No.**

### E10 — Economic-calendar timing (CPI, NFP, FOMC)
- **Script:** `research_economic_calendar_m5.py`. **Outputs:** `economic_calendar_m5_features.csv`, `economic_calendar_m5_research.csv`, `economic_calendar_m5_research_report.txt`.
- **Features:** point-in-time scheduled release timing, built from Internet Archive captures; 11 per event family; no actual or forecast values.
- **Main results:** walk-forward mean balanced accuracy: baseline 0.3777, CPI 0.3788, NFP 0.3757, FOMC 0.3742, all three 0.3755. No CI above zero.
- **Limitations:** only 8 CPI, 8 NFP and 5 FOMC events; window flags active on few rows. This report also established the **server clock = Europe/Athens** (98.4% of daily reopens match).
- **Credible edge:** **No.**

### E11 — Kronos-mini (pretrained foundation model)
- **Script:** `research_kronos_m5.py` (also the home of the holdout guards). **Outputs:** `kronos_m5_predictions.csv`, `kronos_m5_research.csv`, `kronos_m5_research_report.txt`.
- **Model:** NeoQuasar/Kronos-mini (4.1M parameters) with a 2,048-bar context; 12-bar forecast; one sampled path; GTX 1050; 339 minutes of inference.
- **Main results:** mean absolute error is worse than a no-change forecast at every horizon (skill −0.65 to −1.92). 12-bar direction hit rate 48.7–49.8%.
- **Walk-forward:** balanced accuracy 0.3319 / 0.3168 / 0.3301, significantly below RF in every window. Backtest −0.0627R (1,802 trades).
- **Limitations:** no fine-tuning; one path; tick volume used as volume; timestamps treated as UTC.
- **Credible edge:** **No.** It is worse than RF and at or below chance.

### E12 — RF conditional-edge research
- **Script:** `research_rf_m5_conditional_edge.py` (exports `snapshot`, `prefix_sha256`). **Outputs:** `rf_m5_conditional_edge_research.csv`, `rf_m5_conditional_edge_research_report.txt`.
- **Design:** 102 pre-defined subgroups (side, RSI, ATR quartile, session and their pairs); main period plus walk-forward retrained models; Benjamini–Hochberg FDR at q = 0.10.
- **Main results:** 20 groups were profitable in the main period with at least 100 trades. In walk-forward, 2 groups met the window criteria (SELL with RSI 50–60, +0.0336R; RSI 50–60 during the London–NY overlap, +0.0803R). **0 survived FDR** (adjusted p 0.999).
- **Walk-forward:** pooled all trades −0.0454R (CI −0.087 to −0.006); BUY −0.0723R; SELL −0.0136R.
- **Limitations:** overlapping groups; trade-level bootstrap ignores serial correlation.
- **Credible edge:** **No.** Conclusion: "No stable conditional edge found."

### E13 — M5 future-return direction predictability
- **Script:** `research_m5_future_return_predictability.py`. **Outputs:** `m5_future_return_predictability.csv`, `m5_future_return_predictability_report.txt`.
- **Targets:** UP or DOWN at H3, H6 and H12; fixed RF; 30 features; M5 WF.
- **Main results:** mean improvement over 0.5: H3 +0.0140 (CI +0.004 to +0.023), H6 +0.0106, H12 +0.0125. AUC 0.515–0.519. No horizon reached +0.02 in any window. The H6 shuffled-label check passed and collapsed to 0.50.
- **Limitations:** direction only, no costs.
- **Credible edge:** **No.** The effects are statistically above zero but economically negligible. Conclusion: "No convincing walk-forward predictability found."

### E14 — M15 future-return direction predictability
- **Script:** `research_m15_future_return_predictability.py`. **Outputs:** `xauusd_m15.csv`, `m15_future_return_predictability.csv`, `m15_future_return_predictability_report.txt`.
- **Targets:** UP or DOWN at H2, H4 and H8 M15 candles; 33 M15 features; fixed RF; M15 windows (2026-06-19 06:45 → 07-23 14:00 → 08-26 15:00 → 09-29 17:30).
- **Main results:** H4 balanced accuracy 0.5234 / 0.5165 / 0.5263; mean improvement **+0.0221** (CI +0.0048 to +0.0381); it meets all four pre-declared rules. H2 +0.0100 and H8 +0.0101 do not.
- **Permutation check (pre-declared): FAIL.** One shuffled-label run reached 0.530 in WF3.
- **Post-hoc 20-seed shuffled-label run (chat record only, not a project file):** null mean improvement +0.001 (SD 0.007, max +0.014). None of the 20 reached +0.022.
- **Limitations:** one of three horizons; margin over the +0.02 bar only +0.002; period overlaps the M5 development data; direction only, before costs.
- **Credible edge:** **Unconfirmed.** Conclusion: "Potential M15 walk-forward predictability found; independent confirmation required." This is not an economic edge.

### E15 — D1/H4/H1 EMA pullback strategy (rule-based)
- **Scripts:** `fetch_xauusd_h1_history.py`, `research_xauusd_ema_pullback.py`. **Outputs:** `xauusd_ema_pullback_trades.csv`, `xauusd_ema_pullback_results.csv`, `xauusd_ema_pullback_report.txt`.
- **Rules:** D1 EMA50/200 bias, H4 EMA50 confirmation, H1 EMA20 pullback candle; SL 1.5×ATR14; TP 2R; one position.
- **Main results:** 878 trades (754 BUY). Win rate 34.9%; break-even before costs is 33.3%. **+0.0430R average (+37.74R total) but −$218.89/oz**, profit factor 0.964. The units disagree because the gold price rose several-fold. Maximum drawdown 35R.
- **Walk-forward:** DEV −0.0069R; WF1 +0.1408R, WF2 +0.0699R, WF3 +0.0653R (WF1–3 +0.0913R, 446 trades) in R. In USD/oz: +224.07, −67.48, −239.97. SELL −0.0565R. At 2× spread: +0.0087R overall.
- **Limitations:** fixed rule; no significance test; long-only in practice (WF SELL 15 trades); one broker feed.
- **Credible edge:** **Unconfirmed / weak.** Positive R in every WF window, but the USD result is negative, DEV is negative, and there is no permutation or bootstrap test.

### E16 — H4 EMA 21/50 crossover (rule-based)
- **Script:** `research_xauusd_ema_crossover.py`. **Outputs:** `xauusd_ema_crossover_trades.csv`, `xauusd_ema_crossover_results.csv`, `xauusd_ema_crossover_report.txt`.
- **Rules:** H4 EMA21/50 crossover; next-candle entry; SL 1.5×ATR14; TP 2R.
- **Main results:** 244 trades. Win rate 26.6% (break-even 33.3%). **−0.2008R average, −$931.22/oz**, profit factor 0.762.
- **Walk-forward:** WF1 −0.300R, WF2 −0.053R, WF3 0.000R (WF1–3 −0.106R, 104 trades).
- **Cost sensitivity:** identical at 1.0, 1.5 and 2.0× spread. Because SL and TP are placed relative to the fill, a higher spread flipped no outcome.
- **Limitations:** few trades per window.
- **Credible edge:** **No.**

## 6. Summary of evidence

| ID | Experiment | Unit tested | Walk-forward evidence | Credible edge |
|---|---|---|---|---|
| E0 | Legacy daily RF | — | none | Not assessable |
| E2/E3 | RF baseline + backtest | Trade R | Pooled −0.045R, CI below 0 | No |
| E4/E5 | Trade / confidence analysis | Descriptive | — | No |
| E6 | 7 RF configurations | Balanced accuracy, R | — | No |
| E7 | Label horizon | Balanced accuracy | No consistent gain | No |
| E8 | Feature families | Balanced accuracy | No consistent gain | No |
| E9 | DXY / yields | Balanced accuracy | No consistent gain | No |
| E10 | Calendar timing | Balanced accuracy | No consistent gain | No |
| E11 | Kronos-mini | Balanced accuracy, R | Below RF and chance | No |
| E12 | Conditional subgroups | Trade R | 0/102 survive FDR | No |
| E13 | M5 direction | Balanced accuracy (2-class) | +0.011–0.014 | No |
| E14 | M15 direction H4 | Balanced accuracy (2-class) | +0.022; pre-declared permutation check failed | **Unconfirmed** |
| E15 | EMA pullback | Trade R / USD | +0.091R WF in R, negative USD | **Unconfirmed / weak** |
| E16 | EMA crossover | Trade R / USD | −0.106R | No |

No experiment has shown a credible, cost-robust, walk-forward-stable edge.

## 7. Cross-cutting limitations and risks found in the audit

1. **Session clock defect** in `features_m5.py`: server time (Europe/Athens) is labelled UTC. Every RF experiment used session and hour features shifted 2–3 hours. This doesn't invalidate leakage safety, but session conclusions from E2–E14 are approximate.
2. **Validation reuse.** The same M5 validation period and WF windows were used by about 12 experiments, so they carry selection bias. Only the post-cutoff holdout is untouched.
3. **Short M5 history** (7.5 months; three windows of about 5 weeks). Effects below about 0.01–0.02 balanced accuracy, or about 0.05R, cannot be resolved.
4. **Bar-level spreads** are per-bar minimums (M5 median 4 points, 95th percentile 16 points; 92.9% of bars are below the 15-point floor). Real executable spreads and tick-level costs are unknown.
5. **Backtest P&L is unstable** under small training-row changes (E3, E8, E9). Use R across multiple windows, not single-period USD.
6. **Uncalibrated probabilities.** RF outputs cluster at 0.33–0.48 and do not rank outcomes (E5).
7. **Reproducibility.** There is no git repository. `requirements.txt` lacks `MetaTrader5`, `joblib` (it comes with scikit-learn), `torch` and Kronos. The research virtual environment lives outside the project (`%TEMP%\aibot_venv`). Integrity relies on the SHA-256 and prefix-hash snapshots inside each report.
8. **No M5 ingestion script** in the project for the primary dataset.
9. **No shared modules** for walk-forward, bootstrap or permutation testing; each research script reimplements them.
10. **Hardware:** Intel i7-7700HQ (4 cores), 24 GB RAM, NVIDIA GTX 1050 with 4 GB. RF and gradient boosting on CPU are fast. Kronos-mini inference took about 1 s per forecast on the GPU. Large deep models or RL are impractical.
