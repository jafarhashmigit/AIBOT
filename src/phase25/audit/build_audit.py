"""Build machine-readable repository audit from fetched sources (no code copy into strategies)."""

from __future__ import annotations

import json
import re
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT_PATH = Path(__file__).resolve().parents[3] / "reports" / "phase25" / "repo_audit.json"


def _read(name: str) -> str:
    p = RAW_DIR / f"{name}.txt"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _snip(text: str, pattern: str, window: int = 180) -> list[str]:
    out = []
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        a = max(0, m.start() - 40)
        b = min(len(text), m.end() + window)
        out.append(re.sub(r"\s+", " ", text[a:b]).strip())
        if len(out) >= 6:
            break
    return out


def audit_0xagarg() -> dict:
    smc = _read("0xagarg_smc")
    regime = _read("0xagarg_regime")
    risk = _read("0xagarg_risk")
    cfg = _read("0xagarg_config")
    readme = _read("0xagarg_readme")
    return {
        "repo": "https://github.com/0xagarg/xau-ai-trading-bot",
        "license": "MIT",
        "code_copied": False,
        "strategy": {
            "summary": "XGBoost ML signal on M15 with SMC features (OB/FVG/BOS/CHoCH), HMM regime, session filters.",
            "entry_exit": "Model BUY/SELL/HOLD + confidence filters; ATR-based SL; time exit ~6h; TP via risk engine.",
            "indicators_tf": "M15 OHLCV; SMC structure; 37 engineered features; HMM 3-state regime.",
            "regime": "HMM trending/ranging/volatile (regime_detector.py).",
            "sl_tp_sizing": "ATR min SL ~1.5x; Kelly sizing; daily/total loss caps; max 2 positions.",
            "costs": "Spread filter present in README/risk path; live MT5 execution (not used here).",
            "data_deps": "MetaTrader5, Polars, XGBoost, hmmlearn, Telegram, PostgreSQL, Next.js dashboard.",
            "reusable_math": "Closed-bar FVG/BOS concepts; ATR stops; session awareness; regime gating.",
            "look_ahead_risks": "ML labels and HMM fit windows must be audited for leakage; README backtest claims not independently verified; auto-retrain can overfit.",
            "evidence_snippets": _snip(smc, r"fvg|bos|choch|order.?block")
            + _snip(regime, r"hmm|regime|n_components")
            + _snip(risk, r"atr|kelly|stop")
            + _snip(cfg, r"SYMBOL|TIMEFRAME|ATR"),
            "readme_claim_note": "README reports strong backtest metrics; treat as unverified marketing until replicated on our data.",
            "implementation_policy": "Concepts only independently reimplemented in smc_liquidity + regime_router; no ML/HMM copy.",
        },
        "source_bytes": {"smc": len(smc), "regime": len(regime), "risk": len(risk), "readme": len(readme)},
    }


def audit_mooresi() -> dict:
    readme = _read("mooresi_readme")
    lic = _read("mooresi_license")
    agpl = "AGPL" in lic or "Affero" in lic or "AGPL" in readme
    return {
        "repo": "https://github.com/MooreSi/forex-gold",
        "license": "AGPL-3.0",
        "code_copied": False,
        "strategy": {
            "summary": "Telegram signal parsing + research engines + deterministic risk governor + MT5 EA trade management.",
            "entry_exit": "Signals originate from Telegram/research engines; EA manages entries/exits under risk governor.",
            "indicators_tf": "Multi-component stack (Python FastAPI + React + MQL5); exact indicator set varies by research engine.",
            "regime": "Risk governor / research engines may condition on market state; not a simple indicator bot.",
            "sl_tp_sizing": "Deterministic risk governor (documented in README); EA-native trade management.",
            "costs": "Broker/MT5 execution path; not isolated offline research.",
            "data_deps": "MT5, Telegram, FastAPI, React, VPS-oriented deployment.",
            "reusable_math": "High-level risk-governor idea (hard limits before discretionary signal execution).",
            "look_ahead_risks": "Telegram signal timing vs bar close can embed latency/look-ahead; AGPL precludes code reuse.",
            "evidence_snippets": _snip(readme, r"Telegram|risk|governor|MT5|research"),
            "implementation_policy": "AGPL — concepts only; no source incorporated into AIBOT.",
        },
        "agpl_confirmed": agpl,
        "source_bytes": {"readme": len(readme), "license": len(lic)},
    }


def audit_kiran() -> dict:
    bot = _read("kiran_bot")
    readme = _read("kiran_readme")
    return {
        "repo": "https://github.com/Kiran-Kumbar/XAU-USD-Signal-Bot",
        "license": "No LICENSE file in tree (treat as all-rights-reserved / not copyable).",
        "code_copied": False,
        "strategy": {
            "summary": "SMC market-structure + FVG signal bot posting to Telegram via TwelveData.",
            "entry_exit": "Structure/FVG based BUY/SELL alerts; Telegram delivery (signal bot, not full execution engine).",
            "indicators_tf": "SMC swings, BOS/CHoCH-style structure, FVG; timeframe configured in bot.py.",
            "regime": "Implicit via market structure (bullish/bearish structure changes).",
            "sl_tp_sizing": "Signal-oriented; SL/TP may be annotated in messages — not a full portfolio sizer.",
            "costs": "No rigorous spread/commission model in signal path.",
            "data_deps": "TwelveData API (paid potential), Telegram, Railway deploy.",
            "reusable_math": "Liquidity sweep / FVG / BOS confirmation patterns (independently rewritten).",
            "look_ahead_risks": "Pivot/swing confirmation lag if not strictly right-closed; paid API not used here.",
            "evidence_snippets": _snip(bot, r"FVG|BOS|CHoCH|liquidity|swing|TwelveData|Telegram"),
            "implementation_policy": "No code copy (unclear license); concepts independently in smc_liquidity.",
        },
        "source_bytes": {"bot": len(bot), "readme": len(readme)},
    }


def audit_n30() -> dict:
    readme = _read("n30_readme")
    br = _read("n30_breakout")
    rev = _read("n30_reversion")
    return {
        "repo": "https://github.com/n30dyn4m1c/gold-pro-scalper",
        "license": "MIT",
        "code_copied": False,
        "strategy": {
            "summary": "M1 XAUUSD mean-reversion scalpers (Z-score) + TickRobust cost-aware variant + dual MR/breakout EA.",
            "entry_exit": "Z-score deviation entries; ADX/Donchian filters in breakout variant; ATR-style exits in EAs.",
            "indicators_tf": "M1; Z-score; ADX; Donchian; tick-robust costing in TickRobust EA.",
            "regime": "ADX used as trend/range filter (high ADX → avoid MR / enable breakout depending on EA).",
            "sl_tp_sizing": "EA inputs for SL/TP and lot; TickRobust explicitly models costs.",
            "costs": "TickRobust variant designed around spread/slippage realism — useful research idea.",
            "data_deps": "MetaTrader 5 / MQL5 only.",
            "reusable_math": "Z-score mean reversion; Donchian breakout; ADX/vol filters; cost stress mindset.",
            "look_ahead_risks": "EveryTick mode can differ from closed-bar; M1 vs our M5 outcome schema mismatch.",
            "evidence_snippets": _snip(readme, r"Z-Score|ADX|Donchian|TickRobust|mean-reversion")
            + _snip(br, r"Donchian|ADX|ZScore|Inp")
            + _snip(rev, r"ZScore|ATR|spread"),
            "implementation_policy": "Independent Python reimplementation of Z/Donchian concepts on M5; no MQL5 copy.",
        },
        "source_bytes": {"readme": len(readme), "breakout": len(br), "reversion": len(rev)},
    }


def audit_sanket() -> dict:
    readme = _read("sanket_readme")
    gold = _read("sanket_gold")
    events = _read("sanket_events")
    routes = _read("sanket_routes")
    return {
        "repo": "https://github.com/sankett04/XAUUSD-signal-system",
        "license": "MIT",
        "code_copied": False,
        "strategy": {
            "summary": "Realtime XAUUSD signal checklist combining technical + fundamental factors (Streamlit UI).",
            "entry_exit": "Factor checklist / signal provider — not a closed execution strategy with SL/TP engine.",
            "indicators_tf": "Technical gold series via yfinance-style APIs; DXY; macro event calendar.",
            "regime": "Macro/event awareness rather than HMM/ADX regime.",
            "sl_tp_sizing": "Not a full risk engine; UI signal system.",
            "costs": "Not modeled as transaction-cost-aware backtest.",
            "data_deps": "yfinance / external APIs, Flask/FastAPI routes, Streamlit frontend.",
            "reusable_math": "Multi-factor confirmation idea; session/macro caution — not ported (no paid/external APIs).",
            "look_ahead_risks": "Event timestamps and yfinance alignment can leak if not point-in-time; outside our approved dataset.",
            "evidence_snippets": _snip(readme, r"factor|signal|XAU|fundamental")
            + _snip(gold, r"yfinance|gold|download")
            + _snip(events, r"event|calendar|impact")
            + _snip(routes, r"signal|gold|dxy"),
            "implementation_policy": "No external API use; MTF H1+M5 uses only approved local features.",
        },
        "source_bytes": {
            "readme": len(readme),
            "gold": len(gold),
            "events": len(events),
            "routes": len(routes),
        },
    }


def build() -> dict:
    report = {
        "report": "phase25_repo_audit",
        "policy": {
            "no_proprietary_copy": True,
            "agpl_no_code_reuse": True,
            "unclear_license_no_copy": True,
            "mit_concepts_only_independent_rewrite": True,
        },
        "repositories": [
            audit_0xagarg(),
            audit_mooresi(),
            audit_kiran(),
            audit_n30(),
            audit_sanket(),
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = build()
    print("wrote", OUT_PATH)
    print("repos", len(r["repositories"]))
