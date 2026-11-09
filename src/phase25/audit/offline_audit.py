"""Offline repository audit compiled from inspected public metadata/source (no live download required)."""

from __future__ import annotations

import json
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parents[3] / "reports" / "phase25" / "repo_audit.json"


def build_offline_audit() -> dict:
    """
    Evidence basis:
    - GitHub API license/description/tree listings fetched during Phase 25 preflight.
    - README / primary module content inspected via public raw URLs (not copied into strategies).
    AGPL / unclear-license repos: concepts only.
    """
    report = {
        "report": "phase25_repo_audit",
        "mode": "offline_compiled_from_inspected_public_sources",
        "policy": {
            "no_proprietary_copy": True,
            "agpl_no_code_reuse": True,
            "unclear_license_no_copy": True,
            "mit_concepts_only_independent_rewrite": True,
        },
        "repositories": [
            {
                "repo": "https://github.com/0xagarg/xau-ai-trading-bot",
                "license": "MIT",
                "code_copied": False,
                "inspected_paths": [
                    "README.md",
                    "src/smc_polars.py",
                    "src/regime_detector.py",
                    "src/risk_engine.py",
                    "src/config.py",
                    "src/feature_eng.py",
                    "src/ml_model.py",
                ],
                "strategy": {
                    "summary": "XGBoost ML on XAUUSD M15 with SMC (OB/FVG/BOS/CHoCH), HMM regime, session filters, MT5 execution.",
                    "entry_exit": "Model BUY/SELL/HOLD with confidence/session filters; ATR SL (~1.5x); time exit ~6h; max 2 positions.",
                    "indicators_tf": "M15 OHLCV; 37 engineered features; SMC structure; HMM 3-state regime.",
                    "regime": "HMM trending/ranging/volatile.",
                    "sl_tp_sizing": "ATR stops; Kelly-inspired sizing; daily 5% / total 10% loss caps.",
                    "costs": "Spread filter in risk path; live MT5 (not used in Phase 25).",
                    "data_deps": "MetaTrader5, Polars, XGBoost, hmmlearn, Telegram, PostgreSQL.",
                    "reusable_math": "Closed-bar FVG/BOS ideas; ATR stops; session/regime gating.",
                    "look_ahead_risks": "Label construction + HMM fit windows need leakage audit; README backtest unverified; auto-retrain overfitting risk.",
                    "implementation_policy": "Independent rewrite of SMC/regime concepts only; no ML/HMM code copied.",
                },
            },
            {
                "repo": "https://github.com/MooreSi/forex-gold",
                "license": "AGPL-3.0",
                "code_copied": False,
                "inspected_paths": ["README.md", "LICENSE", "repository tree listing"],
                "strategy": {
                    "summary": "Telegram signal parsing + research engines + deterministic risk governor + MT5 EA management (FastAPI/React).",
                    "entry_exit": "External/Telegram/research signals executed under risk governor; EA manages trades.",
                    "indicators_tf": "Multi-engine stack; not a single indicator recipe.",
                    "regime": "Risk-governor conditioning rather than a simple ADX/HMM block.",
                    "sl_tp_sizing": "Deterministic risk governor limits.",
                    "costs": "Broker/MT5 path; not an offline cost-model research package.",
                    "data_deps": "MT5, Telegram, FastAPI, React, VPS.",
                    "reusable_math": "Hard risk limits before discretionary signal execution (conceptual).",
                    "look_ahead_risks": "Telegram timestamp vs bar-close latency; AGPL forbids incorporating source.",
                    "implementation_policy": "AGPL — zero source reuse; concepts only.",
                },
                "agpl_confirmed": True,
            },
            {
                "repo": "https://github.com/Kiran-Kumbar/XAU-USD-Signal-Bot",
                "license": "No LICENSE in tree (treat as non-copyable)",
                "code_copied": False,
                "inspected_paths": ["bot.py", "README.md", "requirements.txt"],
                "strategy": {
                    "summary": "SMC structure + FVG signal bot to Telegram using TwelveData.",
                    "entry_exit": "Structure/FVG alerts; Telegram delivery (signal bot).",
                    "indicators_tf": "Swings, BOS/CHoCH-style structure, FVG; configured TF in bot.py.",
                    "regime": "Implicit via market-structure flips.",
                    "sl_tp_sizing": "Signal annotations; not a full portfolio engine.",
                    "costs": "No rigorous spread/commission model.",
                    "data_deps": "TwelveData API, Telegram, Railway.",
                    "reusable_math": "Liquidity sweep / FVG / BOS confirmation patterns.",
                    "look_ahead_risks": "Swing confirmation lag/repaint if not right-closed; paid API unused here.",
                    "implementation_policy": "No code copy; independent smc_liquidity module.",
                },
            },
            {
                "repo": "https://github.com/n30dyn4m1c/gold-pro-scalper",
                "license": "MIT",
                "code_copied": False,
                "inspected_paths": [
                    "README.md",
                    "XAU_Quant_Reversion_Breakout.mq5",
                    "XAU_Quant_Reversion_TickRobust.mq5",
                    "XAU_Quant_Reversion_m1_OLHC.mq5",
                ],
                "strategy": {
                    "summary": "M1 XAUUSD mean-reversion Z-score scalpers + TickRobust cost-aware EA + MR/breakout dual EA.",
                    "entry_exit": "Z-score entries; ADX/Donchian filters in breakout variant; EA SL/TP inputs.",
                    "indicators_tf": "M1; Z-score; ADX; Donchian.",
                    "regime": "ADX as trend/range filter.",
                    "sl_tp_sizing": "EA inputs; TickRobust emphasizes realistic costs.",
                    "costs": "TickRobust models spread/slippage awareness — useful research mindset.",
                    "data_deps": "MetaTrader 5 / MQL5.",
                    "reusable_math": "Z-score MR; Donchian breakout; ADX/vol filters; cost stress.",
                    "look_ahead_risks": "EveryTick vs closed-bar divergence; M1 vs our M5 outcome schema.",
                    "implementation_policy": "Independent Python M5 rewrite of Z/Donchian concepts; no MQL5 copy.",
                },
            },
            {
                "repo": "https://github.com/sankett04/XAUUSD-signal-system",
                "license": "MIT",
                "code_copied": False,
                "inspected_paths": [
                    "README.md",
                    "XAUUSD/backend/api/gold.py",
                    "XAUUSD/backend/api/events.py",
                    "XAUUSD/backend/api/routes.py",
                    "XAUUSD/frontend/streamlit_app.py",
                ],
                "strategy": {
                    "summary": "Realtime multi-factor XAUUSD checklist (technical + fundamental) with Streamlit UI.",
                    "entry_exit": "Signal provider / checklist — not a full SL/TP execution strategy.",
                    "indicators_tf": "Gold series + DXY + macro event calendar.",
                    "regime": "Macro/event awareness.",
                    "sl_tp_sizing": "Not a risk engine.",
                    "costs": "Not transaction-cost backtested in-repo.",
                    "data_deps": "yfinance-style APIs, Flask routes, Streamlit.",
                    "reusable_math": "Multi-factor confirmation idea only.",
                    "look_ahead_risks": "Event/yfinance point-in-time hazards; outside approved local dataset.",
                    "implementation_policy": "No external APIs; MTF uses approved local H1/M5 features only.",
                },
            },
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = build_offline_audit()
    print("wrote", OUT_PATH, "repos", len(r["repositories"]))
