"""Separate experience stores — never merge HISTORICAL_HYPOTHETICAL and AGENT_SHADOW."""

from __future__ import annotations

from typing import Any

from phase42.progress import write_json


def write_experience_stores(eval_payload: dict[str, Any]) -> dict[str, Any]:
    historical = []
    for r in eval_payload.get("results") or []:
        dec = r.get("decision_validation") or {}
        if dec.get("skipped"):
            continue
        historical.append(
            {
                "hypothesis_id": r["hypothesis_id"],
                "experience_source": "HISTORICAL_HYPOTHETICAL",
                "n_scored": dec.get("n_scored"),
                "mean_net_r": dec.get("mean_net_r"),
                "note": "Counterfactual fills from historical ticks; not live agent decisions",
            }
        )

    # Shadow store: structure only — Phase42 does not run live shadow
    shadow = {
        "experience_source": "AGENT_SHADOW",
        "n_decisions": 0,
        "records": [],
        "note": "No shadow session executed in Phase42; store reserved and unmerged",
    }

    payload = {
        "HISTORICAL_HYPOTHETICAL": historical,
        "AGENT_SHADOW": shadow,
        "merged": False,
        "policy": "Never merge histories or metrics across experience sources",
    }
    write_json("experience_stores.json", payload)
    return payload
