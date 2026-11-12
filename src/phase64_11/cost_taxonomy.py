"""Canonical execution-cost taxonomy and COST_MODEL_VALIDATED decision."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    CALCULATED,
    ESTIMATED,
    LIVE_ACCOUNT,
    TAXONOMY_VERSION,
    UNKNOWN,
    UNKNOWN_FOR_EXECUTION,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)


def _cost(
    name: str,
    *,
    evidence_source: str,
    evidence_type: str,
    unit: str,
    formula: str | None,
    verification_status: str,
    account_specific_status: str,
    uncertainty: str,
    backtest_eligible: bool,
    demo_risk_gating_eligible: bool,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "cost": name,
        "evidence_source": evidence_source,
        "evidence_type": evidence_type,
        "unit": unit,
        "deterministic_formula": formula,
        "verification_status": verification_status,
        "account_specific_status": account_specific_status,
        "uncertainty": uncertainty,
        "backtest_replay_eligible": backtest_eligible,
        "demo_risk_gating_eligible": demo_risk_gating_eligible,
        "notes": notes,
    }


def build_cost_taxonomy(*, observed_spread_points: float = 240.0) -> dict[str, Any]:
    costs = [
        _cost(
            "spread",
            evidence_source="MT5 symbol_info bid/ask",
            evidence_type=LIVE_ACCOUNT,
            unit="points",
            formula="(ask-bid)/tick_size; USD≈points*tick_value*(volume/0.01)",
            verification_status="VERIFIED_SNAPSHOT",
            account_specific_status="VERIFIED_SNAPSHOT",
            uncertainty="Floating; snapshot ≠ future",
            backtest_eligible=True,
            demo_risk_gating_eligible=True,
            notes=f"Observed ~{observed_spread_points} points at Phase64.7 probe",
        ),
        _cost(
            "slippage_execution_deviation",
            evidence_source="Requires fill vs reference",
            evidence_type=UNKNOWN,
            unit="price_units",
            formula=None,
            verification_status=UNKNOWN,
            account_specific_status=UNKNOWN,
            uncertainty="No trade fills",
            backtest_eligible=False,
            demo_risk_gating_eligible=False,
            notes="May be conservatively bounded by deviation parameter in future policy; not verified",
        ),
        _cost(
            "commission",
            evidence_source="No trade deals",
            evidence_type=UNKNOWN,
            unit="account_currency",
            formula=None,
            verification_status=UNKNOWN,
            account_specific_status=UNKNOWN,
            uncertainty="Account-specific unknown; published not mapped",
            backtest_eligible=False,
            demo_risk_gating_eligible=False,
        ),
        _cost(
            "swap_financing",
            evidence_source="symbol_info swap_long conflict + no overnight deals",
            evidence_type=LIVE_ACCOUNT,  # current rate exists but execution state UNKNOWN_FOR_EXECUTION
            unit="points_per_lot_per_day",
            formula="metadata rate; overnight charge unproven",
            verification_status=UNKNOWN_FOR_EXECUTION,
            account_specific_status=UNKNOWN_FOR_EXECUTION,
            uncertainty="Conflict -488.7 vs -644.8; charged swap unproven",
            backtest_eligible=False,
            demo_risk_gating_eligible=False,
        ),
        _cost(
            "conversion_cost",
            evidence_source="margin currency XAU / profit USD",
            evidence_type=UNKNOWN,
            unit="account_currency",
            formula=None,
            verification_status=UNKNOWN,
            account_specific_status=UNKNOWN,
            uncertainty="Conversion path for margin/PnL adjustments not separately observed",
            backtest_eligible=False,
            demo_risk_gating_eligible=False,
            notes="May be N/A for USD profit on XAUUSDm PnL; not proven for all charges",
        ),
        _cost(
            "other_broker_charges",
            evidence_source="No fee fields on trade deals",
            evidence_type=UNKNOWN,
            unit="account_currency",
            formula=None,
            verification_status=UNKNOWN,
            account_specific_status=UNKNOWN,
            uncertainty="No trade deals",
            backtest_eligible=False,
            demo_risk_gating_eligible=False,
        ),
        _cost(
            "data_session_constraints",
            evidence_source="Sessions UNKNOWN",
            evidence_type=UNKNOWN,
            unit="boolean_gate",
            formula="block if session schedule unknown",
            verification_status=UNKNOWN,
            account_specific_status=UNKNOWN,
            uncertainty="Schedule not API-verified",
            backtest_eligible=False,
            demo_risk_gating_eligible=True,
            notes="Conservative block is an engineering gate, not a cash cost",
        ),
    ]

    # Completeness requirements (objective)
    requirements = {
        "deterministic_spread_model": True,  # snapshot + formula exist
        "deterministic_or_bounded_slippage": False,
        "commission_resolved_or_safely_bounded": False,
        "swap_resolved_or_safely_bounded": False,
        "conversion_resolved_or_non_applicable": False,
        "no_material_unresolved_cost": False,
    }
    # Conservative bound attempt without fill: only session gate + spread snapshot qualify
    conservative_bounds = {
        "spread": "USE_LIVE_SNAPSHOT_PLUS_SPREAD_GUARD",
        "slippage": "NOT_SAFELY_BOUNDED_WITHOUT_POLICY_PROXY",
        "commission": "NOT_SAFELY_BOUNDED_WITHOUT_ACCOUNT_SCHEDULE_OR_FILL",
        "swap": "NOT_SAFELY_BOUNDED_FOR_OVERNIGHT_WITHOUT_RECONCILED_RATE_AND_HOLD_EVIDENCE",
        "note": "Do not invent numerical commission/swap bounds as verified",
    }

    validated = all(requirements.values())
    out = {
        "taxonomy_version": TAXONOMY_VERSION,
        "costs": costs,
        "mixing_rule": "Never mix VERIFIED with ESTIMATED or UNKNOWN in a single synthetic total",
        "tick_value_for_point_costs": VERIFIED_TICK_VALUE,
        "COST_MODEL_VALIDATED_requirements": requirements,
        "COST_MODEL_VALIDATED": validated,
        "current_state": "INCOMPLETE",
        "conservative_bounds": conservative_bounds,
        "evaluation": (
            "Spread snapshot model exists; slippage/commission/swap/conversion remain unresolved "
            "or not safely bounded without fill/account-type evidence → COST_MODEL remains INCOMPLETE"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
