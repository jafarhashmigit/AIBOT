"""Phase 35 autonomous runner — historical bid/ask strategy re-evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase35.candles import build_m5_candles, ticks_by_m5
from phase35.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    H13_C_STATUS,
    MIN_RESOLVED_FOR_EVAL,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase35.data import dataset_inventory
from phase35.features import build_features
from phase35.independent import compare_summaries, recompute_from_trades
from phase35.progress import write_json
from phase35.strategies_runner import PREVIOUS_MEAN_R, run_all_strategies

UTC = timezone.utc


def _overall_verdict(results: dict[str, Any]) -> str:
    classes = [r["classification"]["verdict"] for r in results.values()]
    means = [
        (sid, r["view_a_historical_bidask"].get("mean_r"), r["view_a_historical_bidask"].get("n_resolved"))
        for sid, r in results.items()
    ]
    any_promising = any(c == "PROMISING" for c in classes)
    any_unconfirmed_pos = any(c == "UNCONFIRMED" for c in classes)
    any_pos = any(
        m is not None and n is not None and n >= MIN_RESOLVED_FOR_EVAL and m > 0 for _, m, n in means
    )
    all_insuff = all(c == "INSUFFICIENT_SAMPLE" for c in classes)
    if all_insuff:
        return "INSUFFICIENT_SAMPLE"
    if any_promising:
        return "REALISTIC_EXECUTION_EDGE_DETECTED_BUT_UNCONFIRMED"
    if any_unconfirmed_pos or any_pos:
        return "PROMISING_BUT_UNCONFIRMED"
    return "NO_EDGE_AFTER_REALISTIC_EXECUTION"


def _write_final_md(
    *,
    verdict: str,
    results: dict[str, Any],
    inventory: dict[str, Any],
    runtime: dict[str, Any],
    indep_ok: bool,
) -> None:
    rows = []
    for sid, r in results.items():
        a = r["view_a_historical_bidask"]
        prev = PREVIOUS_MEAN_R.get(sid)
        rows.append(
            f"| `{sid}` | {prev if prev is not None else 'n/a'} | "
            f"{a.get('mean_r')} | {a.get('n_resolved')} | {a.get('n_unresolved')} | "
            f"{a.get('profit_factor')} | {a.get('max_drawdown_r')} | {r['classification']['verdict']} |"
        )
    md = "\n".join(
        [
            "# Phase 35 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Executive verdict:** `{verdict}`",
            "",
            "## Strategy comparison",
            "",
            "| Strategy | Previous Mean R | Historical Bid/Ask Mean R | N Resolved | N Unresolved | PF | Max DD (R) | Verdict |",
            "|---|---|---|---|---|---|---|---|",
            *rows,
            "",
            "## Execution comparison",
            "",
            "- VIEW A: historical bid/ask tick-path (primary)",
            "- VIEW B: legacy frozen mid+floor+$0.05/side (comparison only)",
            "- VIEW C: stress = VIEW A minus unverified $0.05/side (sensitivity)",
            "- Spread is not double-counted on VIEW A; COMMISSION_UNVERIFIED; SLIPPAGE_UNVERIFIED",
            "",
            "## Data limitations",
            "",
            f"- Complete trading days only: **{inventory['n_complete_days']}** ({', '.join(inventory['complete_trading_days'])})",
            f"- Ticks used: **{inventory['n_ticks_loaded']}**",
            f"- Recomputed spread median/mean/p95: `{inventory['recomputed_spread_usd']}`",
            "- Missing/failed Phase 34 hours → UNRESOLVED_DATA_GAP (no fabrication)",
            "- MT5 parity: PENDING (not used)",
            "- Commercial licensing: not cleared",
            "- Tick-path coverage incomplete across selected 20-day set",
            "",
            "## Safety",
            "",
            f"- MT5 = NOT USED",
            f"- Broker orders = `{BROKER_ORDERS}`",
            f"- Discord = `{DISCORD_MESSAGES_SENT}`",
            f"- Telegram = `{TELEGRAM_MESSAGES_SENT}`",
            f"- Package installations = `{PACKAGES_INSTALLED}`",
            f"- Holdout accessed = `{HOLDOUT_ACCESSES > 0}`",
            "- Phase 0–34 = untouched",
            f"- Phase 34 immutable = `{inventory['immutability']['ok']}`",
            f"- Commit/push = `{GIT_COMMIT}` / `{GIT_PUSH}`",
            f"- Independent recompute OK = `{indep_ok}`",
            f"- Production = `{PRODUCTION_FINAL_ACTION}` | Champion = `{CHAMPION_STATUS}`",
            "",
            "## Runtime",
            "",
            f"- START_UTC: `{runtime['START_UTC']}`",
            f"- END_UTC: `{runtime['END_UTC']}`",
            f"- DURATION: `{runtime['DURATION']}`",
            "",
        ]
    )
    (REPORTS_DIR / "PHASE_35_FINAL_REPORT.md").write_text(md + "\n", encoding="utf-8")
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_35_RESULTS.md").write_text(md + "\n", encoding="utf-8")
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_35_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 35 — Research Plan",
                "",
                "Re-evaluate frozen strategies on Phase 34 Dukascopy bid/ask ticks with realistic execution.",
                "No MT5, no live data, no parameter optimization, no promotion.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    inventory, ticks = dataset_inventory()
    write_json("dataset_inventory.json", inventory)

    candle_pack = build_m5_candles(ticks)
    write_json(
        "candle_rebuild.json",
        {
            "n_candles": candle_pack["n_candles"],
            "missing_slots": candle_pack["inferred_missing_m5_slots"],
            "fabricated": False,
            "gap_filled": False,
        },
    )
    feat_bundle = build_features(candle_pack["candles"])
    tmap = ticks_by_m5(ticks)

    results = run_all_strategies(feat_bundle=feat_bundle, candle_pack=candle_pack, ticks_by_bar=tmap)

    # Independent recompute on all bid/ask trades
    indep_checks = {}
    all_ok = True
    slim_results = {}
    for sid, r in results.items():
        indep = recompute_from_trades(r["trades_bidask"])
        cmp = compare_summaries(r["view_a_historical_bidask"], indep)
        indep_checks[sid] = cmp
        if not cmp["ok"]:
            all_ok = False
        slim = {k: v for k, v in r.items() if k != "trades_bidask"}
        slim["trades_bidask_n"] = len(r["trades_bidask"])
        # keep a small sample of trades for audit
        slim["trades_bidask_sample"] = r["trades_bidask"][:20]
        slim_results[sid] = slim

    write_json("strategy_results.json", slim_results)
    write_json("independent_recompute.json", {"ok": all_ok, "by_strategy": indep_checks})

    if not all_ok:
        # Phase must fail validation if core results cannot be reproduced
        verdict = "INSUFFICIENT_SAMPLE"
        validation_failed = True
    else:
        verdict = _overall_verdict(results)
        validation_failed = False

    # Best candidate among those with mean_r>0 and max n_resolved
    best = None
    best_n = -1
    for sid, r in results.items():
        a = r["view_a_historical_bidask"]
        if a.get("mean_r") is not None and a["mean_r"] > 0 and a.get("n_resolved", 0) > best_n:
            best = sid
            best_n = a["n_resolved"]

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 35,
        "recipe_id": RECIPE_ID,
        "executive_verdict": verdict,
        "independent_recompute_ok": all_ok,
        "validation_failed": validation_failed,
        "best_candidate": best,
        "best_candidate_note": "validation observation only — not production approval" if best else None,
        "n_strategies": len(results),
        "dataset": {
            "complete_days": inventory["complete_trading_days"],
            "n_ticks": inventory["n_ticks_loaded"],
            "n_m5_candles": candle_pack["n_candles"],
            "spread_recomputed": inventory["recomputed_spread_usd"],
        },
        "strategy_verdicts": {sid: r["classification"] for sid, r in results.items()},
        "mt5_used": False,
        "live_data_used": False,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "broker_orders": BROKER_ORDERS,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "telegram_sent": TELEGRAM_MESSAGES_SENT > 0,
        "packages_installed": PACKAGES_INSTALLED,
        "phase34_immutable": inventory["immutability"]["ok"],
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    _write_final_md(
        verdict=verdict,
        results=slim_results,
        inventory=inventory,
        runtime=runtime,
        indep_ok=all_ok,
    )

    print(json.dumps({"executive_verdict": verdict, "best": best, "runtime": runtime}, indent=2))
    return final


if __name__ == "__main__":
    main()
