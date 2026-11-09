# PHASE 25 — Strategy Research Plan & Repository Audit

Recipe: `phase25_strategy_discovery_v1`

## Scope & Safety

- Isolated under `src/phase25/`.
- H13_C remains frozen EXPERIMENTAL benchmark.
- Champion remains `NO_MODEL`; production `final_action=WAIT`.
- No holdout access, MT5, Discord, Telegram, OCI, package installs, or git push.
- No autonomous retraining / RL.

## Predeclared parameters

```json
{
  "mean_reversion": {
    "z_window": 40,
    "z_entry": 1.75,
    "rsi_buy_max": 35.0,
    "rsi_sell_min": 65.0,
    "atr_pct_min": 0.0003,
    "atr_pct_max": 0.0025,
    "vol_ratio_max": 1.35
  },
  "breakout_retest": {
    "donchian_n": 20,
    "min_break_atr_pct": 0.15,
    "retest_tol_atr_pct": 0.35,
    "false_break_lookback": 3
  },
  "smc_liquidity": {
    "swing_lookback": 3,
    "fvg_min_atr_frac": 0.15,
    "require_bos": true
  },
  "regime_router": {
    "ema_spread_trend": 0.00035,
    "atr_pct_highvol": 0.0018,
    "trend_pullback_z": 0.75
  },
  "mtf_h1_m5": {
    "m5_rsi_buy_max": 45.0,
    "m5_rsi_sell_min": 55.0,
    "ema_spread_confirm": 0.0,
    "require_h1_align": true
  }
}
```

## Repository audits (source-inspected)

### https://github.com/0xagarg/xau-ai-trading-bot

- License: **MIT**
- Code copied into AIBOT: **False**
- Strategy: XGBoost ML on XAUUSD M15 with SMC (OB/FVG/BOS/CHoCH), HMM regime, session filters, MT5 execution.
- Entry/exit: Model BUY/SELL/HOLD with confidence/session filters; ATR SL (~1.5x); time exit ~6h; max 2 positions.
- Indicators/TF: M15 OHLCV; 37 engineered features; SMC structure; HMM 3-state regime.
- Regime: HMM trending/ranging/volatile.
- SL/TP/sizing: ATR stops; Kelly-inspired sizing; daily 5% / total 10% loss caps.
- Costs: Spread filter in risk path; live MT5 (not used in Phase 25).
- Data/deps: MetaTrader5, Polars, XGBoost, hmmlearn, Telegram, PostgreSQL.
- Reusable math: Closed-bar FVG/BOS ideas; ATR stops; session/regime gating.
- Look-ahead / repaint risks: Label construction + HMM fit windows need leakage audit; README backtest unverified; auto-retrain overfitting risk.
- Implementation policy: Independent rewrite of SMC/regime concepts only; no ML/HMM code copied.

### https://github.com/MooreSi/forex-gold

- License: **AGPL-3.0**
- Code copied into AIBOT: **False**
- Strategy: Telegram signal parsing + research engines + deterministic risk governor + MT5 EA management (FastAPI/React).
- Entry/exit: External/Telegram/research signals executed under risk governor; EA manages trades.
- Indicators/TF: Multi-engine stack; not a single indicator recipe.
- Regime: Risk-governor conditioning rather than a simple ADX/HMM block.
- SL/TP/sizing: Deterministic risk governor limits.
- Costs: Broker/MT5 path; not an offline cost-model research package.
- Data/deps: MT5, Telegram, FastAPI, React, VPS.
- Reusable math: Hard risk limits before discretionary signal execution (conceptual).
- Look-ahead / repaint risks: Telegram timestamp vs bar-close latency; AGPL forbids incorporating source.
- Implementation policy: AGPL — zero source reuse; concepts only.

### https://github.com/Kiran-Kumbar/XAU-USD-Signal-Bot

- License: **No LICENSE in tree (treat as non-copyable)**
- Code copied into AIBOT: **False**
- Strategy: SMC structure + FVG signal bot to Telegram using TwelveData.
- Entry/exit: Structure/FVG alerts; Telegram delivery (signal bot).
- Indicators/TF: Swings, BOS/CHoCH-style structure, FVG; configured TF in bot.py.
- Regime: Implicit via market-structure flips.
- SL/TP/sizing: Signal annotations; not a full portfolio engine.
- Costs: No rigorous spread/commission model.
- Data/deps: TwelveData API, Telegram, Railway.
- Reusable math: Liquidity sweep / FVG / BOS confirmation patterns.
- Look-ahead / repaint risks: Swing confirmation lag/repaint if not right-closed; paid API unused here.
- Implementation policy: No code copy; independent smc_liquidity module.

### https://github.com/n30dyn4m1c/gold-pro-scalper

- License: **MIT**
- Code copied into AIBOT: **False**
- Strategy: M1 XAUUSD mean-reversion Z-score scalpers + TickRobust cost-aware EA + MR/breakout dual EA.
- Entry/exit: Z-score entries; ADX/Donchian filters in breakout variant; EA SL/TP inputs.
- Indicators/TF: M1; Z-score; ADX; Donchian.
- Regime: ADX as trend/range filter.
- SL/TP/sizing: EA inputs; TickRobust emphasizes realistic costs.
- Costs: TickRobust models spread/slippage awareness — useful research mindset.
- Data/deps: MetaTrader 5 / MQL5.
- Reusable math: Z-score MR; Donchian breakout; ADX/vol filters; cost stress.
- Look-ahead / repaint risks: EveryTick vs closed-bar divergence; M1 vs our M5 outcome schema.
- Implementation policy: Independent Python M5 rewrite of Z/Donchian concepts; no MQL5 copy.

### https://github.com/sankett04/XAUUSD-signal-system

- License: **MIT**
- Code copied into AIBOT: **False**
- Strategy: Realtime multi-factor XAUUSD checklist (technical + fundamental) with Streamlit UI.
- Entry/exit: Signal provider / checklist — not a full SL/TP execution strategy.
- Indicators/TF: Gold series + DXY + macro event calendar.
- Regime: Macro/event awareness.
- SL/TP/sizing: Not a risk engine.
- Costs: Not transaction-cost backtested in-repo.
- Data/deps: yfinance-style APIs, Flask routes, Streamlit.
- Reusable math: Multi-factor confirmation idea only.
- Look-ahead / repaint risks: Event/yfinance point-in-time hazards; outside approved local dataset.
- Implementation policy: No external APIs; MTF uses approved local H1/M5 features only.

## Independent hypotheses implemented

1. `mean_reversion` — Z-score + RSI + ATR/vol filters
2. `breakout_retest` — Donchian break + retest + false-break filter
3. `smc_liquidity` — liquidity sweep + BOS/CHoCH + FVG (closed-bar)
4. `regime_router` — past-only trending/ranging/high-vol routing
5. `mtf_h1_m5` — H1 bias + M5 RSI/EMA confirmation (not H13_C cuts)

## Evaluation contract

- Same approved features/outcomes/H1 as Phase 14.
- Same WF1–WF3 windows, purge/embargo, day-cluster bootstrap.
- Identical outcome costs (spread/commission/slippage embedded in `m5_side_outcomes`).
- Single confirmatory pass; no iterative retuning on validation.

## Preflight

```json
{
  "n_timestamps": 18234,
  "n_features": 42450,
  "n_outcomes": 81036,
  "bounds": {
    "n_oos": 18234,
    "first": "2026-06-19 03:05:00",
    "last": "2026-09-29 17:50:00",
    "max_decision_time": "2026-09-29 17:50:00",
    "research_cutoff": "2026-09-29 18:50:00",
    "holdout_opened": false
  },
  "fold_timestamp_counts": {
    "WF1": 6078,
    "WF2": 6078,
    "WF3": 6078
  },
  "safety_all_pass": true,
  "audit_mode": "offline_compiled_from_inspected_public_sources",
  "repos_audited": 5
}
```

