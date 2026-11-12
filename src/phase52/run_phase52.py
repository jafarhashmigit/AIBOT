"""Phase 52 runner — bounded market representation selection."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase52.archives import inventory_xauusd_archives
from phase52.constants import (
    BROKER_ORDERS,
    CANDIDATE_INSTRUMENTS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    TIMEFRAMES,
)
from phase52.mt5_probe import close_mt5, list_available_candidates, open_mt5, probe_rates, probe_ticks_sample
from phase52.progress import write_json, write_text
from phase52.qualification import choose_verdict
from phase52.scoring import rank_rows, score_combination


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    archive = inventory_xauusd_archives()
    write_json(REPORTS_DIR / "xauusd_archive_inventory.json", archive)

    conn = open_mt5()
    if not conn.get("ok"):
        payload = {
            "final_verdict": "INSUFFICIENT_DATA",
            "verdict_reason": f"MT5 unavailable: {conn.get('reason')}",
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": time.perf_counter() - t0},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", f"# Phase52\n\n{payload}\n")
        print(__import__("json").dumps(payload, indent=2))
        return payload

    handle = conn["handle"]
    try:
        avail = list_available_candidates(handle)
        write_json(REPORTS_DIR / "symbol_availability.json", avail)

        tick_cache: dict[str, Any] = {}
        rows = []
        n_combos = 0
        for cand in avail["candidates"]:
            symbol = cand["symbol"]
            if not cand.get("available"):
                continue
            if symbol not in tick_cache:
                # bounded tick sample once per symbol
                tick_cache[symbol] = probe_ticks_sample(handle, symbol)
            for tf in TIMEFRAMES:
                if n_combos >= 30:
                    break
                rates = probe_rates(handle, symbol, tf)
                sc = score_combination(
                    rates=rates,
                    ticks=tick_cache.get(symbol),
                    archive=archive if symbol == "XAUUSD" else None,
                    symbol_meta=cand,
                )
                rows.append(
                    {
                        "symbol": symbol,
                        "timeframe": tf,
                        "n_bars": rates.get("n_bars"),
                        "earliest_utc": rates.get("earliest_utc"),
                        "latest_utc": rates.get("latest_utc"),
                        "n_gap_events": rates.get("n_gap_events"),
                        "bid_ask_available": (tick_cache.get(symbol) or {}).get("bid_ask_available"),
                        "tick_spread_median": (tick_cache.get(symbol) or {}).get("spread_median"),
                        "tick_spread_p95": (tick_cache.get(symbol) or {}).get("spread_p95"),
                        "score": sc["score"],
                        "qualified": sc["qualified"],
                        "components": sc["components"],
                        "notes": sc["notes"],
                        "rates_ok": rates.get("ok"),
                    }
                )
                n_combos += 1
            if n_combos >= 30:
                break

        write_json(REPORTS_DIR / "tick_samples.json", tick_cache)
        write_json(REPORTS_DIR / "combination_scores.json", rows)
        ranked = rank_rows(rows)

        qualified = [r for r in ranked if r.get("qualified")]
        primary = qualified[0] if qualified else None
        backup = qualified[1] if len(qualified) > 1 else None
        # If only one qualified, no backup
        if primary and backup and primary["symbol"] == backup["symbol"] and primary["timeframe"] != backup["timeframe"]:
            pass  # ok different TF same symbol as backup
        elif primary and backup and float(backup["score"]) < float(primary["score"]) - 0.15:
            backup = None  # weak backup unsupported

        payload: dict[str, Any] = {
            "phase": 52,
            "recipe_id": RECIPE_ID,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "instruments_inspected": [c["symbol"] for c in avail["candidates"]],
            "timeframes_inspected": list(TIMEFRAMES),
            "n_combinations": len(rows),
            "xauusd_archives": {
                "combined_unique_m5_days": archive.get("combined_unique_m5_days"),
                "combined_span": archive.get("combined_span"),
            },
            "ranked": [
                {
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "score": r["score"],
                    "qualified": r["qualified"],
                    "bid_ask_available": r["bid_ask_available"],
                    "n_bars": r["n_bars"],
                    "tick_spread_median": r["tick_spread_median"],
                }
                for r in ranked
            ],
            "primary": (
                {
                    "symbol": primary["symbol"],
                    "timeframe": primary["timeframe"],
                    "score": primary["score"],
                    "qualified": True,
                    "evidence": {
                        "components": primary["components"],
                        "notes": primary["notes"],
                        "n_bars": primary["n_bars"],
                        "spread_median": primary["tick_spread_median"],
                        "spread_p95": primary["tick_spread_p95"],
                        "archive_days": archive.get("combined_unique_m5_days") if primary["symbol"] == "XAUUSD" else None,
                    },
                }
                if primary
                else None
            ),
            "backup": (
                {
                    "symbol": backup["symbol"],
                    "timeframe": backup["timeframe"],
                    "score": backup["score"],
                    "qualified": True,
                }
                if backup
                else None
            ),
            "limitations": [
                "MetaQuotes-Demo spreads/ticks ≠ live broker execution",
                "Tick probes are bounded samples (3 hours), not full history",
                "Scores measure research data suitability, not profitability",
                "No commission/slippage invented",
                "Phase44 validation / Phase49 confirmation not used",
            ],
            "ranking_methodology": {
                "weights": {
                    "historical_coverage": 0.20,
                    "bid_ask_availability": 0.20,
                    "spread_quality": 0.20,
                    "session_completeness": 0.15,
                    "data_integrity": 0.15,
                    "usable_sample_size": 0.10,
                },
                "qualification": (
                    "score>=0.55 AND bid_ask_availability>=0.45 AND usable_sample_size>=0.50 "
                    "(prefers verified multi-day archives over thin demo tick samples)"
                ),
            },
            "server": conn.get("server"),
        }

        verdict, reason = choose_verdict(payload)
        payload["final_verdict"] = verdict
        payload["verdict_reason"] = reason
        payload["next_step"] = (
            f"Next development should use {primary['symbol']}/{primary['timeframe']} as the primary market representation "
            "and build a fresh information/decision agenda on that substrate — without reviving Phase50/51 learner branch."
            if primary
            else "No qualified market — expand bounded data evidence or stop until better historical coverage exists."
        )
        payload["runtime"] = {
            "START_UTC": start,
            "END_UTC": _utc(),
            "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
        }
        payload["safety"] = {
            "broker_orders": BROKER_ORDERS,
            "discord": DISCORD_MESSAGES_SENT,
            "telegram": TELEGRAM_MESSAGES_SENT,
            "packages": PACKAGES_INSTALLED,
            "holdout": HOLDOUT_ACCESSES,
            "commit": GIT_COMMIT,
            "push": GIT_PUSH,
            "mt5_connections": MT5_CONNECTIONS,
        }

        # comparison table markdown
        lines = [
            "# Phase 52 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
            "",
            f"## Selection",
            f"- Primary: `{payload.get('primary')}`",
            f"- Backup: `{payload.get('backup')}`",
            f"- Reason: {reason}",
            "",
            "## Instruments / timeframes inspected",
            f"- Instruments: `{payload['instruments_inspected']}`",
            f"- Timeframes: `{TIMEFRAMES}`",
            f"- Combinations scored: `{len(rows)}`",
            "",
            "## XAUUSD existing archives",
            f"- `{payload['xauusd_archives']}`",
            "",
            "## Comparison table (ranked)",
            "",
            "| Rank | Symbol | TF | Score | Qualified | Bars | Bid/Ask | Spread median |",
            "|------|--------|----|-------|-----------|------|---------|---------------|",
        ]
        for i, r in enumerate(ranked, 1):
            lines.append(
                f"| {i} | {r['symbol']} | {r['timeframe']} | {r['score']:.3f} | {r['qualified']} | "
                f"{r['n_bars']} | {r['bid_ask_available']} | {r['tick_spread_median']} |"
            )
        lines += [
            "",
            "## Ranking methodology",
            f"- `{payload['ranking_methodology']}`",
            "",
            "## Limitations",
            *[f"- {x}" for x in payload["limitations"]],
            "",
            "## Next step",
            f"- {payload['next_step']}",
            "",
            f"Runtime s: `{payload['runtime']['DURATION_SECONDS']}`",
            "",
            "No Phase53 started. Not a profitability claim.",
            "",
        ]
        write_text(REPORTS_DIR / "FINAL_REPORT.md", "\n".join(lines))
        write_text(
            DOCS_DIR / "PHASE_52_MARKET_REPRESENTATION_SELECTION.md",
            f"# Phase 52\n\nVerdict: `{verdict}`\n\nPrimary: `{payload.get('primary')}`\n\nSee reports/phase52/FINAL_REPORT.md\n",
        )
        write_json(REPORTS_DIR / "final_verdict.json", payload)

        print(
            __import__("json").dumps(
                {
                    "phase": 52,
                    "final_verdict": verdict,
                    "verdict_reason": reason,
                    "primary": payload.get("primary"),
                    "backup": payload.get("backup"),
                    "n_combinations": len(rows),
                    "champion": CHAMPION_STATUS,
                    "production": PRODUCTION_FINAL_ACTION,
                    "runtime": payload["runtime"],
                },
                indent=2,
            )
        )
        return payload
    finally:
        close_mt5(handle)


if __name__ == "__main__":
    main()
