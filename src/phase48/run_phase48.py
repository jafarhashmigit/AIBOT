"""Phase 48 runner — root-cause audit of Phase47 EV failure. No strategy discovery."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase48.constants import (
    BROKER_ORDERS,
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
)
from phase48.diagnostics import (
    ev_diagnostics,
    execution_cost_audit,
    feature_audit,
    overlapping_dependence_note,
    probability_baseline_audit,
    reconstruct_oof,
    wait_gate_analysis,
)
from phase48.progress import write_json, write_text
from phase48.root_causes import classify
from phase48.verify_outcomes import full_verify_11211, load_outcomes


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _docs(verdict_summary: str, top3: list) -> str:
    lines = [
        "# Phase 48 — Decision Intelligence Failure Root-Cause Investigation",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## Purpose",
        "Forensic audit of Phase47 `EV_ESTIMATION_UNRELIABLE` and 100% WAIT.",
        "No new strategy. No model promotion.",
        "",
        "## Primary conclusion",
        verdict_summary,
        "",
        "## Top root causes",
    ]
    for i, r in enumerate(top3, 1):
        lines.append(f"{i}. `{r.get('class')}` — {r.get('summary')}")
    lines += [
        "",
        "See `reports/phase48/FINAL_REPORT.md`.",
        "",
        "No Phase49 started automatically.",
        "",
    ]
    return "\n".join(lines)


def _report(payload: dict[str, Any]) -> str:
    rc = payload["root_causes"]
    lines = [
        "# Phase 48 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Champion:** `{payload['champion']}` | **Production:** `{payload['production']}`",
        "",
        "## Executive conclusion",
        f"- {rc['primary_conclusion']}",
        "",
        "## 1. Complete Phase46 11,211-row verification",
        f"- OK: `{payload['verify_11211']['ok']}`",
        f"- Directional checked: `{payload['verify_11211']['directional']['checked']}` mismatches=`{payload['verify_11211']['directional']['mismatches']}`",
        f"- WAIT checked: `{payload['verify_11211']['wait']['checked']}` failures=`{payload['verify_11211']['wait']['failures']}`",
        f"- Total accounted: `{payload['verify_11211']['total_records_accounted']}`",
        f"- Why Phase47 said 7474: `{payload['verify_11211']['phase47_7474_vs_11211']['explanation']}`",
        "",
        "## 2. Phase47 OOF reconstruction",
        f"- Folds: `{payload['oof']['n_folds']}` leakage_ok=`{payload['oof']['leakage_ok']}`",
        f"- BUY OOF n=`{payload['probability']['buy_pooled'].get('n')}`",
        f"- SELL OOF n=`{payload['probability']['sell_pooled'].get('n')}`",
        "",
        "## 3. Probability baseline comparisons",
        f"- BUY: `{payload['probability']['buy_pooled']}`",
        f"- SELL: `{payload['probability']['sell_pooled']}`",
        f"- Note: `{payload['probability']['interpretation']}`",
        "",
        "## 4. EV prediction diagnostics",
        f"- BUY: `{payload['ev']['buy']}`",
        f"- SELL: `{payload['ev']['sell']}`",
        "",
        "## 5. Feature-target alignment",
        f"- BUY max |corr|: `{payload['features']['by_action']['BUY']['max_abs_corr_with_target']}`",
        f"- SELL max |corr|: `{payload['features']['by_action']['SELL']['max_abs_corr_with_target']}`",
        f"- Finding: `{payload['features']['finding']}`",
        f"- Horizon note: `{payload['features']['horizon_note']}`",
        "",
        "## 6. Seven-fold chronological audit",
        f"- Fold reports summary n=`{len(payload['oof']['fold_reports'])}`",
        f"- Dependence: `{payload['dependence']}`",
        "",
        "## 7. WAIT gate analysis",
        f"- `{payload['wait_gates']}`",
        "",
        "## 8. Execution-cost audit",
        f"- `{payload['costs']}`",
        "",
        "## 9. Confirmed bugs and root causes",
    ]
    for f in rc["findings"]:
        lines.append(
            f"- `{f['class']}` | {f['id']} | severity={f['severity']} | confirmed={f['confirmed']}: {f['summary']}"
        )
    lines += ["", "### Top 3 by evidence/impact"]
    for i, f in enumerate(rc["top3_root_causes"], 1):
        lines.append(f"{i}. **{f['class']}** — {f['summary']}")
    lines += ["", "## 10. Recommended architecture changes"]
    for r in rc["recommendations"]:
        lines.append(f"- `{r['id']}`: {r['action']}")
    lines += [
        "",
        "## 11. Phase49 objective (justified, not auto-started)",
        "- Feature ontology reset & non-overlapping costed-EV information tests "
        "(beat base-rate/const-EV under date-blocked evaluation). No strategy promotion.",
        "",
        "## Safety",
        f"- Orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime s: `{payload['runtime'].get('DURATION_SECONDS')}`",
        "",
        "No Phase49 started. Champion remains NO_MODEL. Production remains WAIT.",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    rows = load_outcomes()
    verify = full_verify_11211(rows)
    write_json(REPORTS_DIR / "phase46_full_11211_verification.json", verify)

    oof = reconstruct_oof()
    buy_oof, sell_oof = oof["buy_oof"], oof["sell_oof"]
    # strip heavy preds from saved oof meta
    oof_meta = {k: v for k, v in oof.items() if k not in ("buy_oof", "sell_oof")}
    write_json(REPORTS_DIR / "oof_fold_audit.json", oof_meta)

    prob = probability_baseline_audit(buy_oof, sell_oof)
    write_json(REPORTS_DIR / "probability_baselines.json", prob)

    ev = ev_diagnostics(buy_oof, sell_oof)
    write_json(REPORTS_DIR / "ev_diagnostics.json", ev)

    feats = feature_audit()
    write_json(REPORTS_DIR / "feature_target_audit.json", feats)

    wait = wait_gate_analysis(buy_oof, sell_oof)
    write_json(REPORTS_DIR / "wait_gate_analysis.json", wait)

    costs = execution_cost_audit(rows)
    write_json(REPORTS_DIR / "execution_cost_audit.json", costs)

    dependence = overlapping_dependence_note(buy_oof)
    write_json(REPORTS_DIR / "overlapping_dependence.json", dependence)

    bundle = {
        "verify_11211": verify,
        "probability": prob,
        "ev": ev,
        "features": feats,
        "wait_gates": wait,
        "costs": costs,
        "folds": oof_meta,
    }
    root = classify(bundle)
    write_json(REPORTS_DIR / "root_cause_classification.json", root)

    payload: dict[str, Any] = {
        "phase": 48,
        "recipe_id": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "verify_11211": verify,
        "oof": oof_meta,
        "probability": prob,
        "ev": ev,
        "features": {
            "finding": feats["finding"],
            "horizon_note": feats["horizon_note"],
            "by_action": {
                a: {
                    "n": feats["by_action"][a]["n"],
                    "max_abs_corr_with_target": feats["by_action"][a]["max_abs_corr_with_target"],
                    "redundant_pairs": feats["by_action"][a]["redundant_pairs"],
                    "feature_rows": feats["by_action"][a]["feature_rows"],
                }
                for a in ("BUY", "SELL")
            },
        },
        "wait_gates": wait,
        "costs": costs,
        "dependence": dependence,
        "root_causes": root,
        "no_strategy_discovery": True,
        "phase49_auto_started": False,
        "runtime": {
            "START_UTC": start,
            "END_UTC": _utc(),
            "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
        },
    }
    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(
        DOCS_DIR / "PHASE_48_DECISION_INTELLIGENCE_ROOT_CAUSE.md",
        _docs(root["primary_conclusion"], root["top3_root_causes"]),
    )

    summary = {
        "phase": 48,
        "recipe_id": RECIPE_ID,
        "verify_11211_ok": verify["ok"],
        "total_verified": verify["total_records_accounted"],
        "wait_verified": verify["wait"]["checked"],
        "directional_verified": verify["directional"]["checked"],
        "buy_brier_skill": prob["buy_pooled"].get("brier_skill_vs_const"),
        "sell_brier_skill": prob["sell_pooled"].get("brier_skill_vs_const"),
        "buy_ev_corr": (ev.get("buy") or {}).get("corr_ev_vs_actual"),
        "sell_ev_corr": (ev.get("sell") or {}).get("corr_ev_vs_actual"),
        "buy_max_feature_abs_corr": feats["by_action"]["BUY"]["max_abs_corr_with_target"],
        "joint_pass_buy": wait["per_side"]["BUY"]["would_pass_all_gates_jointly"],
        "joint_pass_sell": wait["per_side"]["SELL"]["would_pass_all_gates_jointly"],
        "top3": [{"class": x["class"], "id": x["id"]} for x in root["top3_root_causes"]],
        "primary_conclusion": root["primary_conclusion"],
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "runtime": payload["runtime"],
    }
    print(__import__("json").dumps(summary, indent=2))
    return payload


if __name__ == "__main__":
    main()
