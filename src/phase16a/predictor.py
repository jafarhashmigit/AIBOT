"""H13_C experimental shadow prediction + Phase 12C gate (no bypass)."""

from __future__ import annotations

import json
from typing import Any

from phase12c.gate_adapter import ForwardGateAdapter
from phase14.h1_trend import build_h1_series, h1_trend_at
from phase14.strategy import decide_h13c
from phase16a.constants import (
    CANDIDATE,
    CANDIDATE_STATUS,
    CHAMPION,
    CHAMPION_STATUS,
    FROZEN_CUTS,
)
from phase16a.features import latest_features, market_regime


def frozen_cuts() -> dict[str, Any]:
    return dict(FROZEN_CUTS)


def predict_h13c_experimental(
    *,
    m5_closes: list[float],
    h1_rows: list[dict],
    decision_time_utc: str,
) -> dict[str, Any]:
    """Return experimental H13_C action; production final_action remains gated."""
    feat = latest_features(m5_closes)
    series = build_h1_series(h1_rows)
    h1_ctx = h1_trend_at(series, decision_time_utc, strict_gt=True)
    cuts = frozen_cuts()
    action, reason = decide_h13c(feat, h1_ctx, cuts)

    gate = ForwardGateAdapter().apply(action)
    # Safety: champion path must not emit production BUY/SELL
    if gate["final_action"] != "WAIT" and CHAMPION_STATUS == "NO_MODEL":
        raise RuntimeError("HARD FAILURE: gate produced non-WAIT under NO_MODEL")

    return {
        "candidate_id": CANDIDATE,
        "candidate_status": CANDIDATE_STATUS,
        "champion_id": CHAMPION,
        "champion_status": CHAMPION_STATUS,
        "experimental_action": action,
        "experimental_reason": reason,
        "raw_action": action,
        "feature_snapshot": feat,
        "h1_context": h1_ctx,
        "market_regime": market_regime(h1_ctx),
        "frozen_cuts": {
            "close_ema_low": cuts["close_ema_low"],
            "close_ema_high": cuts["close_ema_high"],
            "q_low": cuts["q_low"],
            "q_high": cuts["q_high"],
            "source": cuts["source"],
        },
        "gate": gate,
        "final_action": gate["final_action"],
        "feature_snapshot_json": json.dumps(feat or {}, sort_keys=True),
    }


def parity_smoke_cases() -> list[dict[str, Any]]:
    """Synthetic parity checks against decide_h13c (not live data)."""
    cuts = frozen_cuts()
    cases = []
    buy = decide_h13c(
        {"close_to_ema_20": cuts["close_ema_low"] - 0.0001, "ema_9_20_spread": 0.001},
        {"h1_trend": "up"},
        cuts,
    )
    sell = decide_h13c(
        {"close_to_ema_20": cuts["close_ema_high"] + 0.0001, "ema_9_20_spread": -0.001},
        {"h1_trend": "down"},
        cuts,
    )
    wait = decide_h13c(
        {"close_to_ema_20": cuts["close_ema_low"] - 0.0001, "ema_9_20_spread": -0.001},
        {"h1_trend": "up"},
        cuts,
    )
    cases.append({"name": "buy", "got": buy[0], "expected": "BUY"})
    cases.append({"name": "sell", "got": sell[0], "expected": "SELL"})
    cases.append({"name": "wait", "got": wait[0], "expected": "WAIT"})
    gated = ForwardGateAdapter().apply("BUY")
    cases.append(
        {
            "name": "gate_blocks_buy",
            "got": gated["final_action"],
            "expected": "WAIT",
            "gate_status": gated["gate_status"],
        }
    )
    return cases
