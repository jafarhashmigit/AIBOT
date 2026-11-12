"""Research-readiness scaffolding (30%) — no strategy mining / no model training."""

from __future__ import annotations

from typing import Any

from phase54.constants import (
    FEATURE_VERSION,
    HORIZON_BARS,
    POLICY_VERSION,
    REPORTS_DIR,
    RECIPE_ID,
    canonical_json_sha256,
)
from phase54.progress import write_json


def experiment_registry() -> dict[str, Any]:
    reg = {
        "recipe": RECIPE_ID,
        "purpose": "infrastructure_only",
        "no_strategy_mining": True,
        "no_model_training": True,
        "feature_version": FEATURE_VERSION,
        "policy_version": POLICY_VERSION,
        "frozen_policy": {
            "id": "NullPolicy",
            "champion": "NO_MODEL",
            "default_action": "WAIT",
            "validated_edge": False,
        },
        "event_rules": {
            "horizon_bars": HORIZON_BARS,
            "non_overlapping_stride": HORIZON_BARS,
            "buy_entry": "ASK",
            "buy_exit": "BID",
            "sell_entry": "BID",
            "sell_exit": "ASK",
            "commission": None,
            "slippage": None,
        },
        "baselines_interface": ["ALWAYS_WAIT", "CONSTANT_BUY", "CONSTANT_SELL"],
        "ood_interface": {
            "feature": "C02_rv_48",
            "method": "discovery_iqr_optional",
            "status": "interface_only",
        },
        "cost_sensitivity": ["OBSERVED_BIDASK_ONLY", "STRESS_SPREAD_WIDEN_1_5X"],
        "provenance_fields": ["archive_root", "day", "decision_idx", "feature_version", "policy_version"],
        "independent_recompute": "Replay same archive+policy; compare decision_ids/actions/net_r",
    }
    reg["registry_sha256"] = canonical_json_sha256({k: v for k, v in reg.items() if k != "registry_sha256"})
    write_json(REPORTS_DIR / "experiment_registry.json", reg)
    return reg


def dataset_provenance(archive_root: str, days: list[str]) -> dict[str, Any]:
    prov = {
        "archive_root": archive_root,
        "days": days,
        "n_days": len(days),
        "feature_version": FEATURE_VERSION,
        "forbidden_note": "Phase44 validation and Phase49 confirmation dates blocked",
    }
    prov["provenance_sha256"] = canonical_json_sha256({k: v for k, v in prov.items() if k != "provenance_sha256"})
    write_json(REPORTS_DIR / "dataset_provenance.json", prov)
    return prov
