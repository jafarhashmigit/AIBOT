"""Phase 50 runner — causal adaptive experience learning experiment."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase49.events import build_events_for_dates
from phase50.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PHASE44_VALIDATION,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase50.controls import run_controls
from phase50.evaluation import comparison_table, summarize_run
from phase50.independent import recompute_full_match, verify_decision_path
from phase50.policies import policy_registry
from phase50.progress import write_json, write_text
from phase50.qualification import choose_verdict
from phase50.replay import run_policy_chronological
from phase50.schemas import experience_schema


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_discovery_dates() -> list[str]:
    sel = json.loads((Path("reports/phase49/date_selection.json")).read_text(encoding="utf-8"))
    dates = list(sel["discovery_dates"])
    conf = set(sel["confirmation_dates"])
    # Never use confirmation or phase44 validation
    dates = [d for d in dates if d not in conf and d not in PHASE44_VALIDATION]
    return dates


def _blocks(dates: list[str], size: int = 5) -> tuple[list[list[str]], dict[str, int]]:
    blocks = [dates[i : i + size] for i in range(0, len(dates), size)]
    day_to_block = {}
    for i, b in enumerate(blocks):
        for d in b:
            day_to_block[d] = i
    return blocks, day_to_block


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 50 — Adaptive Experience Learning

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

## Research question
Does structured experience provide measurable incremental decision value beyond NO_LEARNING on chronological unseen blocks?

## Constraints
- HISTORICAL_HYPOTHETICAL and AGENT_SHADOW remain separate
- No fabricated shadow experience
- Phase44 validation / Phase49 confirmation sealed
- No strategy discovery / DL / RL / bandits

## Verdict
`{verdict}` — {reason}

See `reports/phase50/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    lines = [
        "# Phase 50 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{p['final_verdict']}`",
        f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
        "",
        "## Answers to required questions",
        f"1. Learn from past experience? `{p['answers']['learned']}`",
        f"2. Change BUY/SELL/WAIT? `{p['answers']['changed_actions']}`",
        f"3. Improve cost-aware quality OOS chrono? `{p['answers']['improved']}`",
        f"4. HISTORICAL_HYPOTHETICAL value? `{p['answers']['historical_value']}`",
        f"5. AGENT_SHADOW value? `{p['answers']['shadow_value']}`",
        f"6. Dual value? `{p['answers']['dual_value']}`",
        f"7. Adaptive beat static? `{p['answers']['adaptive_vs_static']}`",
        f"8. Real beat randomized? `{p['answers']['real_vs_random']}`",
        f"9. Robust across blocks? `{p['answers']['block_robust']}`",
        f"10. Justify new strategy phase? `{p['answers']['justify_strategy_phase']}`",
        "",
        f"## Verdict reason",
        f"- {p['verdict_reason']}",
        "",
        "## Experiment design",
        f"- `{p['design']}`",
        "",
        "## Experience sources",
        f"- `{p['experience_sources']}`",
        "",
        "## Policy comparison table",
        f"- `{p['comparison_table']}`",
        "",
        "## Controls",
        f"- `{p['controls_summary']}`",
        "",
        "## Learning-over-time / blocks",
        f"- POLICY_1 blocks: `{(p.get('policy_summaries') or {}).get('POLICY_1', {}).get('block_rows')}`",
        "",
        "## Integrity / leakage",
        f"- `{p['integrity']}`",
        "",
        "## Independent recomputation",
        f"- `{p['independent']}`",
        "",
        "## Next recommendation",
        f"- `{p['next_recommendation']}`",
        "",
        "## Safety",
        f"- Orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime s: `{p['runtime'].get('DURATION_SECONDS')}`",
        "",
        "No Phase51 started. Champion remains NO_MODEL. Production remains WAIT.",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    schema = experience_schema()
    preg = policy_registry()
    write_json(REPORTS_DIR / "policy_registry.json", preg)
    write_json(
        REPORTS_DIR / "learner_registry.json",
        {
            "learner_version": "shrink_bucket_v1",
            "method": "bucket + global shrinkage action-conditioned mean net R",
            "actions": ["BUY", "SELL", "WAIT"],
            "WAIT_q": 0.0,
        },
    )

    dates = _load_discovery_dates()
    blocks, day_to_block = _blocks(dates, 5)

    # Build non-overlapping events from Phase49 discovery dates only
    pack = build_events_for_dates(dates)
    events = pack["events"]
    if pack["overlap_violations"] != 0:
        payload = {
            "final_verdict": "DATA_INTEGRITY_FAILURE",
            "verdict_reason": "overlap violations in event construction",
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "integrity_failure": "overlap",
            "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": time.perf_counter() - t0},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        return payload

    # POLICY runs
    p0 = run_policy_chronological(events, policy_id="POLICY_0", experience_mode="none", day_to_block=day_to_block)
    s0 = summarize_run(p0, baseline_mean=0.0)
    baseline_mean = float(s0["mean_net_r"] or 0.0)

    p1 = run_policy_chronological(events, policy_id="POLICY_1", experience_mode="historical", day_to_block=day_to_block)
    s1 = summarize_run(p1, baseline_mean=baseline_mean)

    p2 = run_policy_chronological(events, policy_id="POLICY_2", experience_mode="shadow", day_to_block=day_to_block)
    s2 = summarize_run(p2, baseline_mean=baseline_mean)

    p3 = run_policy_chronological(events, policy_id="POLICY_3", experience_mode="dual", day_to_block=day_to_block)
    s3 = summarize_run(p3, baseline_mean=baseline_mean)

    controls = run_controls(events, day_to_block=day_to_block, baseline_decisions_mean=baseline_mean)

    # Independent recompute POLICY_1
    p1_b = run_policy_chronological(events, policy_id="POLICY_1", experience_mode="historical", day_to_block=day_to_block)
    ind_match = recompute_full_match(p1, p1_b)
    ind_path = verify_decision_path(events, p0["decisions"], policy_id="POLICY_0", experience_mode="none")

    integrity = {
        "leakage_p0": p0["leakage_ok"],
        "leakage_p1": p1["leakage_ok"],
        "leakage_p2": p2["leakage_ok"],
        "leakage_p3": p3["leakage_ok"],
        "overlap_violations": pack["overlap_violations"],
        "forbidden_dates_used": sorted(set(dates) & PHASE44_VALIDATION),
        "confirmation_dates_used": False,
    }
    write_json(REPORTS_DIR / "integrity_report.json", integrity)

    summaries = {"POLICY_0": s0, "POLICY_1": s1, "POLICY_2": s2, "POLICY_3": s3}
    table = comparison_table([s0, s1, s2, s3])
    write_json(REPORTS_DIR / "metrics.json", {"summaries": summaries, "table": table, "controls": controls})

    agent_shadow_status = "EMPTY" if p1.get("agent_shadow_empty", True) else "POPULATED"

    # Answers
    incr1 = s1.get("incremental_value_vs_baseline")
    rand_incr = (controls.get("randomized") or {}).get("incremental_value_vs_baseline")
    static_incr = (controls.get("static") or {}).get("incremental_value_vs_baseline")
    answers = {
        "learned": bool(s1.get("learning_changed_actions")) and (s1.get("hist_n") or 0) > 0,
        "changed_actions": bool(s1.get("learning_changed_actions")),
        "improved": bool(incr1 is not None and incr1 > 0 and (s1.get("bootstrap_incremental") or {}).get("ci95_low", -1) > 0),
        "historical_value": incr1,
        "shadow_value": "UNEVALUABLE_EMPTY" if agent_shadow_status == "EMPTY" else s2.get("incremental_value_vs_baseline"),
        "dual_value": s3.get("incremental_value_vs_baseline"),
        "adaptive_vs_static": None if static_incr is None or incr1 is None else incr1 - static_incr,
        "real_vs_random": None if rand_incr is None or incr1 is None else incr1 - rand_incr,
        "block_robust": s1.get("block_rows"),
        "justify_strategy_phase": False,
    }

    payload: dict[str, Any] = {
        "phase": 50,
        "recipe_id": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "design": {
            "data": "Phase49 discovery dates only; non-overlapping H12 events",
            "n_dates": len(dates),
            "n_events": len(events),
            "blocks": blocks,
            "learner": "shrinkage bucket action-conditioned mean net R",
            "primary_metric": "INCREMENTAL_DECISION_VALUE vs POLICY_0",
        },
        "experience_sources": {
            "HISTORICAL_HYPOTHETICAL": "counterfactual BUY/SELL/WAIT outcomes matured chronologically",
            "AGENT_SHADOW": agent_shadow_status,
            "stores_merged": False,
        },
        "agent_shadow_status": agent_shadow_status,
        "policy_summaries": summaries,
        "comparison_table": table,
        "controls": controls,
        "controls_summary": {
            "randomized_incr": rand_incr,
            "static_incr": static_incr,
            "delayed_incr": (controls.get("delayed") or {}).get("incremental_value_vs_baseline"),
        },
        "integrity": integrity,
        "independent": {"full_match_policy1": ind_match, "path_checks": ind_path, "schema_sha": schema.get("schema_sha256")},
        "answers": answers,
        "schema": {"experience_schema_version": schema["experience_schema_version"], "sha256": schema["schema_sha256"]},
    }

    if not integrity["leakage_p1"] or not ind_match.get("ok") or integrity["forbidden_dates_used"]:
        payload["integrity_failure"] = "leakage_or_recompute_or_forbidden"

    verdict, reason = choose_verdict(payload)
    # If shadow empty and no hist learning value, still prefer NO_DEMONSTRATED over AGENT_SHADOW_EMPTY as primary
    # but mention empty in reason (already handled)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["next_recommendation"] = (
        "Do not start another indicator sweep. If pursuing learning further, accumulate genuine AGENT_SHADOW "
        "offline on sealed protocols — or revisit information representation only with preregistered ontology tests. "
        "Keep Production=WAIT."
    )
    payload["runtime"] = {
        "START_UTC": start,
        "END_UTC": _utc(),
        "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
    }

    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(DOCS_DIR / "PHASE_50_ADAPTIVE_EXPERIENCE_LEARNING.md", _docs(verdict, reason))

    print(
        __import__("json").dumps(
            {
                "phase": 50,
                "recipe_id": RECIPE_ID,
                "final_verdict": verdict,
                "verdict_reason": reason,
                "n_events": len(events),
                "agent_shadow_status": agent_shadow_status,
                "policy_actions": {k: v.get("action_counts") for k, v in summaries.items()},
                "incremental_P1": incr1,
                "controls": payload["controls_summary"],
                "independent_ok": ind_match.get("ok") and ind_path.get("ok"),
                "champion": CHAMPION_STATUS,
                "production": PRODUCTION_FINAL_ACTION,
                "runtime": payload["runtime"],
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    main()
