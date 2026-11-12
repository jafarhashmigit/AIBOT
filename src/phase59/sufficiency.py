"""Explicit data sufficiency matrix — missing ≠ zero."""

from __future__ import annotations

from typing import Any

from phase59.constants import canonical_json_sha256


def build_sufficiency(
    *,
    inventory: dict[str, Any],
    integrity: dict[str, Any],
    spread: dict[str, Any],
    costs: dict[str, Any],
    stress: dict[str, Any],
    observability: dict[str, Any],
    wait: dict[str, Any],
    experience: dict[str, Any],
) -> dict[str, Any]:
    obs_bars = int(spread.get("observable_bars") or 0)
    unobs = int(spread.get("unobservable_bars_no_ticks") or 0)
    spread_status = "SUFFICIENT" if obs_bars > 1000 and unobs / max(1, obs_bars + unobs) < 0.25 else (
        "PARTIALLY_SUFFICIENT" if obs_bars > 100 else "INSUFFICIENT"
    )

    matrix = [
        {
            "capability": "reliable_spread_measurement",
            "status": spread_status,
            "basis": f"observable_bars={obs_bars}, unobservable={unobs}",
        },
        {
            "capability": "commission_adjusted_evaluation",
            "status": "INSUFFICIENT",
            "basis": "commission UNKNOWN; must not treat as zero",
        },
        {
            "capability": "slippage_evaluation",
            "status": "INSUFFICIENT",
            "basis": "slippage UNKNOWN; stress proxies labeled hypothetical only",
        },
        {
            "capability": "session_based_analysis",
            "status": "PARTIALLY_SUFFICIENT" if (spread.get("by_session") or {}) else "INSUFFICIENT",
            "basis": "UTC session labels on demo ticks; live session microstructure unknown",
        },
        {
            "capability": "regime_based_research",
            "status": "PARTIALLY_SUFFICIENT",
            "basis": f"heuristic regimes={observability.get('regime_counts')}; disruptions unlabeled",
        },
        {
            "capability": "execution_aware_backtesting",
            "status": "PARTIALLY_SUFFICIENT",
            "basis": "bid/ask path fills observable; delay/commission/slippage not",
        },
        {
            "capability": "future_independent_edge_research",
            "status": "PARTIALLY_SUFFICIENT" if inventory.get("union_n_days", 0) >= 40 else "INSUFFICIENT",
            "basis": (
                f"union_days={inventory.get('union_n_days')}; Phase58 found no family; "
                "economics incomplete for live-cost claims"
            ),
        },
        {
            "capability": "dual_experience_learning_evaluation",
            "status": "PARTIALLY_SUFFICIENT" if (experience.get("agent_shadow") or {}).get("n", 0) > 0 else "INSUFFICIENT",
            "basis": f"shadow_n={(experience.get('agent_shadow') or {}).get('n')}, hist_n={(experience.get('historical_hypothetical') or {}).get('n')}",
        },
        {
            "capability": "wait_economics_descriptive",
            "status": "SUFFICIENT" if (wait.get("n_events") or 0) > 50 else "PARTIALLY_SUFFICIENT",
            "basis": f"n_events={wait.get('n_events')} on non-holdout days",
        },
        {
            "capability": "dataset_integrity_auditing",
            "status": "SUFFICIENT" if integrity.get("n_days", 0) > 0 else "INSUFFICIENT",
            "basis": f"audited_days={integrity.get('n_days')}, ok_days={integrity.get('n_ok')}",
        },
    ]

    statuses = [m["status"] for m in matrix]
    if any(s == "INSUFFICIENT" for s in statuses[:3]):  # spread ok maybe, commission/slippage insufficient
        overall = "DATA_SUFFICIENCY_LIMITED"
    else:
        overall = "MIXED"

    # Verdict helpers
    critical_unknowns = ["commission_adjusted_evaluation", "slippage_evaluation"]
    crit_insuf = [m for m in matrix if m["capability"] in critical_unknowns and m["status"] == "INSUFFICIENT"]

    out = {
        "matrix": matrix,
        "critical_unknowns_insufficient": crit_insuf,
        "overall_label": overall,
        "missing_never_zero": True,
        "stress_reproducible": bool(stress.get("stress_sha256")),
        "notes": [
            "Demo bid/ask supports path-embedded spread research",
            "Cannot claim commission/slippage-aware live edge evaluation",
            "Phase58 holdout remains sealed for strategy development",
        ],
    }
    out["sufficiency_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sufficiency_sha256"})
    return out


def choose_verdict(
    *,
    integrity: dict[str, Any],
    spread: dict[str, Any],
    sufficiency: dict[str, Any],
    holdout_sealed: bool,
) -> tuple[str, str]:
    if not holdout_sealed:
        return "EXECUTION_ECONOMICS_FAILED", "Phase58 holdout seal violated"
    if integrity.get("n_days", 0) == 0:
        return "EXECUTION_ECONOMICS_FAILED", "No days audited"
    obs = int(spread.get("observable_bars") or 0)
    if obs < 50:
        return "DATA_SUFFICIENCY_INSUFFICIENT", "Too few observable bid/ask bars for spread economics"

    # We always have commission/slippage UNKNOWN → cannot be full VALIDATED for complete economics
    # PARTIAL is honest if spread+integrity+stress delivered
    if sufficiency.get("critical_unknowns_insufficient"):
        # Check observability breadth
        if obs >= 500 and integrity.get("n_ok", 0) >= max(1, int(0.5 * integrity.get("n_days", 1))):
            return (
                "EXECUTION_ECONOMICS_PARTIAL",
                "Spread/path fills measurable on demo archives; commission and slippage remain UNKNOWN; "
                "execution-aware live claims not supported.",
            )
        return (
            "MARKET_OBSERVABILITY_LIMITED",
            "Partial observability with critical unknown cost components and/or weak coverage.",
        )
    return (
        "EXECUTION_ECONOMICS_VALIDATED",
        "All classified cost components measured or explicitly documented with sufficient coverage.",
    )
