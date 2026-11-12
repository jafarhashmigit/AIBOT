"""Phase 46 runner — costed EV foundation only. No strategy discovery."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase46.baselines import evaluate_baselines
from phase46.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DATA_OUT_DIR,
    DECISION_STRIDE,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    ENGINEERING_DATES,
    FORBIDDEN_VALIDATION_DATES,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    canonical_json_sha256,
)
from phase46.contract import build_research_contract
from phase46.cost_scenarios import COST_SCENARIO_REGISTRY
from phase46.data import (
    engineering_dates_present,
    load_m5,
    load_ticks,
    ticks_by_m5_bar,
    verify_no_forbidden_access,
)
from phase46.independent import verify_outcomes
from phase46.outcomes import build_day_outcomes
from phase46.progress import append_jsonl, write_json, write_text
from phase46.qualification import choose_verdict


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_docs(contract: dict[str, Any], verdict: str, reason: str) -> str:
    return f"""# Phase 46 — Costed Expected Value Foundation

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

## Purpose
M1 foundation: action-conditioned BUY/SELL/WAIT outcomes with bid/ask execution,
gross vs net separation, explicit cost scenarios, and independent recomputation.

This phase does **not** discover or promote a trading edge.

## Frozen contract
- Contract SHA-256: `{contract["contract_sha256"]}`
- Horizon: `{contract["horizons"]["horizon_bars"]}` M5 bars
- BUY entry ASK / exit BID; SELL entry BID / exit ASK
- WAIT: zero incremental PnL and costs (no opportunity-cost model here)
- Commission/slippage under OBSERVED_BIDASK_ONLY: **UNKNOWN** (not invented)
- Demo source is **not** live broker truth

## Data exposure
- Engineering dates: Phase44 discovery dates only (already exposed)
- Forbidden: Phase44 validation dates, holdout, legacy tests
- Independent validation is **not** claimed

## Out of scope
Neural nets, RL, bandits, online policy updates, strategy discovery,
indicator screens, live trading, model promotion.

## Final verdict
`{verdict}` — {reason}

See `reports/phase46/FINAL_REPORT.md`.
"""


def _render_final_report(payload: dict[str, Any]) -> str:
    c = payload["contract"]
    b = payload["baselines"]
    lines = [
        "# Phase 46 — Final Report",
        "",
        f"**Recipe:** `{payload['recipe_id']}`",
        f"**Verdict:** `{payload['final_verdict']}`",
        f"**Champion:** `{payload['champion']}` | **Production:** `{payload['production']}`",
        "",
        "## Executive finding",
        f"- {payload['verdict_reason']}",
        f"- Contract SHA-256: `{c['contract_sha256']}`",
        f"- Independent verification OK: `{payload['independent']['ok']}`",
        f"- Forbidden-date gate OK: `{payload['data_gate']['ok']}`",
        f"- Mid-price fills used: `{payload['mid_price_used']}`",
        "",
        "## 1. Research contract (frozen before evaluation)",
        f"- Target: `{c['target_definition']['primary']}`",
        f"- Horizon bars: `{c['horizons']['horizon_bars']}`",
        f"- Risk: `{c['risk_normalization']['risk_amount']}`",
        f"- Engineering dates n=`{len(c['data_exposure']['engineering_dates'])}`",
        f"- Forbidden validation dates locked: `{len(c['data_exposure']['forbidden_validation_dates'])}`",
        "",
        "## 2. Outcome architecture",
        f"- OK BUY outcomes: `{payload['counts']['ok_buy']}`",
        f"- OK SELL outcomes: `{payload['counts']['ok_sell']}`",
        f"- WAIT outcomes: `{payload['counts']['wait']}`",
        f"- Outcome dataset: `{payload['artifacts']['outcomes_jsonl']}`",
        "",
        "## 3. Cost scenarios",
    ]
    for sid, sc in COST_SCENARIO_REGISTRY.items():
        lines.append(f"- `{sid}`: {sc['description']}")
    lines += [
        "",
        "## 4. Baseline comparison (diagnostic only — not an edge claim)",
        f"- Note: {b.get('note')}",
    ]
    for bid, block in (b.get("baselines") or {}).items():
        obs = (block.get("by_scenario") or {}).get("OBSERVED_BIDASK_ONLY") or {}
        lines.append(
            f"- `{bid}`: n={block.get('n_selected')}, "
            f"mean_net_R={obs.get('mean_net_r')}, "
            f"win_rate={obs.get('win_rate')}, "
            f"max_concurrent={((block.get('exposure') or {}).get('max_concurrent_positions'))}"
        )
    lines += [
        "",
        "## 5. Independent verification",
        f"- Method: `{payload['independent'].get('method')}`",
        f"- Checked: `{payload['independent'].get('checked')}`",
        f"- Mismatches: `{payload['independent'].get('n_mismatches')}`",
        f"- Duplicate keys: `{payload['independent'].get('duplicate_keys')}`",
        "",
        "## 6. Safety / exposure",
        f"- Accessed dates: `{payload['data_gate'].get('accessed_dates')}`",
        f"- Forbidden hits: `{payload['data_gate'].get('forbidden_hits')}`",
        f"- Orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime seconds: `{payload['runtime'].get('DURATION_SECONDS')}`",
        "",
        "## Final verdict",
        f"- `{payload['final_verdict']}`",
        f"- {payload['verdict_reason']}",
        "",
        "No Phase47 started. No profitability claim. Champion remains NO_MODEL.",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc_now()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Freeze contract BEFORE evaluations
    contract = build_research_contract()
    write_json(REPORTS_DIR / "research_contract.json", contract)
    contract_hash_locked = contract["contract_sha256"]
    # Re-hash without trusting stored field
    contract_ok = (
        canonical_json_sha256({k: v for k, v in contract.items() if k != "contract_sha256"})
        == contract_hash_locked
    )

    write_json(REPORTS_DIR / "cost_scenario_registry.json", COST_SCENARIO_REGISTRY)

    present = engineering_dates_present()
    accessed: list[str] = []
    all_rows: list[dict[str, Any]] = []
    m5_by_day: dict[str, list] = {}
    ticks_by_day: dict[str, dict] = {}

    for day in present:
        # Hard gate before load
        if day in FORBIDDEN_VALIDATION_DATES:
            raise RuntimeError(f"refusing forbidden date {day}")
        accessed.append(day)
        m5 = load_m5(day)
        ticks = load_ticks(day)
        by_bar = ticks_by_m5_bar(ticks)
        m5_by_day[day] = m5
        ticks_by_day[day] = by_bar
        day_rows = build_day_outcomes(
            day=day,
            m5=m5,
            ticks_by_bar=by_bar,
            actions=("BUY", "SELL", "WAIT"),
            stride=DECISION_STRIDE,
        )
        all_rows.extend(day_rows)

    outcomes_path = DATA_OUT_DIR / "action_conditioned_outcomes.jsonl"
    append_jsonl(outcomes_path, all_rows)
    write_json(
        REPORTS_DIR / "outcome_manifest.json",
        {
            "n_rows": len(all_rows),
            "sha256_of_path_note": "per-row outcome_sha256; see outcomes file",
            "engineering_dates": present,
            "contract_sha256": contract_hash_locked,
            "stride": DECISION_STRIDE,
        },
    )

    data_gate = verify_no_forbidden_access(accessed)
    # Also assert we never listed a forbidden engineering date
    assert not (set(ENGINEERING_DATES) & FORBIDDEN_VALIDATION_DATES)

    baselines = evaluate_baselines(all_rows, list(COST_SCENARIO_REGISTRY.keys()))
    write_json(REPORTS_DIR / "baseline_comparison.json", baselines)

    independent = verify_outcomes(
        all_rows,
        m5_by_day=m5_by_day,
        ticks_by_day=ticks_by_day,
        max_checks=250,
    )
    write_json(REPORTS_DIR / "independent_verification.json", independent)

    ok_buy = sum(1 for r in all_rows if r.get("action") == "BUY" and r.get("data_quality_status") == "OK")
    ok_sell = sum(1 for r in all_rows if r.get("action") == "SELL" and r.get("data_quality_status") == "OK")
    n_wait = sum(1 for r in all_rows if r.get("action") == "WAIT")
    mid_used = any(r.get("mid_price_used") for r in all_rows if r.get("action") in ("BUY", "SELL"))

    verdict, reason = choose_verdict(
        contract_ok=contract_ok,
        independent_ok=bool(independent.get("ok")),
        data_gate_ok=bool(data_gate.get("ok")),
        n_ok_buy=ok_buy,
        n_ok_sell=ok_sell,
        n_wait=n_wait,
        scenarios_present=len(COST_SCENARIO_REGISTRY) >= 2,
        mid_price_used=bool(mid_used),
    )

    end = _utc_now()
    runtime = {
        "START_UTC": start,
        "END_UTC": end,
        "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
    }

    payload: dict[str, Any] = {
        "phase": 46,
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict,
        "verdict_reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "contract": {
            "contract_sha256": contract_hash_locked,
            "target_definition": contract["target_definition"],
            "horizons": contract["horizons"],
            "risk_normalization": contract["risk_normalization"],
            "data_exposure": contract["data_exposure"],
        },
        "counts": {"ok_buy": ok_buy, "ok_sell": ok_sell, "wait": n_wait, "total_rows": len(all_rows)},
        "baselines": baselines,
        "independent": independent,
        "data_gate": data_gate,
        "mid_price_used": mid_used,
        "artifacts": {
            "outcomes_jsonl": str(outcomes_path.as_posix()),
            "research_contract": str((REPORTS_DIR / "research_contract.json").as_posix()),
            "cost_scenarios": str((REPORTS_DIR / "cost_scenario_registry.json").as_posix()),
            "baselines": str((REPORTS_DIR / "baseline_comparison.json").as_posix()),
        },
        "no_strategy_discovery": True,
        "no_model_promotion": True,
        "runtime": runtime,
        "safety": {
            "broker_orders": BROKER_ORDERS,
            "discord": DISCORD_MESSAGES_SENT,
            "telegram": TELEGRAM_MESSAGES_SENT,
            "packages_installed": PACKAGES_INSTALLED,
            "holdout_accesses": HOLDOUT_ACCESSES,
            "git_commit": GIT_COMMIT,
            "git_push": GIT_PUSH,
            "mt5_connections": MT5_CONNECTIONS,
        },
    }
    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _render_final_report(payload))
    write_text(DOCS_DIR / "PHASE_46_COSTED_EV_FOUNDATION.md", _render_docs(contract, verdict, reason))

    print(
        __import__("json").dumps(
            {
                "phase": 46,
                "recipe_id": RECIPE_ID,
                "final_verdict": verdict,
                "verdict_reason": reason,
                "ok_buy": ok_buy,
                "ok_sell": ok_sell,
                "wait": n_wait,
                "independent_ok": independent.get("ok"),
                "contract_sha256": contract_hash_locked,
                "champion": CHAMPION_STATUS,
                "production": PRODUCTION_FINAL_ACTION,
                "runtime": runtime,
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    main()
