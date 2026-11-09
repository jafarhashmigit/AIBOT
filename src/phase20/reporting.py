"""Phase 20 shadow activity summary (not trading performance proof)."""

from __future__ import annotations

from typing import Any

from phase18.constants import HORIZON_LABELS, HORIZONS
from phase18.experience import ExperienceStore
from phase18.store import Phase18Store
from phase20.constants import CANDIDATE_STATUS, CHAMPION_STATUS, SOURCE_HISTORICAL, SOURCE_SHADOW


def build_activity_summary(
    *,
    store: Phase18Store,
    experience: ExperienceStore,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decisions = store.decisions()
    outcomes = store.outcomes()
    buy = sum(1 for d in decisions if str(d.get("experimental_action")).upper() == "BUY")
    sell = sum(1 for d in decisions if str(d.get("experimental_action")).upper() == "SELL")
    wait = sum(1 for d in decisions if str(d.get("experimental_action")).upper() == "WAIT")

    by_horizon: dict[str, dict[str, int]] = {
        hid: {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0, "BUY": 0, "SELL": 0}
        for hid in HORIZONS
    }
    for o in outcomes:
        hid = o.get("horizon_id", "")
        if hid not in by_horizon:
            continue
        st = str(o.get("status", "PENDING")).upper()
        if st in by_horizon[hid]:
            by_horizon[hid][st] += 1
        side = str(o.get("side", "")).upper()
        if side in {"BUY", "SELL"} and st in {"PASS", "FAIL", "TIMEOUT"}:
            by_horizon[hid][side] = by_horizon[hid].get(side, 0) + 1

    counts = experience.counts()
    session = session or {}
    return {
        "label": "shadow_observations_not_validated_trading_performance",
        "observation_count": len(decisions),
        "BUY_count": buy,
        "SELL_count": sell,
        "WAIT_count": wait,
        "discord_signals_sent": session.get("discord_signals_sent", 0),
        "pending_outcomes": sum(1 for o in outcomes if str(o.get("status")).upper() == "PENDING"),
        "completed_outcomes": sum(
            1 for o in outcomes if str(o.get("status")).upper() in {"PASS", "FAIL", "TIMEOUT"}
        ),
        "PASS_FAIL_TIMEOUT_by_horizon": {
            HORIZON_LABELS[hid]: {
                "PASS": by_horizon[hid]["PASS"],
                "FAIL": by_horizon[hid]["FAIL"],
                "TIMEOUT": by_horizon[hid]["TIMEOUT"],
                "PENDING": by_horizon[hid]["PENDING"],
            }
            for hid in HORIZONS
        },
        "BUY_SELL_completed_by_horizon": {
            HORIZON_LABELS[hid]: {"BUY": by_horizon[hid].get("BUY", 0), "SELL": by_horizon[hid].get("SELL", 0)}
            for hid in HORIZONS
        },
        "AGENT_SHADOW_experience_count": counts.get("agent_shadow", 0),
        "HISTORICAL_HYPOTHETICAL_experience_count": counts.get("historical_hypothetical", 0),
        "experience_sources": {
            "AGENT_SHADOW": SOURCE_SHADOW,
            "HISTORICAL_HYPOTHETICAL": SOURCE_HISTORICAL,
        },
        "phase19_synthetic_records_excluded": True,
        "broker_orders": 0,
        "production_actions": "WAIT",
        "champion": CHAMPION_STATUS,
        "h13c_status": CANDIDATE_STATUS,
        "note": (
            "Statistics are shadow observations only — not proof of a trading edge. "
            "Infrastructure/shadow validation only."
        ),
    }
