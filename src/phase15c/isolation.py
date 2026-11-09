"""AIBOT isolation boundaries for external provider data."""

from __future__ import annotations

from typing import Any

from phase15c.constants import (
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    FORBIDDEN_MERGE_SOURCES,
    SOURCE_TYPE,
    STAGE_B_AUTHORIZED,
)


def isolation_boundaries() -> dict[str, Any]:
    return {
        "external_source_type": SOURCE_TYPE,
        "must_remain_separate_from": list(FORBIDDEN_MERGE_SOURCES),
        "phase1_to_15b_unchanged": True,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "champion_altered": False,
        "buy_sell_enabled": BUY_SELL_ENABLED,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
        "model_training_allowed": False,
        "decision_policies_altered": False,
        "rules": [
            "Provider data must not merge into HISTORICAL_HYPOTHETICAL, AGENT_PAPER, or FORWARD_SHADOW.",
            "Do not modify Phase 1–15B artifacts.",
            "Do not train models or alter decision policies.",
            "Champion remains NO_MODEL.",
        ],
    }


def assert_isolation() -> None:
    bounds = isolation_boundaries()
    assert bounds["champion_status"] == "NO_MODEL"
    assert bounds["buy_sell_enabled"] is False
    assert SOURCE_TYPE not in FORBIDDEN_MERGE_SOURCES
