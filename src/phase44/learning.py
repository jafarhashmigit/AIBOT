"""Separate experience stores — never merge."""

from __future__ import annotations

from typing import Any

from phase44.progress import write_json


def write_experience_stores(discovery: dict[str, Any], validation: dict[str, Any] | None) -> dict[str, Any]:
    historical = []
    for block in (discovery, validation or {}):
        for r in block.get("results") or []:
            dec = r.get("discovery_decision") or r.get("validation_decision") or {}
            if dec.get("skipped") or dec.get("n_scored") is None:
                continue
            historical.append(
                {
                    "hypothesis_id": r["hypothesis_id"],
                    "split": block.get("split"),
                    "experience_source": "HISTORICAL_HYPOTHETICAL",
                    "n_scored": dec.get("n_scored"),
                    "mean_net_r": dec.get("mean_net_r"),
                }
            )
    payload = {
        "HISTORICAL_HYPOTHETICAL": historical,
        "AGENT_SHADOW": {
            "experience_source": "AGENT_SHADOW",
            "n_decisions": 0,
            "records": [],
            "note": "Empty — no live/forward shadow run in Phase44",
        },
        "merged": False,
    }
    write_json("experience_stores.json", payload)
    return payload
