"""Static audit of paper lifecycle construction / invocation paths (read-only)."""

from __future__ import annotations

from typing import Any

from phase64_3.constants import APPROVED_FACTORY, HARDENING_VERSION, canonical_json_sha256

# Classification:
# APPROVED — sole path for new paper runs (Phase64.3)
# LEGACY_EXPLICIT — historical phase runners/tests; not approved for new paper runs
# HARDENED_INTERNAL — phase64_2 factory used only via approved wrapper / own phase tests
# TEST_REGRESSION — allowed in regression suites; not production paper entry

ENTRY_POINTS: list[dict[str, Any]] = [
    {
        "path": "phase64_3.approved_runtime.make_approved_paper_engine",
        "kind": "factory",
        "classification": "APPROVED",
        "notes": "Sole approved factory for new AIBOT paper runs",
    },
    {
        "path": "phase64_3.run_phase64_3 / paper_run CLI",
        "kind": "cli_runner",
        "classification": "APPROVED",
        "notes": "Operational paper validation runner",
    },
    {
        "path": "phase64_2.engine.make_hardened_engine",
        "kind": "factory",
        "classification": "HARDENED_INTERNAL",
        "notes": "Underlying hardened implementation; new runs must go through phase64_3 wrapper",
    },
    {
        "path": "phase64_2.run_phase64_2",
        "kind": "cli_runner",
        "classification": "LEGACY_EXPLICIT",
        "notes": "Hardening validation phase runner — not the ongoing paper runtime entry",
    },
    {
        "path": "phase64_1.engine.make_canonical_engine",
        "kind": "factory",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
        "notes": "Lacks 64.2 intent/WAIT/status hardening; accidental use blocked by adoption policy",
    },
    {
        "path": "phase64_1.run_phase64_1",
        "kind": "cli_runner",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
    },
    {
        "path": "phase57_1.durable_engine.make_durable_engine",
        "kind": "factory",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
        "notes": "No canonical identity / intent journal / WAIT durability",
    },
    {
        "path": "phase57_1.run_phase57_1 / cli",
        "kind": "cli_runner",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "MEDIUM",
    },
    {
        "path": "phase57.adapter.make_engine",
        "kind": "factory",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
    },
    {
        "path": "phase56.lifecycle.IntegratedLifecycleEngine + cli/poller/run_phase56",
        "kind": "factory_cli",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
    },
    {
        "path": "phase55.harness / audit LifecycleEngine",
        "kind": "test_harness",
        "classification": "TEST_REGRESSION",
        "bypass_risk": "LOW",
        "notes": "Engineering tests only",
    },
    {
        "path": "phase54.LifecycleEngine / run_phase54 / replay",
        "kind": "factory_cli",
        "classification": "LEGACY_EXPLICIT",
        "bypass_risk": "HIGH",
        "notes": "Original paper FSM; no durable intent/snapshot hardening",
    },
]


def audit_entry_points() -> dict[str, Any]:
    approved = [e for e in ENTRY_POINTS if e["classification"] == "APPROVED"]
    legacy = [e for e in ENTRY_POINTS if e["classification"] == "LEGACY_EXPLICIT"]
    high = [e for e in legacy if e.get("bypass_risk") == "HIGH"]
    out = {
        "approved_factory": APPROVED_FACTORY,
        "hardening_version": HARDENING_VERSION,
        "entry_points": ENTRY_POINTS,
        "n_entry_points": len(ENTRY_POINTS),
        "n_approved": len(approved),
        "n_legacy_explicit": len(legacy),
        "n_high_bypass_risk_legacy": len(high),
        "remediation": {
            "phase0_64_2_modified": False,
            "strategy": (
                "Phase64.3 is the sole APPROVED paper runtime. Legacy factories remain for "
                "historical regression immutability but are classified LEGACY_EXPLICIT and "
                "must not be used for new paper runs. Runtime assert_hardened_runtime enforces "
                "HardenedLifecycleEngine on the approved path."
            ),
            "before": "Multiple factories (54/56/57/57.1/64.1/64.2) could start paper runs",
            "after": "New paper runs → make_approved_paper_engine only",
        },
        "accidental_bypass_eliminated_for_approved_path": True,
        "legacy_still_importable_for_regression": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
