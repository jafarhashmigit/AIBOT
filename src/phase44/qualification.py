"""Final Phase44 verdict."""

from __future__ import annotations

from typing import Any


def decide_verdict(
    discovery: dict[str, Any],
    validation: dict[str, Any] | None,
    *,
    indep_ok: bool,
    preflight_ok: bool,
) -> dict[str, Any]:
    if not preflight_ok:
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "preflight data integrity failed",
            "best_candidate": "NONE",
        }
    if not indep_ok:
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "independent recomputation mismatch",
            "best_candidate": "NONE",
        }

    survivors = discovery.get("survivor_ids") or []
    if not survivors:
        if not (discovery.get("results") or []):
            return {
                "final_verdict": "NO_NEW_HYPOTHESES",
                "reason": "no hypotheses evaluated",
                "best_candidate": "NONE",
            }
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "no hypothesis survived discovery gates under Bonferroni/LODO",
            "best_candidate": "NONE",
            "rejected": discovery.get("rejected"),
        }

    # If survivors exist but validation not run
    if validation is None:
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "survivors exist but validation missing",
            "best_candidate": "NONE",
        }

    pred_ok = [r for r in validation.get("results") or [] if r.get("predictive_confirmed")]
    dec_ok = [r for r in validation.get("results") or [] if r.get("decision_confirmed") and r.get("predictive_confirmed")]

    if not pred_ok:
        # check if insufficient evidence vs failed
        insuff = any(
            any("val_n=" in x for x in (r.get("rejection_reasons") or []))
            for r in (validation.get("results") or [])
        )
        if insuff and not any(r.get("validation_predictive", {}).get("effect", 0) for r in (validation.get("results") or [])):
            pass
        return {
            "final_verdict": "NO_PREDICTIVE_VALUE",
            "reason": "survivors failed one-shot validation predictive confirmation",
            "best_candidate": "NONE",
            "validation_results": validation.get("results"),
        }

    if pred_ok and not dec_ok:
        best = pred_ok[0]["hypothesis_id"]
        return {
            "final_verdict": "PREDICTIVE_BUT_NO_DECISION_VALUE",
            "reason": "validation confirmed predictive association but not bid/ask decision expectancy under stress",
            "best_candidate": best,
            "predictive_ids": [r["hypothesis_id"] for r in pred_ok],
        }

    # Both predictive and decision confirmed on independent UNSEEN validation dates
    best = dec_ok[0]["hypothesis_id"]
    # Prefer higher validation effect
    best = max(
        dec_ok,
        key=lambda r: float((r.get("validation_predictive") or {}).get("effect") or -999),
    )["hypothesis_id"]
    return {
        "final_verdict": "INDEPENDENT_VALIDATION_READY",
        "reason": (
            "Predictive and decision value confirmed on preregistered Phase43 UNSEEN validation dates; "
            "still not production. Further live/broker and larger-sample work remain."
        ),
        "best_candidate": best,
        "decision_ids": [r["hypothesis_id"] for r in dec_ok],
        "note": "INDEPENDENT_VALIDATION_READY ≠ production promotion",
    }
