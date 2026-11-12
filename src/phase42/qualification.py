"""Final Phase42 verdict — adversarial, no production promotion."""

from __future__ import annotations

from typing import Any


def decide_verdict(
    eval_payload: dict[str, Any],
    ranked: list[dict[str, Any]],
    *,
    indep_ok: bool,
) -> dict[str, Any]:
    if not indep_ok:
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "independent verification failed — blocking claims",
            "best_candidate": "NONE",
            "merits_independent_validation": False,
        }

    results = eval_payload.get("results") or []
    if not results:
        return {
            "final_verdict": "NO_NEW_HYPOTHESES",
            "reason": "no hypotheses evaluated",
            "best_candidate": "NONE",
            "merits_independent_validation": False,
        }

    pred_pass = [r for r in results if r.get("predictive_pass")]
    decision_pass = [r for r in results if r.get("decision_value")]
    unsigned_pred = [r for r in pred_pass if (r.get("decision_validation") or {}).get("skipped")]

    if not pred_pass:
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "no frozen hypothesis survived discovery/validation gates under Bonferroni",
            "best_candidate": "NONE",
            "merits_independent_validation": False,
            "top_rejected": (eval_payload.get("rejected") or [])[:5],
        }

    if pred_pass and not decision_pass:
        best = ranked[0]["hypothesis_id"] if ranked else pred_pass[0]["hypothesis_id"]
        return {
            "final_verdict": "PREDICTIVE_BUT_NO_DECISION_VALUE",
            "reason": (
                f"{len(pred_pass)} hypothesis(es) show predictive association but "
                f"none improve BUY/SELL expectancy under bid/ask + stress "
                f"(unsigned_only={len(unsigned_pred)})"
            ),
            "best_candidate": best,
            "merits_independent_validation": False,
            "predictive_ids": [r["hypothesis_id"] for r in pred_pass],
        }

    # decision_pass non-empty — still on previously examined dates
    best = decision_pass[0]["hypothesis_id"]
    # Prefer highest rank among decision_pass
    for row in ranked:
        if row["hypothesis_id"] in {r["hypothesis_id"] for r in decision_pass}:
            best = row["hypothesis_id"]
            break

    # Cannot claim INDEPENDENT_VALIDATION_READY: dates previously examined; no new date set acquired
    return {
        "final_verdict": "PROMISING_BUT_UNCONFIRMED",
        "reason": (
            "Predictive + decision value on chronological split of previously examined Phase40 dates; "
            "NOT independent OOS. Requires new never-examined dates before INDEPENDENT_VALIDATION_READY."
        ),
        "best_candidate": best,
        "merits_independent_validation": True,
        "decision_ids": [r["hypothesis_id"] for r in decision_pass],
        "blocked_from_independent_ready": "dates_previously_examined_in_phases_38_41",
    }
