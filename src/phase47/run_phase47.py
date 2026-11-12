"""Phase 47 runner — calibrated decision intelligence. No profitability claim."""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from phase46.data import load_m5
from phase47.calibration import date_block_ci, evaluate_predictions
from phase47.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DATA_OUT_DIR,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    ENGINEERING_DATES,
    FEATURE_NAMES,
    FORBIDDEN_VALIDATION_DATES,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    POLICY_THRESHOLDS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    file_sha256,
)
from phase47.experience import write_experience_stores
from phase47.features import attach_features_to_outcomes
from phase47.independent import verify_ev_rows, verify_policy_decisions
from phase47.models import fit_action_models, predict_components
from phase47.policy import apply_policy_to_paired, decision_summary
from phase47.preflight import load_phase46_outcomes, run_preflight
from phase47.progress import write_json, write_text
from phase47.qualification import choose_verdict
from phase47.splits import assert_no_leakage, partition_rows, walk_forward_folds


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _docs(verdict: str, reason: str, contract_sha: str) -> str:
    return f"""# Phase 47 — Calibrated Decision Intelligence & Intelligent WAIT

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

## Purpose
Build the decision-intelligence layer on Phase46 costed outcomes:
action-conditioned probabilities, conditional payoffs, expected net R,
uncertainty, market familiarity, and intelligent WAIT.

Exploratory only on Phase44 discovery / Phase46 engineering dates.
Not a profitability claim. No online adaptive learning claimed.

## Phase46 contract
Confirmed SHA-256: `{contract_sha}`

## Frozen policy thresholds
See `reports/phase47/policy_thresholds.json` (locked before evaluation).

## Experience stores
- `HISTORICAL_HYPOTHETICAL` — populated from Phase46 outcomes
- `AGENT_SHADOW` — empty (not fabricated)

## Final verdict
`{verdict}` — {reason}

See `reports/phase47/FINAL_REPORT.md`.
"""


def _final_report(p: dict[str, Any]) -> str:
    lines = [
        "# Phase 47 — Final Report",
        "",
        f"**Recipe:** `{p['recipe_id']}`",
        f"**Verdict:** `{p['final_verdict']}`",
        f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
        "",
        "## 1. Phase46 integrity verification",
        f"- OK: `{p['preflight']['ok']}`",
        f"- Contract: `{p['preflight']['contract']}`",
        f"- Structural: n=`{p['preflight']['structural'].get('n_rows')}`, counts=`{p['preflight']['structural'].get('action_counts')}`",
        f"- Independent full recompute: checked=`{p['preflight']['independent'].get('checked_directional')}`, "
        f"mismatches=`{p['preflight']['independent'].get('n_mismatches')}`, ok=`{p['preflight']['independent'].get('ok')}`",
        "",
        "## 2. Dataset / features",
        f"- Feature names: `{FEATURE_NAMES}`",
        f"- BUY featured rows: `{p['dataset']['n_buy']}`",
        f"- SELL featured rows: `{p['dataset']['n_sell']}`",
        f"- Label: `{p['dataset']['label']}`",
        "",
        "## 3. Chronological splits",
        f"- Folds: `{p['splits']['n_folds']}`",
        f"- Design: `{p['splits']['design']}`",
        f"- Leakage checks OK: `{p['splits']['leakage_ok']}`",
        "",
        "## 4. Models",
        f"- `{p['models']}`",
        "",
        "## 5. BUY calibration (OOF)",
        f"- `{p['buy_calibration']}`",
        "",
        "## 6. SELL calibration (OOF)",
        f"- `{p['sell_calibration']}`",
        "",
        "## 7–9. Conditional payoff / direct regression / EV accuracy",
        f"- BUY conditional: `{((p.get('buy_calibration') or {}).get('conditional_payoff'))}`",
        f"- SELL conditional: `{((p.get('sell_calibration') or {}).get('conditional_payoff'))}`",
        f"- BUY EV decomp error: `{((p.get('buy_calibration') or {}).get('ev_decomp_error'))}`",
        f"- BUY direct error: `{((p.get('buy_calibration') or {}).get('ev_direct_error'))}`",
        f"- SELL EV decomp error: `{((p.get('sell_calibration') or {}).get('ev_decomp_error'))}`",
        f"- SELL direct error: `{((p.get('sell_calibration') or {}).get('ev_direct_error'))}`",
        "",
        "## 10. Intelligent WAIT distribution",
        f"- `{p['policy_summary']}`",
        "",
        "## 11. Cost-stress sensitivity",
        f"- Stress scenario / haircut: `{POLICY_THRESHOLDS['stress_scenario_id']}` + predicted EV haircut proxy 0.05 (labeled hypothetical)",
        f"- Rejection reasons: `{(p.get('policy_summary') or {}).get('rejection_reason_counts')}`",
        "",
        "## 12. OOD / uncertainty rejections",
        f"- Included in rejection_reason_counts above (low_familiarity_ood / high_uncertainty).",
        "",
        "## 13. Baselines",
        f"- `{p['baselines']}`",
        "",
        "## 14. Date-grouped CIs",
        f"- BUY actual net_R CI: `{p.get('buy_ci')}`",
        f"- SELL actual net_R CI: `{p.get('sell_ci')}`",
        f"- Policy realized CI: `{p.get('policy_ci')}`",
        "",
        "## 15. Limitations",
        "- 15 exposed engineering dates only; not independent validation.",
        "- Demo bid/ask ≠ live broker truth; commission/slippage UNKNOWN.",
        "- No online learning; AGENT_SHADOW empty.",
        "- Calibration/EV quality may be insufficient for production decisions.",
        "",
        "## 16. Independent verification",
        f"- EV arithmetic: `{p['independent_ev']}`",
        f"- Policy decisions: `{p['independent_policy']}`",
        "",
        "## 17. Artifacts / hashes",
        f"- `{p.get('artifacts')}`",
        "",
        "## Safety",
        f"- Orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime s: `{p['runtime'].get('DURATION_SECONDS')}`",
        "",
        "## Final verdict",
        f"- `{p['final_verdict']}`",
        f"- {p['verdict_reason']}",
        "",
        "No Phase48 started. Champion remains NO_MODEL. Production remains WAIT.",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc_now()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Freeze thresholds artifact before modeling
    write_json(REPORTS_DIR / "policy_thresholds.json", POLICY_THRESHOLDS)

    preflight = run_preflight()
    write_json(REPORTS_DIR / "phase46_integrity.json", preflight)
    if not preflight["ok"]:
        verdict, reason = "DATA_INTEGRITY_FAILURE", "Phase46 full integrity verification failed."
        payload = {
            "phase": 47,
            "recipe_id": RECIPE_ID,
            "final_verdict": verdict,
            "verdict_reason": reason,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "preflight": preflight,
            "engine_implemented": False,
            "runtime": {"START_UTC": start, "END_UTC": _utc_now(), "DURATION_SECONDS": time.perf_counter() - t0},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", _final_report({**payload, "dataset": {}, "splits": {}, "models": {}, "buy_calibration": {}, "sell_calibration": {}, "policy_summary": {}, "baselines": {}, "independent_ev": {}, "independent_policy": {}, "artifacts": {}}))
        write_text(
            DOCS_DIR / "PHASE_47_CALIBRATED_DECISION_INTELLIGENCE.md",
            _docs(verdict, reason, str(preflight.get("contract", {}).get("stored") or PHASE46_CONTRACT_SHA)),
        )
        print(__import__("json").dumps({"final_verdict": verdict, "verdict_reason": reason}, indent=2))
        return payload

    from phase47.constants import PHASE46_CONTRACT_SHA256_EXPECTED

    rows = load_phase46_outcomes()
    # Load M5 for feature build (engineering dates only)
    accessed = []
    m5_by_day = {}
    for d in ENGINEERING_DATES:
        assert d not in FORBIDDEN_VALIDATION_DATES
        accessed.append(d)
        m5_by_day[d] = load_m5(d)

    featured = attach_features_to_outcomes(rows, m5_by_day)
    buy_rows = [r for r in featured if r["action"] == "BUY"]
    sell_rows = [r for r in featured if r["action"] == "SELL"]

    folds = walk_forward_folds()
    leakage_flags = []
    buy_oof: list[dict[str, Any]] = []
    sell_oof: list[dict[str, Any]] = []
    model_metas = []

    for fold in folds:
        tr_dates = set(fold["train_dates"])
        ev_dates = set(fold["eval_dates"])
        b_tr, b_ev = partition_rows(buy_rows, tr_dates, ev_dates)
        s_tr, s_ev = partition_rows(sell_rows, tr_dates, ev_dates)
        leakage_flags.append(assert_no_leakage(b_tr + s_tr, b_ev + s_ev))

        b_model = fit_action_models("BUY", b_tr)
        s_model = fit_action_models("SELL", s_tr)
        model_metas.append({"fold": fold["fold_id"], "buy": b_model.to_meta(), "sell": s_model.to_meta()})
        buy_oof.extend(predict_components(b_model, b_ev))
        sell_oof.extend(predict_components(s_model, s_ev))

    buy_cal = evaluate_predictions(buy_oof, label="BUY_OOF")
    sell_cal = evaluate_predictions(sell_oof, label="SELL_OOF")
    buy_ci = date_block_ci(buy_oof, "actual_net_r")
    sell_ci = date_block_ci(sell_oof, "actual_net_r")

    decisions = apply_policy_to_paired(buy_oof, sell_oof)
    pol_sum = decision_summary(decisions)
    policy_ci = date_block_ci(
        [{"day": d["day"], "actual_net_r": d["realized_net_r"]} for d in decisions if d.get("realized_net_r") is not None],
        "actual_net_r",
    )

    # Baselines on same OOF decision bars
    always_wait_r = [0.0] * len(decisions)
    # Unconditional BUY/SELL means on OOF actuals
    baselines = {
        "ALWAYS_WAIT_mean_net_r": 0.0,
        "UNCONDITIONAL_BUY_oof_mean_net_r": buy_cal.get("mean_actual_net_r"),
        "UNCONDITIONAL_SELL_oof_mean_net_r": sell_cal.get("mean_actual_net_r"),
        "POLICY_mean_realized_net_r": pol_sum.get("mean_realized_net_r"),
        "note": "Exploratory comparison on exposed dates only; not an edge claim.",
    }

    ind_ev = verify_ev_rows(buy_oof + sell_oof)
    ind_pol = verify_policy_decisions(decisions, buy_oof, sell_oof)

    exp = write_experience_stores(historical_rows=buy_rows + sell_rows, policy_decisions=decisions)

    write_json(REPORTS_DIR / "walk_forward_folds.json", folds)
    write_json(REPORTS_DIR / "model_meta.json", model_metas)
    write_json(REPORTS_DIR / "buy_calibration.json", buy_cal)
    write_json(REPORTS_DIR / "sell_calibration.json", sell_cal)
    write_json(REPORTS_DIR / "policy_summary.json", pol_sum)
    write_json(REPORTS_DIR / "baselines.json", baselines)
    write_json(REPORTS_DIR / "independent_verification.json", {"ev": ind_ev, "policy": ind_pol})

    artifacts = {
        "phase46_outcomes_sha256": file_sha256(__import__("pathlib").Path("src/data/phase46/action_conditioned_outcomes.jsonl")),
        "policy_thresholds_sha256": file_sha256(REPORTS_DIR / "policy_thresholds.json"),
        "experience": exp,
        "accessed_dates": accessed,
        "forbidden_hits": sorted(set(accessed) & FORBIDDEN_VALIDATION_DATES),
    }

    payload: dict[str, Any] = {
        "phase": 47,
        "recipe_id": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "preflight": preflight,
        "engine_implemented": True,
        "dataset": {
            "n_buy": len(buy_rows),
            "n_sell": len(sell_rows),
            "feature_names": FEATURE_NAMES,
            "label": "EXPLORATORY_PHASE44_DISCOVERY_EXPOSED",
        },
        "splits": {
            "n_folds": len(folds),
            "design": "chronological_expanding_walk_forward",
            "leakage_ok": all(x["ok"] for x in leakage_flags),
            "min_train_dates": 8,
        },
        "models": {
            "probability": "LogisticRegression L2",
            "conditional_payoff": "Ridge pos/neg",
            "direct": "Ridge net_R",
            "challenger": "HistGradientBoostingClassifier (optional, fold-dependent)",
        },
        "buy_calibration": buy_cal,
        "sell_calibration": sell_cal,
        "buy_ci": buy_ci,
        "sell_ci": sell_ci,
        "policy_summary": pol_sum,
        "policy_ci": policy_ci,
        "baselines": baselines,
        "independent_ev": ind_ev,
        "independent_policy": ind_pol,
        "artifacts": artifacts,
        "decision_count_oof": dict(Counter(d["decision"] for d in decisions)),
        "no_online_learning_claimed": True,
        "agent_shadow_empty": True,
    }
    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["runtime"] = {
        "START_UTC": start,
        "END_UTC": _utc_now(),
        "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
    }

    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _final_report(payload))
    write_text(
        DOCS_DIR / "PHASE_47_CALIBRATED_DECISION_INTELLIGENCE.md",
        _docs(verdict, reason, PHASE46_CONTRACT_SHA256_EXPECTED),
    )

    print(
        __import__("json").dumps(
            {
                "phase": 47,
                "recipe_id": RECIPE_ID,
                "final_verdict": verdict,
                "verdict_reason": reason,
                "preflight_ok": preflight["ok"],
                "buy_oof_n": buy_cal.get("n"),
                "sell_oof_n": sell_cal.get("n"),
                "buy_ece": (buy_cal.get("calibration") or {}).get("ece"),
                "sell_ece": (sell_cal.get("calibration") or {}).get("ece"),
                "policy_counts": pol_sum.get("decision_counts"),
                "independent_ev_ok": ind_ev.get("ok"),
                "independent_policy_ok": ind_pol.get("ok"),
                "champion": CHAMPION_STATUS,
                "production": PRODUCTION_FINAL_ACTION,
                "runtime": payload["runtime"],
            },
            indent=2,
        )
    )
    return payload


# fix forward ref in early-exit docs
PHASE46_CONTRACT_SHA = "44e33d0ea569c916d2f3332d875799076dc75149abe6b02f09abb4e44893984d"

if __name__ == "__main__":
    main()
