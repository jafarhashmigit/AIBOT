"""Campaign and session reporting for Phase 22."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase18.constants import HORIZON_LABELS, HORIZONS
from phase18.experience import ExperienceStore
from phase18.store import Phase18Store
from phase22.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    PHASE21_HISTORICAL_BUY_N,
    PHASE21_HISTORICAL_BUY_RATE,
    PHASE21_HISTORICAL_N,
    PHASE21_HISTORICAL_SELL_N,
    PHASE21_HISTORICAL_SELL_RATE,
)
from phase22.diagnostics import DiagnosticJournal


def build_campaign_report(
    *,
    campaign_state: dict[str, Any],
    store: Phase18Store,
    experience: ExperienceStore,
    diagnostics: DiagnosticJournal | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decisions = store.decisions()
    outcomes = store.outcomes()
    diag_rows = diagnostics.rows() if diagnostics is not None else []

    wait_reasons = Counter()
    buy_cond = sell_cond = 0
    for row in diag_rows:
        wait_reasons[row.get("wait_reason") or ""] += 1
        if str(row.get("buy_condition")).lower() in {"true", "1"}:
            buy_cond += 1
        if str(row.get("sell_condition")).lower() in {"true", "1"}:
            sell_cond += 1

    by_horizon: dict[str, dict[str, int]] = {
        hid: {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0, "BUY": 0, "SELL": 0} for hid in HORIZONS
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

    observed = int(campaign_state.get("observed_candles") or 0)
    buy = int(campaign_state.get("buy_count") or 0)
    sell = int(campaign_state.get("sell_count") or 0)
    wait = int(campaign_state.get("wait_count") or 0)
    fwd_buy_rate = buy / observed if observed else 0.0
    fwd_sell_rate = sell / observed if observed else 0.0
    # Condition frequency from diagnostics (may count buy_condition true even if...)
    # Prefer experimental action rates as forward signal frequency.
    exp_counts = experience.counts()

    return {
        "label": "forward_shadow_observation_not_validated_trading_performance",
        "campaign_id": campaign_state.get("campaign_id"),
        "target_candles": campaign_state.get("target_candles"),
        "total_observed_candles": observed,
        "remaining_candles": campaign_state.get("remaining_candles"),
        "number_of_sessions": len(campaign_state.get("sessions") or []),
        "BUY_count": buy,
        "SELL_count": sell,
        "WAIT_count": wait,
        "WAIT_reason_distribution": dict(wait_reasons),
        "BUY_condition_true_count": buy_cond,
        "SELL_condition_true_count": sell_cond,
        "forward_experimental_BUY_frequency": fwd_buy_rate,
        "forward_experimental_SELL_frequency": fwd_sell_rate,
        "discord_signals_sent": campaign_state.get("discord_signals_sent", 0),
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
        "AGENT_SHADOW_experience_count": exp_counts.get("agent_shadow", 0),
        "HISTORICAL_HYPOTHETICAL_count": exp_counts.get("historical_hypothetical", 0),
        "synthetic_phase19_excluded": True,
        "production_actions": "WAIT",
        "champion": CHAMPION_STATUS,
        "h13c_status": CANDIDATE_STATUS,
        "rejected_incomplete": campaign_state.get("rejected_incomplete", 0),
        "rejected_duplicate": campaign_state.get("rejected_duplicate", 0),
        "decision_rows": len(decisions),
        "phase21_comparison": {
            "historical_reachability_BUY_rate": PHASE21_HISTORICAL_BUY_RATE,
            "historical_reachability_SELL_rate": PHASE21_HISTORICAL_SELL_RATE,
            "historical_n": PHASE21_HISTORICAL_N,
            "historical_BUY_n": PHASE21_HISTORICAL_BUY_N,
            "historical_SELL_n": PHASE21_HISTORICAL_SELL_N,
            "forward_BUY_rate": fwd_buy_rate,
            "forward_SELL_rate": fwd_sell_rate,
            "note": (
                "Phase 21 rates are historical condition frequencies, not proven live signal "
                "frequencies or profitable trade rates. Forward rates are experimental signal "
                "frequencies from this campaign only."
            ),
        },
        "session": session,
        "note": (
            "Distinguish: (1) historical reachability, (2) forward experimental signal frequency, "
            "(3) outcome statistics. No statistical significance or profitability claimed."
        ),
    }
