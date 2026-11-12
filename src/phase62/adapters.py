"""Read-only adapters over prior phases — no mutation of Phase 0–61."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase61.constants import SUFFICIENCY_THRESHOLDS as P61_THRESHOLDS
from phase62.constants import EXPECTED_NULL_POLICY, PHASE58_SPLITS, PHASE61_REPORTS


def null_policy_ok() -> bool:
    return NullPolicy().version == EXPECTED_NULL_POLICY


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    obj = json.loads(PHASE58_SPLITS.read_text(encoding="utf-8"))
    return list(obj.get("holdout_sealed") or [])


def phase61_verdict() -> dict[str, Any]:
    p = PHASE61_REPORTS / "validation_results.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def phase61_thresholds() -> dict[str, Any]:
    return dict(P61_THRESHOLDS)


def mt5_api_capability() -> dict[str, Any]:
    return {
        "permitted": sorted(PERMITTED_MT5_API),
        "prohibited": sorted(PROHIBITED_MT5_API),
        "history_deals_get_permitted": "history_deals_get" not in PROHIBITED_MT5_API
        and "history_deals_get" in PERMITTED_MT5_API,
        "history_orders_get_permitted": "history_orders_get" not in PROHIBITED_MT5_API
        and "history_orders_get" in PERMITTED_MT5_API,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "note": (
            "Phase64.8 permits RO history/positions/orders get; order_send and mutation APIs remain prohibited. "
            "Phase62 does not activate native MT5 collection."
        ),
    }
