"""Part E — AIBOT integration boundaries for external provider signals."""

from __future__ import annotations

from typing import Any

from phase15a.constants import (
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    FORBIDDEN_MERGE_SOURCES,
    SOURCE_TYPE,
    STAGE_B_AUTHORIZED,
)


def integration_boundaries() -> dict[str, Any]:
    return {
        "external_source_type": SOURCE_TYPE,
        "must_remain_separate_from": list(FORBIDDEN_MERGE_SOURCES),
        "phase6_unchanged": True,
        "phase12_unchanged": True,
        "phase12c_unchanged": True,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "champion_altered": False,
        "buy_sell_enabled": BUY_SELL_ENABLED,
        "stage_b_authorized": STAGE_B_AUTHORIZED,
        "rules": [
            "External provider signals are a separate research source only.",
            "Do not merge into HISTORICAL_HYPOTHETICAL, AGENT_PAPER, or FORWARD_SHADOW stores.",
            "Do not alter Phase 6, Phase 12, or Phase 12C artifacts.",
            "Do not change champion NO_MODEL / no_model.",
            "Do not enable BUY/SELL.",
            "Do not train AI/ML on Telegram-derived data without explicit consent.",
        ],
    }


def assert_boundaries() -> None:
    bounds = integration_boundaries()
    assert bounds["champion_status"] == "NO_MODEL"
    assert bounds["buy_sell_enabled"] is False
    assert bounds["stage_b_authorized"] is False
    assert SOURCE_TYPE not in FORBIDDEN_MERGE_SOURCES
