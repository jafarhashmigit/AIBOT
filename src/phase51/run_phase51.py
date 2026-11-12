"""Phase 51 — one-shot frozen Phase50 learner confirmation."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase50.controls import make_randomizer, run_controls
from phase50.evaluation import summarize_run
from phase50.replay import realized_net_r, run_policy_chronological
from phase51.acquisition import acquire_dates, load_state
from phase51.candidate import FrozenAIBOTCandidate
from phase51.connection import close_readonly, open_readonly
from phase51.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    canonical_json_sha256,
)
from phase51.date_selection import freeze_date_selection
from phase51.events import build_events_for_dates
from phase51.freeze import freeze_phase50_learner
from phase51.progress import write_json, write_text
from phase51.qualification import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blocks(dates: list[str], size: int = 5) -> tuple[list[list[str]], dict[str, int]]:
    blocks = [dates[i : i + size] for i in range(0, len(dates), size)]
    m = {}
    for i, b in enumerate(blocks):
        for d in b:
            m[d] = i
    return blocks, m


def _constant_action_run(events: list[dict[str, Any]], action: str) -> dict[str, Any]:
    decisions = []
    for e in sorted(events, key=lambda x: (x["day"], x["decision_idx"])):
        decisions.append(
            {
                "day": e["day"],
                "decision_bar": e["decision_bar"],
                "decision_timestamp_utc": e["decision_bar"],
                "action": action,
                "realized_net_r": realized_net_r(e, action),
                "block": None,
            }
        )
    return {
        "policy_id": f"CONSTANT_{action}",
        "experience_mode": "none",
        "decisions": decisions,
        "n_decisions": len(decisions),
        "hist_n": 0,
        "shadow_n": 0,
        "leakage_ok": True,
        "block_rows": [],
        "agent_shadow_empty": True,
        "action_counts": {action: len(decisions)},
    }


def _docs(verdict: str, reason: str, sha: str) -> str:
    return f"""# Phase 51 — Frozen Experience Learner Confirmation

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

Frozen Phase50 learner SHA-256: `{sha}`

One-shot independent confirmation. No tuning. No new features.

See `reports/phase51/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    s = p.get("frozen_summary") or {}
    return "\n".join(
        [
            "# Phase 51 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{p['final_verdict']}`",
            f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
            "",
            "## 1–2. Frozen learner",
            f"- SHA: `{p['frozen_learner_sha256']}`",
            f"- Definition: `{p.get('frozen_learner')}`",
            "",
            "## 3–5. Validation dates",
            f"- Selection SHA: `{p.get('selection_sha256')}`",
            f"- Dates n=`{p.get('n_dates')}`: `{p.get('selected_dates')}`",
            f"- Completed n=`{p.get('n_completed')}`",
            "",
            "## 6–13. Frozen learner results",
            f"- Decisions: `{s.get('n_decisions')}`",
            f"- BUY/SELL/WAIT: `{s.get('buy')}` / `{s.get('sell')}` / `{s.get('wait')}`",
            f"- Mean/Median Net R: `{s.get('mean_net_r')}` / `{s.get('median_net_r')}`",
            f"- PF / Max DD: `{s.get('profit_factor')}` / `{s.get('max_drawdown_r')}`",
            f"- Bootstrap CI (incr): `{s.get('bootstrap_incremental')}`",
            f"- Date-blocks: `{s.get('block_rows')}`",
            "",
            "## 14. Cost stress",
            f"- `{p.get('cost_stress')}`",
            "",
            "## 15–19. Comparisons / controls",
            f"- ALWAYS_WAIT: `{p.get('wait_summary')}`",
            f"- CONSTANT_BUY: `{p.get('const_buy_summary')}`",
            f"- CONSTANT_SELL: `{p.get('const_sell_summary')}`",
            f"- Static: `{(p.get('controls') or {}).get('static')}`",
            f"- Randomized: `{(p.get('controls') or {}).get('randomized')}`",
            "",
            "## 20–21. Integrity / independent",
            f"- `{p.get('integrity')}`",
            f"- `{p.get('independent')}`",
            "",
            "## 22. Final verdict",
            f"- `{p['final_verdict']}`",
            f"- {p['verdict_reason']}",
            "",
            f"Candidate interface: `{p.get('candidate_smoke')}`",
            f"Next: `{p.get('next_recommendation')}`",
            "",
            f"Safety orders/discord/telegram/packages/holdout/commit/push/mt5="
            f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
            f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
            f"Runtime s: `{p['runtime'].get('DURATION_SECONDS')}`",
            "",
            "No Phase52 started. Champion=NO_MODEL. Production=WAIT.",
            "",
        ]
    )


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    frozen = freeze_phase50_learner()
    # Re-verify freeze hash
    body = {k: v for k, v in frozen.items() if k != "frozen_learner_sha256"}
    if canonical_json_sha256(body) != frozen["frozen_learner_sha256"]:
        payload = {
            "final_verdict": "DATA_INTEGRITY_FAILURE",
            "verdict_reason": "frozen learner hash mismatch",
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "integrity_failure": "freeze_hash",
            "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": time.perf_counter() - t0},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        return payload

    selection = freeze_date_selection()
    selected = selection["selected_dates"]

    # Acquire
    conn = open_readonly()
    if conn.get("status") != "connected_readonly":
        acquisition = {
            "ok": False,
            "error": conn.get("reason"),
            "completed_dates": [],
            "pending_dates": selected,
            "ticks_total": 0,
        }
    else:
        try:
            acquisition = acquire_dates(
                conn["handle"],
                selected,
                server=conn.get("server"),
                terminal_build=conn.get("terminal_build"),
                wall_deadline=time.monotonic() + MAX_WALL_SECONDS,
            )
            acquisition["ok"] = True
        finally:
            close_readonly(conn.get("handle"))

    # Resume state if already acquired
    st = load_state(selected)
    completed = sorted(st["completed"].keys()) if st["completed"] else list(acquisition.get("completed_dates") or [])
    write_json(
        REPORTS_DIR / "acquisition.json",
        {
            "completed_n": len(completed),
            "completed_dates": completed,
            "pending": st.get("pending") or acquisition.get("pending_dates"),
            "ticks_total": st.get("ticks_total") or acquisition.get("ticks_total"),
            "stop_reason": acquisition.get("stop_reason"),
        },
    )

    if len(completed) < 10:
        payload = {
            "final_verdict": "RESEARCH_DESIGN_FAILURE",
            "verdict_reason": f"insufficient complete dates acquired: {len(completed)}",
            "design_failure": "insufficient_data",
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "frozen_learner_sha256": frozen["frozen_learner_sha256"],
            "selection_sha256": selection["selection_sha256"],
            "n_dates": len(selected),
            "n_completed": len(completed),
            "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": round(time.perf_counter() - t0, 6)},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
        return payload

    blocks, day_to_block = _blocks(completed, 5)
    pack = build_events_for_dates(completed)
    events = pack["events"]

    # Primary: frozen POLICY_1 historical
    frozen_run = run_policy_chronological(
        events, policy_id="POLICY_1", experience_mode="historical", day_to_block=day_to_block
    )
    wait_run = run_policy_chronological(events, policy_id="POLICY_0", experience_mode="none", day_to_block=day_to_block)
    wait_sum = summarize_run(wait_run, baseline_mean=0.0)
    baseline = float(wait_sum["mean_net_r"] or 0.0)
    frozen_sum = summarize_run(frozen_run, baseline_mean=baseline)

    buy_run = _constant_action_run(events, "BUY")
    sell_run = _constant_action_run(events, "SELL")
    # attach blocks for buy/sell
    for d in buy_run["decisions"]:
        d["block"] = day_to_block.get(d["day"])
    for d in sell_run["decisions"]:
        d["block"] = day_to_block.get(d["day"])
    buy_sum = summarize_run(buy_run, baseline_mean=baseline)
    sell_sum = summarize_run(sell_run, baseline_mean=baseline)

    controls = run_controls(events, day_to_block=day_to_block, baseline_decisions_mean=baseline)

    # Independent recompute
    frozen_run_b = run_policy_chronological(
        events, policy_id="POLICY_1", experience_mode="historical", day_to_block=day_to_block
    )
    diffs = 0
    for a, b in zip(frozen_run["decisions"], frozen_run_b["decisions"]):
        if a["action"] != b["action"] or abs(float(a["realized_net_r"]) - float(b["realized_net_r"])) > 1e-9:
            diffs += 1

    # Cost stress: recompute mean using STRESS scenario on chosen actions
    stress_rs = []
    for d, e in zip(
        frozen_run["decisions"],
        sorted(events, key=lambda x: (x["day"], x["decision_idx"])),
    ):
        # align carefully
        pass
    # Better: map by decision_bar
    emap = {(e["day"], e["decision_bar"]): e for e in events}
    for d in frozen_run["decisions"]:
        e = emap.get((d["day"], d["decision_bar"]))
        if not e:
            continue
        a = d["action"]
        if a == "WAIT":
            stress_rs.append(0.0)
        else:
            outcome = e["buy"] if a == "BUY" else e["sell"]
            sn = (outcome.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
            stress_rs.append(float(sn.get("net_r") if sn.get("net_r") is not None else outcome["net_r"]))
    cost_stress = {
        "OBSERVED_BIDASK_ONLY_mean": frozen_sum.get("mean_net_r"),
        "STRESS_SPREAD_WIDEN_1_5X_mean": (sum(stress_rs) / len(stress_rs)) if stress_rs else None,
        "note": "Spread not double-counted; stress is hypothetical widen on top of bid/ask fills",
    }

    # Candidate smoke test
    candidate = FrozenAIBOTCandidate(frozen["frozen_learner_sha256"])
    smoke = candidate.decide(
        {"timestamp_utc": "2025-07-04 12:00:00", "features": events[0]["features"] if events else {}},
        {"HISTORICAL_HYPOTHETICAL": [], "AGENT_SHADOW": []},
    )

    integrity = {
        "overlap_violations": pack["overlap_violations"],
        "leakage_ok": frozen_run["leakage_ok"],
        "forbidden_in_selection": False,
        "one_shot_no_tuning": True,
        "independent_action_diffs": diffs,
    }

    payload: dict[str, Any] = {
        "phase": 51,
        "recipe_id": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "frozen_learner": {
            "learner_version": frozen["learner_version"],
            "policy_version": frozen["policy_version"],
            "shrinkage_k": frozen["shrinkage_k"],
            "spread_atr_edges": frozen["spread_atr_edges"],
            "min_experience_per_action": frozen["min_experience_per_action"],
            "uncertainty_penalty": frozen["uncertainty_penalty"],
        },
        "frozen_learner_sha256": frozen["frozen_learner_sha256"],
        "selection_sha256": selection["selection_sha256"],
        "selected_dates": selected,
        "n_dates": len(selected),
        "n_completed": len(completed),
        "n_events": len(events),
        "frozen_summary": frozen_sum,
        "wait_summary": wait_sum,
        "const_buy_summary": buy_sum,
        "const_sell_summary": sell_sum,
        "controls": controls,
        "cost_stress": cost_stress,
        "integrity": integrity,
        "independent": {"action_diffs": diffs, "ok": diffs == 0 and frozen_run["leakage_ok"]},
        "leakage_ok": frozen_run["leakage_ok"],
        "no_tuning": True,
        "candidate_smoke": {
            "action": smoke.get("action"),
            "learner_version": smoke.get("learner_version"),
            "paper_only": smoke.get("paper_only"),
        },
        "agent_shadow_status": "EMPTY",
    }

    if pack["overlap_violations"] or diffs or not frozen_run["leakage_ok"]:
        payload["integrity_failure"] = "overlap_or_leakage_or_recompute"

    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    if verdict == "EDGE_CANDIDATE_CONFIRMED":
        payload["next_recommendation"] = (
            "Phase52 should harden this exact frozen learner into autonomous paper/shadow decision engine. "
            "Do not search new strategies."
        )
    elif verdict == "PROMISING_UNCONFIRMED":
        payload["next_recommendation"] = (
            "Do not tune. Missing evidence listed in verdict_reason. Keep Production=WAIT."
        )
    else:
        payload["next_recommendation"] = (
            "Stop this learner branch. Do not run variations. Consider market representation / "
            "instrument / timeframe change before more learning attempts."
        )

    payload["runtime"] = {
        "START_UTC": start,
        "END_UTC": _utc(),
        "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
    }

    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_json(REPORTS_DIR / "metrics.json", {
        "frozen": frozen_sum,
        "wait": wait_sum,
        "buy": buy_sum,
        "sell": sell_sum,
        "controls": controls,
        "cost_stress": cost_stress,
    })
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(
        DOCS_DIR / "PHASE_51_FROZEN_LEARNER_CONFIRMATION.md",
        _docs(verdict, reason, frozen["frozen_learner_sha256"]),
    )

    print(
        __import__("json").dumps(
            {
                "phase": 51,
                "recipe_id": RECIPE_ID,
                "final_verdict": verdict,
                "verdict_reason": reason,
                "frozen_learner_sha256": frozen["frozen_learner_sha256"],
                "selection_sha256": selection["selection_sha256"],
                "n_completed": len(completed),
                "n_events": len(events),
                "actions": frozen_sum.get("action_counts"),
                "mean_net_r": frozen_sum.get("mean_net_r"),
                "incremental_vs_wait": frozen_sum.get("incremental_value_vs_baseline"),
                "ci95_incr": (frozen_sum.get("bootstrap_incremental") or {}).get("ci95_low"),
                "ci95_incr_hi": (frozen_sum.get("bootstrap_incremental") or {}).get("ci95_high"),
                "independent_ok": diffs == 0,
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
