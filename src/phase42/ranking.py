"""Rank discoveries — not by win rate alone."""

from __future__ import annotations

from typing import Any


def rank_candidates(eval_payload: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for r in eval_payload.get("results") or []:
        val = r.get("validation") or {}
        boot = val.get("bootstrap") or {}
        score = 0.0
        # effect size
        eff = abs(val.get("effect") or 0)
        score += min(eff, 1.0) * 30
        # uncertainty: bonus if Bonferroni excludes 0
        if boot.get("bonferroni_excludes_zero"):
            score += 25
        elif boot.get("ci95_excludes_zero"):
            score += 10
        # sample
        score += min(val.get("n_events") or 0, 200) / 200 * 15
        score += min(val.get("n_dates") or 0, 5) / 5 * 10
        # chronological
        lodo = val.get("lodo") or {}
        if lodo.get("all_positive") or lodo.get("all_negative"):
            score += 10
        if r.get("decision_value"):
            score += 20
        if r.get("predictive_pass"):
            score += 15
        # penalize reject
        if not r.get("predictive_pass"):
            score -= 50
        ranked.append(
            {
                "hypothesis_id": r["hypothesis_id"],
                "family": r["family"],
                "status": r["status"],
                "rank_score": round(score, 3),
                "validation_effect": val.get("effect"),
                "n_events_val": val.get("n_events"),
                "decision_value": r.get("decision_value"),
                "components": {
                    "effect": eff,
                    "bonferroni": bool(boot.get("bonferroni_excludes_zero")),
                    "decision_value": r.get("decision_value"),
                },
            }
        )
    ranked.sort(key=lambda x: x["rank_score"], reverse=True)
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
    return ranked
