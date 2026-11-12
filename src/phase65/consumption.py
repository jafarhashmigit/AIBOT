"""Date/event consumption registry — sealed holdout protection."""

from __future__ import annotations

import json
from typing import Any

from phase58.data import chronological_splits, eligible_days
from phase65.constants import (
    CONSUMPTION_PATH,
    N_DISCOVERY,
    N_VALIDATION,
    PROJECT_ROOT,
    canonical_json_sha256,
)


def _phase49_discovery_dates() -> list[str]:
    # From Phase49 final report / date_selection.json
    p = PROJECT_ROOT / "reports" / "phase49" / "date_selection.json"
    if p.is_file():
        obj = json.loads(p.read_text(encoding="utf-8"))
        return list(obj.get("discovery_dates") or obj.get("selected", {}).get("discovery_dates") or [])
    return []


def _phase49_confirmation_dates() -> list[str]:
    p = PROJECT_ROOT / "reports" / "phase49" / "date_selection.json"
    if p.is_file():
        obj = json.loads(p.read_text(encoding="utf-8"))
        return list(obj.get("confirmation_dates") or [])
    return []


def build_consumption_registry() -> dict[str, Any]:
    splits = chronological_splits()
    elig = eligible_days()
    p58_used = set(splits["discovery"]) | set(splits["validation"]) | set(splits["holdout_sealed"])
    p49_disc = set(_phase49_discovery_dates())
    p49_conf = set(_phase49_confirmation_dates())

    status: dict[str, str] = {}
    for d in elig:
        if d in splits["holdout_sealed"]:
            status[d] = "PHASE58_HOLDOUT_SEALED"
        elif d in splits["discovery"]:
            status[d] = "PHASE58_DISCOVERY_CONSUMED"
        elif d in splits["validation"]:
            status[d] = "PHASE58_VALIDATION_CONSUMED"
        elif d in p49_conf:
            status[d] = "PHASE49_CONFIRMATION_SEALED"
        elif d in p49_disc:
            status[d] = "PHASE49_DISCOVERY_CONSUMED"
        else:
            status[d] = "UNCONSUMED_ELIGIBLE"

    unconsumed = sorted(d for d, s in status.items() if s == "UNCONSUMED_ELIGIBLE")
    # Chronological Phase65 split from unconsumed only
    disc = unconsumed[:N_DISCOVERY]
    val = unconsumed[N_DISCOVERY : N_DISCOVERY + N_VALIDATION]
    leftover = unconsumed[N_DISCOVERY + N_VALIDATION :]

    out = {
        "eligible_n": len(elig),
        "status_by_day": status,
        "phase58_holdout_sealed": list(splits["holdout_sealed"]),
        "phase58_holdout_opened": False,
        "unconsumed_eligible": unconsumed,
        "phase65_discovery": disc,
        "phase65_validation": val,
        "phase65_leftover_unused": leftover,
        "holdout_policy": (
            "Phase58 holdout remains sealed. Not used for discovery, feature selection, "
            "parameter selection, or repeated evaluation. Open only once if a preregistered "
            "survivor exists — Phase65 does not open it unless survivors pass validation."
        ),
        "independent_holdout_available": len(splits["holdout_sealed"]) > 0,
        "sufficient_unconsumed_for_discovery": len(disc) >= 2 and len(val) >= 1,
        "n_discovery": len(disc),
        "n_validation": len(val),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    CONSUMPTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONSUMPTION_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def assert_holdout_sealed(used_days: list[str], holdout: list[str]) -> None:
    hit = sorted(set(used_days) & set(holdout))
    if hit:
        raise RuntimeError(f"sealed_holdout_leak:{hit}")
