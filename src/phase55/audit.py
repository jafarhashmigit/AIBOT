"""Phase54 integration audit — connected vs class-exists-only."""

from __future__ import annotations

import inspect
from typing import Any

from phase54.constants import POLICY_VERSION
from phase54.decision import NullPolicy, decide
from phase54.experience import historical_store, shadow_store
from phase54.lifecycle import LifecycleEngine
from phase54.observer import build_observation
from phase54.paper_exec import open_paper_position
from phase54.risk import RiskManager
from phase55.constants import PHASE54_POLICY, REPORTS_DIR
from phase55.progress import write_json


def audit_phase54() -> dict[str, Any]:
    # Source inspection: LifecycleEngine wires components in process_bar
    src = inspect.getsource(LifecycleEngine.process_bar)
    checks = {
        "observer_connected": "build_observation(" in src,
        "decision_connected": "decide(" in src,
        "risk_connected": "self.risk.evaluate(" in src,
        "paper_entry_connected": "open_paper_position(" in src,
        "exit_connected": "force_horizon_exit_from_bars(" in src,
        "experience_shadow_connected": "record_agent_shadow(" in src,
        "experience_hist_connected": "record_historical_hypothetical(" in src,
        "persist_connected": "self.persist(" in src,
        "idempotency_connected": "already_processed(" in src,
    }
    # Default policy protection
    eng = LifecycleEngine()
    default_is_null = isinstance(eng.policy, NullPolicy)
    default_version = getattr(eng.policy, "version", None)

    # Production stores readable
    hist = historical_store()
    shadow = shadow_store()

    gaps = []
    if "monitor_and_maybe_exit" not in src:
        gaps.append(
            "LifecycleEngine uses horizon force-exit only; SL/TP monitoring exists in paper_exec but is not called in process_bar"
        )
    if "open_positions" in src and "force_horizon" in src:
        gaps.append("Open positions are closed in the same process_bar call — recovery-of-OPEN requires harness pause")

    report = {
        "phase54_policy_constant": POLICY_VERSION,
        "expected_null_policy": PHASE54_POLICY,
        "default_policy_is_NullPolicy": default_is_null,
        "default_policy_version": default_version,
        "production_null_untouched": default_is_null and default_version == POLICY_VERSION,
        "wiring_checks": checks,
        "all_core_wired": all(checks.values()),
        "production_hist_n": hist.n,
        "production_shadow_n": shadow.n,
        "components": {
            "observer": build_observation.__module__,
            "decision": decide.__module__,
            "risk": RiskManager.__module__,
            "paper_exec": open_paper_position.__module__,
            "lifecycle": LifecycleEngine.__module__,
            "experience": historical_store.__module__,
        },
        "known_gaps_for_verification": gaps,
        "note": "Phase55 harness reuses Phase54 primitives; does not modify Phase54 or activate EngineeringTestPolicy in production.",
    }
    write_json(REPORTS_DIR / "phase54_integration_audit.json", report)
    return report
