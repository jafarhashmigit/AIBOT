"""Download public GitHub raw sources for audit (stdlib only)."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent / "raw"

SOURCES = {
    "0xagarg_readme": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/README.md",
    "0xagarg_smc": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/src/smc_polars.py",
    "0xagarg_regime": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/src/regime_detector.py",
    "0xagarg_risk": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/src/risk_engine.py",
    "0xagarg_config": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/src/config.py",
    "0xagarg_feature": "https://raw.githubusercontent.com/0xagarg/xau-ai-trading-bot/main/src/feature_eng.py",
    "mooresi_readme": "https://raw.githubusercontent.com/MooreSi/forex-gold/main/README.md",
    "mooresi_license": "https://raw.githubusercontent.com/MooreSi/forex-gold/main/LICENSE",
    "kiran_bot": "https://raw.githubusercontent.com/Kiran-Kumbar/XAU-USD-Signal-Bot/main/bot.py",
    "kiran_readme": "https://raw.githubusercontent.com/Kiran-Kumbar/XAU-USD-Signal-Bot/main/README.md",
    "n30_readme": "https://raw.githubusercontent.com/n30dyn4m1c/gold-pro-scalper/master/README.md",
    "n30_breakout": "https://raw.githubusercontent.com/n30dyn4m1c/gold-pro-scalper/master/XAU_Quant_Reversion_Breakout.mq5",
    "n30_reversion": "https://raw.githubusercontent.com/n30dyn4m1c/gold-pro-scalper/master/XAU_Quant_Reversion_m1_OLHC.mq5",
    "sanket_readme": "https://raw.githubusercontent.com/sankett04/XAUUSD-signal-system/main/README.md",
    "sanket_gold": "https://raw.githubusercontent.com/sankett04/XAUUSD-signal-system/main/XAUUSD/backend/api/gold.py",
    "sanket_events": "https://raw.githubusercontent.com/sankett04/XAUUSD-signal-system/main/XAUUSD/backend/api/events.py",
    "sanket_routes": "https://raw.githubusercontent.com/sankett04/XAUUSD-signal-system/main/XAUUSD/backend/api/routes.py",
}


def fetch_all(timeout: int = 60) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, url in SOURCES.items():
        path = RAW_DIR / f"{name}.txt"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIBOT-phase25-audit/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            path.write_bytes(data)
            meta[name] = {"ok": True, "bytes": len(data), "url": url, "path": str(path)}
            print(f"OK {name} {len(data)}")
        except Exception as exc:  # noqa: BLE001
            meta[name] = {"ok": False, "error": str(exc), "url": url}
            print(f"FAIL {name}: {exc}")
    (RAW_DIR / "fetch_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    fetch_all()
