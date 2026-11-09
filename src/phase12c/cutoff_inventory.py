"""Inventory of Phase 6 cutoff / validation checks. Read-only documentation helper."""

from __future__ import annotations

from phase12c.constants import RESEARCH_CUTOFF_UTC

# Every known rejection point on the Phase 6 evaluation path.
CUTOFF_CHECKS = [
    {
        "component": "phase6.information_boundary.assert_before_cutoff",
        "trigger": f"timestamp > {RESEARCH_CUTOFF_UTC}",
        "effect": "InformationBoundaryError",
        "forward_compatible": False,
    },
    {
        "component": "phase6.schemas.Observation.__post_init__",
        "trigger": "calls assert_before_cutoff(self.timestamp)",
        "effect": "cannot construct Phase 6 Observation after cutoff",
        "forward_compatible": False,
    },
    {
        "component": "phase6.information_boundary.assert_decision_time_payload",
        "trigger": "as_of > RESEARCH_CUTOFF when as_of is supplied",
        "effect": "InformationBoundaryError",
        "forward_compatible": False,
    },
    {
        "component": "phase6.decision_engine.DecisionEngine.decide",
        "trigger": "assert_decision_time_payload(..., as_of=observation.timestamp)",
        "effect": "refuses post-cutoff observation.timestamp",
        "forward_compatible": False,
    },
    {
        "component": "phase6.risk_gate.RiskGate.evaluate",
        "trigger": "observation.timestamp > RESEARCH_CUTOFF",
        "effect": "InformationBoundaryError; requires Phase 6 Observation",
        "forward_compatible": False,
    },
    {
        "component": "phase6.risk_gate.apply_gate",
        "trigger": "none (pure function on raw_decision + GateResult)",
        "effect": "BLOCK/WAIT mapping only; no timestamp check",
        "forward_compatible": True,
    },
    {
        "component": "phase6.risk_gate.GateResult",
        "trigger": "none",
        "effect": "immutable status container",
        "forward_compatible": True,
    },
    {
        "component": "phase6.risk_gate.RiskGate.__init__",
        "trigger": "none",
        "effect": "exposes frozen wait_only / champion_id / version",
        "forward_compatible": True,
    },
]


def inventory() -> dict:
    reusable = [c for c in CUTOFF_CHECKS if c["forward_compatible"]]
    blockers = [c for c in CUTOFF_CHECKS if not c["forward_compatible"]]
    return {
        "research_cutoff": RESEARCH_CUTOFF_UTC,
        "checks": CUTOFF_CHECKS,
        "reusable_without_modifying_phase6": [c["component"] for c in reusable],
        "forward_blockers": [c["component"] for c in blockers],
        "full_evaluate_parity": "NOT_PROVEN",
        "note": (
            "A forward adapter may reuse apply_gate + GateResult + RiskGate config. "
            "It must not claim RiskGate.evaluate() or DecisionEngine.decide() parity "
            "on post-cutoff Observations."
        ),
    }
