"""Freeze complete policies before opening confirmation."""

from __future__ import annotations

from typing import Any

from phase53.constants import REPORTS_DIR, canonical_json_sha256
from phase53.policies import family_registry
from phase53.progress import write_json


def freeze_policies(discovery: dict[str, Any]) -> dict[str, Any]:
    reg = family_registry()
    survivors = list(discovery.get("survivors") or [])
    payload = {
        "registry_sha256": reg["registry_sha256"],
        "families": reg["families"],
        "frozen_ood_bounds": discovery.get("frozen_ood_bounds") or {},
        "survivor_family_ids": survivors,
        "n_survivors": len(survivors),
        "frozen_before_confirmation": True,
        "no_retuning_allowed": True,
        "horizon_bars": 12,
        "event_stride": 12,
        "cost_primary": "OBSERVED_BIDASK_ONLY",
        "cost_stress": "STRESS_SPREAD_WIDEN_1_5X",
        "commission": None,
        "slippage": None,
        "note": "WAIT is an explicit economic action when gates fail or regime is OOD.",
    }
    payload["policy_freeze_sha256"] = canonical_json_sha256(
        {k: v for k, v in payload.items() if k != "policy_freeze_sha256"}
    )
    write_json(REPORTS_DIR / "policy_freeze.json", payload)
    write_json(REPORTS_DIR / "hypothesis_registry.json", reg)
    return payload
