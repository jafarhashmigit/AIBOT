"""Champion selection — at most one; do not lower thresholds."""

from __future__ import annotations

from typing import Any

from signal_bot.final_selection.constants import (
    CHAMPION_STATUS,
    DISCORD_ACTIONABLE,
    MIN_INDEPENDENT_COMPLETE_LIVE_DATES,
    MIN_NET_EXPECTANCY_R,
    MIN_REALIZED_TRADES,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    REQUIRE_NET_ESTABLISHED,
    RISK_POLICY,
    VERDICT_NONE,
    VERDICT_QUALIFIED,
    VERDICT_SAFETY,
)


def qualification_checklist(candidate_eval: dict[str, Any], economics: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "implementable_from_evidence": bool(candidate_eval.get("implementable_from_evidence")),
        "positive_net_expectancy_under_supported_costs": False,
        "net_profitability_established": economics.get("NET_PROFITABILITY") == "ESTABLISHED",
        "robust_across_date_blocks": False,
        "not_one_trade_dependent": False,
        "acceptable_drawdown_demonstrated": False,
        "stable_parameters_demonstrated": False,
        "cost_sensitivity_ok": False,
        "independent_live_sample_adequate": (
            int(candidate_eval.get("live_complete_asia_london_dates") or 0)
            >= MIN_INDEPENDENT_COMPLETE_LIVE_DATES
        ),
        "trade_count_adequate": int(candidate_eval.get("n_trades") or 0) >= MIN_REALIZED_TRADES,
        "beats_WAIT_baseline": False,
    }
    # Net expectancy: only if established and > floor
    net_r = candidate_eval.get("expectancy_net_r")
    if checks["net_profitability_established"] and net_r is not None:
        checks["positive_net_expectancy_under_supported_costs"] = float(net_r) > MIN_NET_EXPECTANCY_R

    if REQUIRE_NET_ESTABLISHED and not checks["net_profitability_established"]:
        checks["positive_net_expectancy_under_supported_costs"] = False

    all_pass = all(checks.values())
    return {"checks": checks, "all_pass": all_pass}


def select_champion(
    *,
    matrix: dict[str, Any],
    c07: dict[str, Any],
    economics: dict[str, Any],
) -> dict[str, Any]:
    if ORDER_SEND != "PROHIBITED" or CHAMPION_STATUS != "NO_MODEL":
        return {
            "primary_verdict": VERDICT_SAFETY,
            "champion_candidate_id": None,
            "champion_status": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "implementation": "NONE",
            "discord_actionable": DISCORD_ACTIONABLE,
            "risk_policy": RISK_POLICY,
        }

    checklist = qualification_checklist(c07, economics)

    # No alternate candidate has surviving confirmatory evidence
    alternates_considered = [
        {
            "id": "H70_LS1",
            "result": "EXCLUDED — exploratory negative; retune forbidden",
        },
        {
            "id": "retired_phase45_families",
            "result": "EXCLUDED — do_not_revive",
        },
        {
            "id": "H69_D1_US1",
            "result": "EXCLUDED — unresolved / unconfirmed",
        },
    ]

    if checklist["all_pass"] and c07.get("disposition") != "REJECT_UNIMPLEMENTABLE":
        return {
            "primary_verdict": VERDICT_QUALIFIED,
            "champion_candidate_id": c07.get("candidate_id"),
            "champion_status": "UNVALIDATED_PENDING_PROMPT10",  # would still need P10
            "production": PRODUCTION_FINAL_ACTION,
            "checklist": checklist,
            "implementation": "AUTHORIZED_IF_GATES",
            "alternates_considered": alternates_considered,
        }

    return {
        "primary_verdict": VERDICT_NONE,
        "champion_candidate_id": None,
        "champion_status": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "discord_actionable": DISCORD_ACTIONABLE,
        "risk_policy": RISK_POLICY,
        "order_send": ORDER_SEND,
        "checklist": checklist,
        "c07_disposition": c07.get("disposition"),
        "c07_reason": c07.get("reason"),
        "alternates_considered": alternates_considered,
        "implementation": "NONE — NullPolicy WAIT retained; no fake champion module",
        "thresholds_lowered": False,
        "n_accepted_validated_edges": matrix.get("n_accepted_validated_edges"),
        "rationale": (
            "No candidate demonstrated implementable evidence-derived rules, positive net "
            "expectancy under supported costs, and independent date-block robustness. "
            "C07_A rejected as unimplementable without arbitrary parameter invention. "
            "H70 and retired families excluded. Independent complete live dates below floor. "
            "NET_PROFITABILITY not established."
        ),
    }
